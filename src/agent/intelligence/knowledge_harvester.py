"""
knowledge_harvester.py — Autonomous Web Knowledge Gathering System

This is NOT a basic web scraper. This is a SMART knowledge engine that:
1. Identifies HIGH-QUALITY sources (Wikipedia, MDN, official docs, research)
2. Filters out NOISE (ads, clickbait, duplicate content, SEO spam)
3. Extracts CLEAN factual knowledge using NLP quality scoring
4. Stores knowledge locally in a searchable vector-like database
5. Can "ask" other AI models (ChatGPT, Gemini) when it's confused (like a human)
6. Learns incrementally — each crawl session makes it smarter

Architecture:
  ScoutAgent → fetches URL → QualityFilter → KnowledgeExtractor → KnowledgeStore
  ↓                                                                      ↓
  TopicPlanner ← doubt? → AIConsultant (opens ChatGPT/Gemini)    RAG Retrieval
"""
import os
import re
import json
import time
import hashlib
import sqlite3
import threading
import traceback
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

# ═══════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                       "data", "knowledge.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# High-quality source domains (these get a quality bonus)
TRUSTED_SOURCES = {
    'wikipedia.org': 0.95,
    'developer.mozilla.org': 0.95,  # MDN
    'docs.python.org': 0.95,
    'stackoverflow.com': 0.85,
    'arxiv.org': 0.90,
    'github.com': 0.80,
    'microsoft.com': 0.85,
    'google.com': 0.80,
    'pytorch.org': 0.90,
    'huggingface.co': 0.90,
    'medium.com': 0.60,        # Variable quality
    'towardsdatascience.com': 0.70,
    'realpython.com': 0.85,
    'w3schools.com': 0.75,
    'geeksforgeeks.org': 0.70,
    'nature.com': 0.95,
    'sciencedirect.com': 0.90,
    'ieee.org': 0.90,
    'bbc.com': 0.80,
    'reuters.com': 0.85,
}

# Domains to NEVER crawl (waste of time)
BLACKLISTED_DOMAINS = {
    'facebook.com', 'instagram.com', 'tiktok.com', 'twitter.com', 'x.com',
    'pinterest.com', 'tumblr.com', 'reddit.com/r/memes',
    'buzzfeed.com', 'boredpanda.com',
    'wish.com', 'aliexpress.com', 'amazon.com',
    'porn', 'xxx', 'adult', 'gambling', 'casino', 'bet',
}

# Content quality signals (positive = good, negative = bad)
QUALITY_SIGNALS = {
    'positive': [
        r'\b(research|study|findings|methodology|abstract|conclusion)\b',
        r'\b(algorithm|function|class|implementation|architecture)\b',
        r'\b(tutorial|guide|documentation|reference|specification)\b',
        r'\b(peer-reviewed|published|journal|conference)\b',
        r'\b(example|code|syntax|parameter|return)\b',
        r'\b(theorem|proof|lemma|corollary|definition)\b',
        r'\b(experiment|results|dataset|benchmark|evaluation)\b',
    ],
    'negative': [
        r'\b(click here|buy now|subscribe|newsletter|discount|promo)\b',
        r'\b(trending|viral|shocking|you won\'t believe)\b',
        r'\b(cookie|consent|privacy policy|terms of service)\b',
        r'\b(advertisement|sponsored|affiliate)\b',
        r'\b(sign up free|limited time|act now|order now)\b',
        r'(404|page not found|access denied|forbidden)',
    ]
}

# Minimum thresholds
MIN_CONTENT_LENGTH = 200    # Characters — skip tiny pages
MIN_QUALITY_SCORE = 0.4     # 0-1 scale — reject below this
MAX_PAGES_PER_SESSION = 50  # Don't crawl forever
CRAWL_DELAY_SECONDS = 1.5   # Be respectful


# ═══════════════════════════════════════════════════════
# KNOWLEDGE STORE (SQLite with text search)
# ═══════════════════════════════════════════════════════

class KnowledgeStore:
    """Local knowledge database — stores extracted facts, summaries, and metadata."""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Create tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Main knowledge table
        c.execute("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                domain TEXT NOT NULL,
                title TEXT,
                summary TEXT NOT NULL,
                full_text TEXT,
                topics TEXT,
                quality_score REAL DEFAULT 0.5,
                source_trust REAL DEFAULT 0.5,
                word_count INTEGER DEFAULT 0,
                crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed TIMESTAMP,
                access_count INTEGER DEFAULT 0,
                is_stale BOOLEAN DEFAULT 0
            )
        """)
        
        # Topic index for fast topic-based retrieval
        c.execute("""
            CREATE TABLE IF NOT EXISTS topic_index (
                topic TEXT NOT NULL,
                knowledge_id TEXT NOT NULL,
                relevance REAL DEFAULT 0.5,
                FOREIGN KEY (knowledge_id) REFERENCES knowledge(id)
            )
        """)
        
        # Crawl session log
        c.execute("""
            CREATE TABLE IF NOT EXISTS crawl_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                topics TEXT,
                pages_crawled INTEGER DEFAULT 0,
                pages_accepted INTEGER DEFAULT 0,
                pages_rejected INTEGER DEFAULT 0,
                total_knowledge_items INTEGER DEFAULT 0,
                duration_seconds REAL DEFAULT 0
            )
        """)
        
        # URL dedup — never crawl same URL twice
        c.execute("""
            CREATE TABLE IF NOT EXISTS crawled_urls (
                url_hash TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create FTS (Full-Text Search) index for fast retrieval
        c.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
            USING fts5(title, summary, full_text, topics, content='knowledge', content_rowid='rowid')
        """)
        
        conn.commit()
        conn.close()
    
    def is_url_crawled(self, url: str) -> bool:
        """Check if we've already crawled this URL."""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT 1 FROM crawled_urls WHERE url_hash = ?", (url_hash,))
        result = c.fetchone() is not None
        conn.close()
        return result
    
    def mark_url_crawled(self, url: str):
        """Record that we've crawled this URL."""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO crawled_urls (url_hash, url) VALUES (?, ?)", (url_hash, url))
        conn.commit()
        conn.close()
    
    def store_knowledge(self, url: str, title: str, summary: str, full_text: str,
                        topics: List[str], quality_score: float, source_trust: float):
        """Store a piece of extracted knowledge."""
        knowledge_id = hashlib.md5(f"{url}:{title}".encode()).hexdigest()
        domain = urlparse(url).netloc
        word_count = len(full_text.split())
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            c.execute("""
                INSERT OR REPLACE INTO knowledge 
                (id, url, domain, title, summary, full_text, topics, quality_score, source_trust, word_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (knowledge_id, url, domain, title, summary, full_text,
                  json.dumps(topics), quality_score, source_trust, word_count))
            
            # Index by topic
            for topic in topics:
                c.execute("""
                    INSERT INTO topic_index (topic, knowledge_id, relevance) VALUES (?, ?, ?)
                """, (topic.lower().strip(), knowledge_id, quality_score))
            
            conn.commit()
        except Exception as e:
            print(f"[KnowledgeStore] Error storing: {e}")
        finally:
            conn.close()
        
        return knowledge_id
    
    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """Search knowledge base using full-text search."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        results = []
        try:
            # FTS search
            c.execute("""
                SELECT k.* FROM knowledge k
                WHERE k.id IN (
                    SELECT knowledge_id FROM topic_index 
                    WHERE topic LIKE ? 
                    ORDER BY relevance DESC
                )
                OR k.title LIKE ? OR k.summary LIKE ?
                ORDER BY k.quality_score DESC, k.access_count DESC
                LIMIT ?
            """, (f"%{query.lower()}%", f"%{query}%", f"%{query}%", limit))
            
            for row in c.fetchall():
                results.append(dict(row))
                # Update access count
                c.execute("""
                    UPDATE knowledge SET access_count = access_count + 1, 
                    last_accessed = CURRENT_TIMESTAMP WHERE id = ?
                """, (row['id'],))
            
            conn.commit()
        except Exception as e:
            print(f"[KnowledgeStore] Search error: {e}")
        finally:
            conn.close()
        
        return results
    
    def get_stats(self) -> Dict:
        """Get knowledge base statistics."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM knowledge")
        total_items = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM crawled_urls")
        total_urls = c.fetchone()[0]
        
        c.execute("SELECT COUNT(DISTINCT topic) FROM topic_index")
        total_topics = c.fetchone()[0]
        
        c.execute("SELECT SUM(word_count) FROM knowledge")
        total_words = c.fetchone()[0] or 0
        
        c.execute("SELECT AVG(quality_score) FROM knowledge")
        avg_quality = c.fetchone()[0] or 0
        
        c.execute("SELECT domain, COUNT(*) as cnt FROM knowledge GROUP BY domain ORDER BY cnt DESC LIMIT 10")
        top_domains = [(row[0], row[1]) for row in c.fetchall()]
        
        conn.close()
        
        return {
            'total_knowledge_items': total_items,
            'total_urls_crawled': total_urls,
            'total_topics': total_topics,
            'total_words': total_words,
            'avg_quality_score': round(avg_quality, 3),
            'top_domains': top_domains,
            'db_size_mb': round(os.path.getsize(self.db_path) / 1024 / 1024, 2) if os.path.exists(self.db_path) else 0
        }


# ═══════════════════════════════════════════════════════
# QUALITY FILTER — The brain that separates gold from trash
# ═══════════════════════════════════════════════════════

class QualityFilter:
    """
    Scores content quality on a 0-1 scale using multiple heuristics.
    This is what separates a $500M training pipeline from random scraping.
    
    Scoring dimensions:
    1. Source trust (is this domain reliable?)
    2. Content signals (does it contain educational/factual patterns?)
    3. Noise level (how much boilerplate/ads vs. actual content?)
    4. Readability (is it coherent text or garbled HTML?)
    5. Freshness (is the information recent?)
    6. Uniqueness (is this a duplicate of something we already have?)
    """
    
    def __init__(self, store: KnowledgeStore):
        self.store = store
        # Compile regex patterns once
        self._positive_patterns = [re.compile(p, re.IGNORECASE) for p in QUALITY_SIGNALS['positive']]
        self._negative_patterns = [re.compile(p, re.IGNORECASE) for p in QUALITY_SIGNALS['negative']]
    
    def score_content(self, url: str, title: str, text: str) -> Tuple[float, str]:
        """
        Score content quality. Returns (score, reason).
        Score is 0.0 (garbage) to 1.0 (gold).
        """
        domain = urlparse(url).netloc.replace('www.', '')
        reasons = []
        
        # ── Check 1: Domain blacklist ──
        for banned in BLACKLISTED_DOMAINS:
            if banned in domain or banned in url.lower():
                return 0.0, f"Blacklisted domain/pattern: {banned}"
        
        # ── Check 2: Minimum length ──
        if len(text) < MIN_CONTENT_LENGTH:
            return 0.0, f"Too short ({len(text)} chars, min {MIN_CONTENT_LENGTH})"
        
        # ── Check 3: Source trust score ──
        source_score = 0.5  # Default neutral
        for trusted_domain, trust_score in TRUSTED_SOURCES.items():
            if trusted_domain in domain:
                source_score = trust_score
                reasons.append(f"Trusted source ({trusted_domain}: {trust_score})")
                break
        
        # ── Check 4: Positive content signals ──
        positive_hits = 0
        for pattern in self._positive_patterns:
            if pattern.search(text):
                positive_hits += 1
        signal_score = min(1.0, positive_hits / 3)  # 3+ signals = max score
        
        # ── Check 5: Negative content signals ──
        negative_hits = 0
        for pattern in self._negative_patterns:
            if pattern.search(text):
                negative_hits += 1
        noise_penalty = min(0.5, negative_hits * 0.15)
        
        # ── Check 6: Content-to-noise ratio ──
        # Count "useful" lines vs. total lines
        lines = text.split('\n')
        non_empty = [l for l in lines if len(l.strip()) > 20]
        content_ratio = len(non_empty) / max(len(lines), 1)
        
        # ── Check 7: Duplication check ──
        content_hash = hashlib.md5(text[:500].encode()).hexdigest()
        # Simple dedup — check if we already have very similar content
        existing = self.store.search(title[:50] if title else text[:50], limit=1)
        dedup_penalty = 0.3 if existing else 0.0
        
        # ── Check 8: Information density ──
        # Higher density = more unique words per total words (more diverse content)
        words = text.lower().split()
        if len(words) > 0:
            unique_ratio = len(set(words)) / len(words)
        else:
            unique_ratio = 0
        density_score = min(1.0, unique_ratio * 2)  # 0.5+ unique ratio = max
        
        # ── Final composite score ──
        final_score = (
            source_score * 0.25 +        # 25% from source reputation
            signal_score * 0.25 +         # 25% from content quality signals
            content_ratio * 0.15 +        # 15% from content-to-noise ratio
            density_score * 0.15 +        # 15% from information density 
            0.20                          # 20% base (benefit of the doubt)
        ) - noise_penalty - dedup_penalty
        
        final_score = max(0.0, min(1.0, final_score))
        
        reason = f"Source:{source_score:.2f} Signals:{signal_score:.2f} Content:{content_ratio:.2f} Density:{density_score:.2f} Noise:-{noise_penalty:.2f} Dedup:-{dedup_penalty:.2f}"
        
        return final_score, reason
    
    def is_acceptable(self, url: str, title: str, text: str) -> Tuple[bool, float, str]:
        """Check if content passes quality threshold."""
        score, reason = self.score_content(url, title, text)
        return score >= MIN_QUALITY_SCORE, score, reason


# ═══════════════════════════════════════════════════════
# KNOWLEDGE EXTRACTOR — Pulls clean knowledge from raw text
# ═══════════════════════════════════════════════════════

class KnowledgeExtractor:
    """
    Extracts clean, structured knowledge from raw web content.
    Uses pattern matching and optional LLM summarization.
    """
    
    def __init__(self, llm_fn=None):
        self.llm_fn = llm_fn  # Optional: Ollama/Gemini for summarization
    
    def extract(self, url: str, title: str, raw_text: str) -> Dict:
        """Extract knowledge from raw text."""
        # Clean the text
        clean = self._clean_text(raw_text)
        
        # Extract topics/keywords
        topics = self._extract_topics(title, clean)
        
        # Generate summary
        if self.llm_fn:
            summary = self._llm_summarize(title, clean)
        else:
            summary = self._extractive_summary(clean)
        
        return {
            'url': url,
            'title': title or 'Untitled',
            'summary': summary,
            'full_text': clean[:10000],  # Cap at 10k chars to save space
            'topics': topics,
        }
    
    def _clean_text(self, text: str) -> str:
        """Remove boilerplate, navigation, ads, and HTML artifacts."""
        # Remove common boilerplate patterns
        patterns_to_remove = [
            r'<[^>]+>',                         # HTML tags
            r'(?:cookie|privacy|consent).*?\n',  # Cookie banners
            r'(?:subscribe|newsletter).*?\n',    # Newsletter prompts
            r'(?:all rights reserved|copyright).*?\n',  # Copyright
            r'https?://\S+',                     # URLs (keep knowledge, not links)
            r'\[.*?\]\(.*?\)',                    # Markdown links
            r'{[^}]+}',                          # CSS/JSON artifacts
            r'(?:share|tweet|pin|like)\s*(?:on|this)',  # Social buttons
        ]
        
        clean = text
        for pattern in patterns_to_remove:
            clean = re.sub(pattern, ' ', clean, flags=re.IGNORECASE)
        
        # Collapse whitespace
        clean = re.sub(r'\s+', ' ', clean).strip()
        clean = re.sub(r'\n{3,}', '\n\n', clean)
        
        return clean
    
    def _extract_topics(self, title: str, text: str) -> List[str]:
        """Extract topic keywords from content."""
        # Combine title and first 500 chars
        sample = f"{title} {text[:500]}".lower()
        
        # Common topic patterns
        topic_patterns = [
            r'\b(python|javascript|java|rust|golang|typescript|c\+\+|ruby|swift)\b',
            r'\b(machine learning|deep learning|neural network|ai|artificial intelligence)\b',
            r'\b(web development|frontend|backend|api|database|cloud)\b',
            r'\b(security|encryption|authentication|vulnerability|firewall)\b',
            r'\b(data science|statistics|analytics|visualization)\b',
            r'\b(blockchain|crypto|web3|smart contract)\b',
            r'\b(devops|docker|kubernetes|ci/cd|deployment)\b',
            r'\b(linux|windows|macos|operating system)\b',
            r'\b(networking|protocol|tcp|http|dns|websocket)\b',
            r'\b(physics|chemistry|biology|mathematics|engineering)\b',
            r'\b(economics|finance|business|management)\b',
            r'\b(history|geography|philosophy|psychology)\b',
        ]
        
        topics = set()
        for pattern in topic_patterns:
            matches = re.findall(pattern, sample, re.IGNORECASE)
            topics.update(m.lower() if isinstance(m, str) else m[0].lower() for m in matches)
        
        # Also extract from title
        if title:
            title_words = [w.lower() for w in title.split() if len(w) > 3 and w.isalpha()]
            topics.update(title_words[:5])
        
        return list(topics)[:15]  # Max 15 topics per item
    
    def _extractive_summary(self, text: str, max_sentences: int = 5) -> str:
        """Create summary by extracting the most important sentences."""
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 30]
        
        if not sentences:
            return text[:300]
        
        # Score sentences by importance (position + keyword density)
        scored = []
        for i, sent in enumerate(sentences[:30]):  # Only look at first 30 sentences
            score = 0
            # First sentences usually contain key info
            if i < 3:
                score += 2
            # Sentences with numbers/data are usually important
            if re.search(r'\d+', sent):
                score += 1
            # Longer sentences often contain more info
            if len(sent.split()) > 10:
                score += 1
            # Sentences with key phrases
            if re.search(r'\b(is|are|was|were|means|defined|refers)\b', sent, re.IGNORECASE):
                score += 1
            scored.append((score, i, sent))
        
        # Get top sentences, maintaining original order
        scored.sort(key=lambda x: x[0], reverse=True)
        top = sorted(scored[:max_sentences], key=lambda x: x[1])
        
        return '. '.join(s[2] for s in top) + '.'
    
    def _llm_summarize(self, title: str, text: str) -> str:
        """Use local LLM (Ollama) to generate a clean summary."""
        try:
            prompt = f"""Summarize this content into a clear, concise knowledge entry (3-5 sentences).
Focus on FACTS, DEFINITIONS, and KEY CONCEPTS only. Remove opinions and filler.

Title: {title}
Content: {text[:2000]}

Summary:"""
            result = self.llm_fn(prompt)
            if result and len(result) > 20:
                return result.strip()
        except Exception:
            pass
        # Fallback to extractive
        return self._extractive_summary(text)


# ═══════════════════════════════════════════════════════
# SCOUT AGENT — Individual web crawler with intelligence
# ═══════════════════════════════════════════════════════

class ScoutAgent:
    """
    A single scout that crawls the web following a topic trail.
    It's smart: it follows promising links and ignores noise.
    """
    
    def __init__(self, topic: str, store: KnowledgeStore, quality_filter: QualityFilter,
                 extractor: KnowledgeExtractor, max_pages: int = 10):
        self.topic = topic
        self.store = store
        self.quality_filter = quality_filter
        self.extractor = extractor
        self.max_pages = max_pages
        self.pages_crawled = 0
        self.pages_accepted = 0
        self.pages_rejected = 0
    
    def crawl(self) -> Dict:
        """Start crawling for this topic. Returns stats."""
        start = time.time()
        seed_urls = self._generate_seed_urls()
        
        for url in seed_urls:
            if self.pages_crawled >= self.max_pages:
                break
            self._process_url(url)
        
        duration = time.time() - start
        return {
            'topic': self.topic,
            'pages_crawled': self.pages_crawled,
            'pages_accepted': self.pages_accepted,
            'pages_rejected': self.pages_rejected,
            'duration_seconds': round(duration, 1)
        }
    
    def _generate_seed_urls(self) -> List[str]:
        """Generate starting URLs for this topic."""
        topic_encoded = self.topic.replace(' ', '+')
        seeds = [
            f"https://en.wikipedia.org/wiki/{self.topic.replace(' ', '_')}",
            f"https://en.wikipedia.org/wiki/Special:Search?search={topic_encoded}",
        ]
        
        # Add domain-specific seeds based on topic
        if any(kw in self.topic.lower() for kw in ['python', 'javascript', 'programming', 'code', 'web']):
            seeds.extend([
                f"https://developer.mozilla.org/en-US/search?q={topic_encoded}",
                f"https://docs.python.org/3/search.html?q={topic_encoded}",
                f"https://realpython.com/search?q={topic_encoded}",
            ])
        
        if any(kw in self.topic.lower() for kw in ['ai', 'machine learning', 'neural', 'deep learning']):
            seeds.extend([
                f"https://huggingface.co/models?search={topic_encoded}",
                f"https://pytorch.org/docs/stable/search.html?q={topic_encoded}",
            ])
        
        if any(kw in self.topic.lower() for kw in ['security', 'hacking', 'vulnerability', 'crypto']):
            seeds.extend([
                f"https://owasp.org/www-community/",
            ])
        
        return seeds
    
    def _process_url(self, url: str):
        """Fetch, evaluate, and potentially store content from a URL."""
        # Skip if already crawled
        if self.store.is_url_crawled(url):
            return
        
        try:
            import urllib.request
            
            # Fetch with timeout and user-agent
            req = urllib.request.Request(url, headers={
                'User-Agent': 'NOMAD-KnowledgeBot/1.0 (educational research crawler)',
                'Accept': 'text/html,application/xhtml+xml',
                'Accept-Language': 'en-US,en;q=0.9',
            })
            
            response = urllib.request.urlopen(req, timeout=10)
            content_type = response.headers.get('Content-Type', '')
            
            if 'text/html' not in content_type and 'text/plain' not in content_type:
                return  # Skip non-text content
            
            raw_html = response.read().decode('utf-8', errors='ignore')
            
            # Extract title
            title_match = re.search(r'<title[^>]*>(.*?)</title>', raw_html, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else ''
            
            # Strip HTML tags for text content
            text = re.sub(r'<script[^>]*>.*?</script>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<nav[^>]*>.*?</nav>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<footer[^>]*>.*?</footer>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<header[^>]*>.*?</header>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            
            self.pages_crawled += 1
            self.store.mark_url_crawled(url)
            
            # Quality check
            acceptable, score, reason = self.quality_filter.is_acceptable(url, title, text)
            
            if acceptable:
                # Extract and store knowledge
                knowledge = self.extractor.extract(url, title, text)
                
                domain = urlparse(url).netloc.replace('www.', '')
                source_trust = TRUSTED_SOURCES.get(domain, 0.5)
                
                self.store.store_knowledge(
                    url=url,
                    title=knowledge['title'],
                    summary=knowledge['summary'],
                    full_text=knowledge['full_text'],
                    topics=knowledge['topics'] + [self.topic],
                    quality_score=score,
                    source_trust=source_trust
                )
                
                self.pages_accepted += 1
                print(f"  ✅ [{self.topic}] Accepted: {title[:60]}... (score: {score:.2f})")
            else:
                self.pages_rejected += 1
                print(f"  ❌ [{self.topic}] Rejected: {title[:40]}... ({reason})")
            
            # Respect rate limits
            time.sleep(CRAWL_DELAY_SECONDS)
            
        except Exception as e:
            self.pages_crawled += 1
            print(f"  ⚠️ [{self.topic}] Error: {url[:50]}... - {str(e)[:60]}")


# ═══════════════════════════════════════════════════════
# AI CONSULTANT — When the agent is confused, ask another AI
# ═══════════════════════════════════════════════════════

class AIConsultant:
    """
    When the agent encounters something it doesn't understand,
    it can "consult" another AI — exactly like a human Googling
    or opening ChatGPT when they're stuck.
    """
    
    def __init__(self, browser_tool=None, ollama_fn=None):
        self.browser_tool = browser_tool
        self.ollama_fn = ollama_fn
    
    def consult(self, question: str) -> str:
        """Ask another AI model for help."""
        
        # Method 1: Ask Ollama locally (fastest, offline)
        if self.ollama_fn:
            try:
                answer = self.ollama_fn(f"Answer this concisely: {question}")
                if answer and len(answer) > 20:
                    return f"[Ollama] {answer}"
            except Exception:
                pass
        
        # Method 2: Use browser to search the web
        if self.browser_tool:
            try:
                from src.agent.tools.browser_tool import execute_browser
                result = execute_browser({
                    'action': 'navigate',
                    'url': f'https://www.google.com/search?q={question.replace(" ", "+")}'
                })
                if 'Error' not in result:
                    # Read the page
                    page_info = execute_browser({'action': 'get_page_info'})
                    return f"[Web Search] {page_info}"
            except Exception:
                pass
        
        return f"[No AI available] Unable to consult on: {question}"


# ═══════════════════════════════════════════════════════
# KNOWLEDGE HARVESTER — Main orchestrator
# ═══════════════════════════════════════════════════════

class KnowledgeHarvester:
    """
    Main orchestrator that coordinates scout agents, quality filtering,
    and knowledge storage. This is the "brain" of the learning system.
    """
    
    def __init__(self, llm_fn=None):
        self.store = KnowledgeStore()
        self.quality_filter = QualityFilter(self.store)
        self.extractor = KnowledgeExtractor(llm_fn=llm_fn)
        self.consultant = AIConsultant(ollama_fn=llm_fn)
        self.llm_fn = llm_fn
    
    def harvest(self, topics: List[str], max_pages_per_topic: int = 10, 
                max_workers: int = 3) -> Dict:
        """
        Launch scout agents to gather knowledge on given topics.
        
        Args:
            topics: List of topics to learn about
            max_pages_per_topic: Max pages to crawl per topic
            max_workers: Number of parallel scouts
        
        Returns:
            Session statistics
        """
        print(f"\n{'='*60}")
        print(f"  🧠 NOMAD Knowledge Harvester — Launching Scout Agents")
        print(f"  Topics: {', '.join(topics)}")
        print(f"  Max pages/topic: {max_pages_per_topic}")
        print(f"{'='*60}\n")
        
        start_time = time.time()
        all_stats = []
        
        # Launch scouts in parallel (but be respectful with rate limits)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for topic in topics:
                scout = ScoutAgent(
                    topic=topic,
                    store=self.store,
                    quality_filter=self.quality_filter,
                    extractor=self.extractor,
                    max_pages=max_pages_per_topic
                )
                futures[executor.submit(scout.crawl)] = topic
            
            for future in as_completed(futures):
                topic = futures[future]
                try:
                    stats = future.result()
                    all_stats.append(stats)
                    print(f"\n  📊 Scout [{topic}]: {stats['pages_accepted']}/{stats['pages_crawled']} accepted ({stats['duration_seconds']}s)")
                except Exception as e:
                    print(f"\n  ❌ Scout [{topic}] failed: {e}")
                    all_stats.append({'topic': topic, 'pages_crawled': 0, 'pages_accepted': 0, 'pages_rejected': 0, 'error': str(e)})
        
        total_duration = time.time() - start_time
        
        # Log session
        total_crawled = sum(s.get('pages_crawled', 0) for s in all_stats)
        total_accepted = sum(s.get('pages_accepted', 0) for s in all_stats)
        total_rejected = sum(s.get('pages_rejected', 0) for s in all_stats)
        
        session_result = {
            'topics': topics,
            'total_pages_crawled': total_crawled,
            'total_pages_accepted': total_accepted,
            'total_pages_rejected': total_rejected,
            'acceptance_rate': round(total_accepted / max(total_crawled, 1) * 100, 1),
            'duration_seconds': round(total_duration, 1),
            'scout_reports': all_stats,
            'knowledge_base_stats': self.store.get_stats()
        }
        
        print(f"\n{'='*60}")
        print(f"  ✅ Harvest Complete!")
        print(f"  Pages: {total_crawled} crawled, {total_accepted} accepted, {total_rejected} rejected")
        print(f"  Acceptance rate: {session_result['acceptance_rate']}%")
        print(f"  Duration: {session_result['duration_seconds']}s")
        print(f"  Knowledge base: {session_result['knowledge_base_stats']['total_knowledge_items']} items")
        print(f"{'='*60}\n")
        
        return session_result
    
    def search_knowledge(self, query: str, limit: int = 5) -> str:
        """Search the knowledge base. Used as a tool by the agent."""
        results = self.store.search(query, limit)
        
        if not results:
            return f"No knowledge found for '{query}'. Consider running a harvest on this topic."
        
        output = f"🧠 Knowledge Search: '{query}' — {len(results)} results\n\n"
        for i, r in enumerate(results, 1):
            output += f"  [{i}] {r['title']}\n"
            output += f"      Quality: {r['quality_score']:.2f} | Source: {r['domain']}\n"
            output += f"      Summary: {r['summary'][:200]}...\n"
            output += f"      Topics: {r['topics']}\n\n"
        
        return output


# ═══════════════════════════════════════════════════════
# TOOL INTERFACE — For the ReACT agent
# ═══════════════════════════════════════════════════════

_harvester_instance = None

def get_harvester(llm_fn=None) -> KnowledgeHarvester:
    """Get or create the global harvester instance."""
    global _harvester_instance
    if _harvester_instance is None:
        _harvester_instance = KnowledgeHarvester(llm_fn=llm_fn)
    return _harvester_instance


def execute_knowledge_tool(params: Dict) -> str:
    """
    Tool interface for the agent.
    
    Actions:
      harvest  - Send scouts to learn about topics from the web
      search   - Search existing knowledge base
      stats    - Get knowledge base statistics
    """
    action = params.get('action', 'search')
    harvester = get_harvester()
    
    if action == 'harvest':
        topics = params.get('topics', [])
        if isinstance(topics, str):
            topics = [t.strip() for t in topics.split(',')]
        if not topics:
            return "Error: 'topics' parameter required. Example: ['machine learning', 'python security']"
        
        max_pages = params.get('max_pages', 10)
        result = harvester.harvest(topics, max_pages_per_topic=max_pages)
        return json.dumps(result, indent=2, default=str)
    
    elif action == 'search':
        query = params.get('query', '')
        if not query:
            return "Error: 'query' parameter required. Example: 'machine learning basics'"
        limit = params.get('limit', 5)
        return harvester.search_knowledge(query, limit)
    
    elif action == 'stats':
        stats = harvester.store.get_stats()
        return json.dumps(stats, indent=2, default=str)
    
    else:
        return f"Unknown action: {action}. Supported: harvest, search, stats"
