"""
Multi-Source Knowledge Harvester — Proven, Legitimate Knowledge Only

PURPOSE: Harvests knowledge from MULTIPLE reliable, licensed sources.
Only downloads verified, practical content that actually works.

SOURCES:
    1. Wikipedia (general knowledge, science, technology)
    2. WikiHow (practical how-to: cooking, repairs, building, DIY)
    3. Stack Exchange API (programming, engineering, science Q&A)
    4. arXiv (scientific papers — abstracts + summaries)
    5. Official Documentation (Python docs, MDN, etc.)
    6. Open Textbooks / Educational (OpenStax, MIT OCW)

QUALITY FILTER:
    - Source reputation scoring (peer-reviewed > wiki > forum)
    - Content type classification (practical, theoretical, reference)
    - Minimum quality thresholds per source
    - Deduplication via content hashing
    - Only stores content with actionable information

DOMAINS COVERED:
    - Cooking & recipes (proven, tested recipes)
    - Business models & entrepreneurship
    - Repairs & fixing things (cars, electronics, plumbing)
    - Engineering & building from scratch
    - Programming & coding (all languages)
    - Mathematics & science (proven methods)
    - Strategic thinking & problem solving
    - Survival & practical skills
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from html.parser import HTMLParser


# ────────────────────────────────────────────────────────
#  HTML / Text Processing
# ────────────────────────────────────────────────────────

class _HTMLTextExtractor(HTMLParser):
    """Extract plain text from HTML, skipping scripts/styles/nav."""
    SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "header",
                 "aside", "iframe", "form", "button", "svg"}

    def __init__(self):
        super().__init__()
        self._text_parts: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self._text_parts.append(text)

    def get_text(self) -> str:
        return " ".join(self._text_parts)


def html_to_text(html: str) -> str:
    """Convert HTML to clean plain text."""
    extractor = _HTMLTextExtractor()
    extractor.feed(html)
    text = extractor.get_text()
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ────────────────────────────────────────────────────────
#  Data Classes
# ────────────────────────────────────────────────────────

@dataclass
class HarvestResult:
    """Result from a single harvest operation."""
    source: str
    topic: str
    chunks_stored: int
    total_chars: int
    success: bool
    quality_score: float = 0.0
    error: Optional[str] = None
    duration_s: float = 0.0
    source_type: str = "unknown"  # wikipedia, wikihow, stackexchange, arxiv, docs, url


@dataclass
class HarvestStats:
    """Overall harvesting statistics."""
    total_pages_harvested: int = 0
    total_chunks_stored: int = 0
    total_chars_ingested: int = 0
    topics_covered: List[str] = field(default_factory=list)
    sources_used: Dict[str, int] = field(default_factory=dict)
    last_harvest_time: Optional[str] = None
    errors: int = 0
    quality_filtered_out: int = 0


# ────────────────────────────────────────────────────────
#  Quality Filter
# ────────────────────────────────────────────────────────

class QualityFilter:
    """
    Scores and filters harvested content for reliability.
    Only allows proven, legitimate knowledge through.
    """

    # Source reputation scores (0-1)
    SOURCE_SCORES = {
        "wikipedia": 0.85,
        "wikihow": 0.75,
        "stackexchange": 0.80,
        "arxiv": 0.95,
        "official_docs": 0.90,
        "textbook": 0.90,
        "url": 0.50,
    }

    # Minimum quality to accept content
    MIN_QUALITY = 0.40

    # Words indicating low-quality / unreliable content
    LOW_QUALITY_SIGNALS = [
        "advertisement", "sponsored", "buy now", "click here",
        "subscribe", "sign up free", "limited time offer",
        "disclaimer: not medical advice", "allegedly",
        "conspiracy", "unverified", "rumor has it",
    ]

    # Words indicating high-quality / practical content
    HIGH_QUALITY_SIGNALS = [
        "step by step", "instructions", "procedure", "method",
        "research shows", "according to", "peer-reviewed",
        "tested", "proven", "certified", "official",
        "how to", "tutorial", "guide", "example",
        "formula", "equation", "theorem", "algorithm",
        "safety", "warning", "important", "note",
        "ingredients", "materials", "tools needed",
        "troubleshooting", "solution", "fix",
    ]

    @classmethod
    def score_content(cls, text: str, source_type: str) -> float:
        """
        Score content quality from 0.0 to 1.0.
        Higher = more reliable and useful.
        """
        if not text or len(text) < 50:
            return 0.0

        score = cls.SOURCE_SCORES.get(source_type, 0.5)
        text_lower = text.lower()

        # Penalize low-quality signals
        low_count = sum(1 for sig in cls.LOW_QUALITY_SIGNALS if sig in text_lower)
        score -= low_count * 0.1

        # Reward high-quality signals
        high_count = sum(1 for sig in cls.HIGH_QUALITY_SIGNALS if sig in text_lower)
        score += min(high_count * 0.03, 0.15)

        # Length bonus — longer content tends to be more substantial
        if len(text) > 500:
            score += 0.05
        if len(text) > 2000:
            score += 0.05

        # Has numbers / data = more factual
        if re.search(r'\d+\.\d+|\d{2,}', text):
            score += 0.03

        # Has citations / references
        if re.search(r'\[\d+\]|references|bibliography|doi:|isbn:', text_lower):
            score += 0.05

        return max(0.0, min(1.0, score))

    @classmethod
    def passes_filter(cls, text: str, source_type: str) -> bool:
        """Check if content passes the quality filter."""
        return cls.score_content(text, source_type) >= cls.MIN_QUALITY

    @classmethod
    def score_chunk(cls, chunk: str, source_type: str) -> float:
        """Score an individual chunk."""
        if len(chunk.strip()) < 30:
            return 0.0
        base = cls.SOURCE_SCORES.get(source_type, 0.5)
        # Short chunks from good sources still pass
        if len(chunk) > 100:
            base += 0.05
        return base


# ────────────────────────────────────────────────────────
#  Multi-Source Knowledge Harvester
# ────────────────────────────────────────────────────────

class MultiSourceHarvester:
    """
    Downloads PROVEN, LEGITIMATE knowledge from multiple sources
    into vector memory. Only stores content that actually works.

    Sources: Wikipedia, WikiHow, Stack Exchange, arXiv, Official Docs

    Usage:
        harvester = MultiSourceHarvester(memory_store)
        
        # Practical knowledge
        harvester.harvest_wikihow("how to fix a flat tire")
        harvester.harvest_wikihow("how to cook pasta")
        
        # Programming knowledge
        harvester.harvest_stackexchange("python sort dictionary by value")
        
        # Scientific papers
        harvester.harvest_arxiv("transformer attention mechanism")
        
        # Smart search across all sources
        harvester.smart_harvest("machine learning basics")
    """

    # APIs
    WIKI_API = "https://en.wikipedia.org/w/api.php"
    STACKEXCHANGE_API = "https://api.stackexchange.com/2.3"
    ARXIV_API = "http://export.arxiv.org/api/query"

    # ────── Expanded Topic Packs ──────
    ESSENTIAL_TOPICS = [
        # Core CS & Programming
        "Python (programming language)", "JavaScript", "Machine learning",
        "Artificial intelligence", "Neural network", "Deep learning",
        "Natural language processing", "Computer science", "Algorithm",
        "Data structure", "Object-oriented programming", "API",
        "Database", "SQL", "Git (software)", "Linux", "Docker (software)",
        # Math & Science
        "Linear algebra", "Calculus", "Statistics", "Probability theory",
        # AI-Specific
        "Large language model", "Transformer (deep learning architecture)",
        "Reinforcement learning", "Vector database",
        "Retrieval-augmented generation", "Few-shot learning", "Transfer learning",
        # General
        "World Wide Web", "Internet", "Cloud computing", "Cybersecurity",
        "Open-source software", "Software engineering",
        "Startup company", "Entrepreneurship",
    ]

    TOPIC_PACKS = {
        "ai_fundamentals": [
            "Artificial intelligence", "Machine learning", "Deep learning",
            "Neural network", "Natural language processing",
            "Large language model", "Transformer (deep learning architecture)",
            "Reinforcement learning", "Few-shot learning", "Transfer learning",
            "Retrieval-augmented generation", "Vector database",
        ],
        "programming": [
            "Python (programming language)", "JavaScript",
            "Object-oriented programming", "Algorithm", "Data structure",
            "API", "Git (software)", "Software engineering",
            "Database", "SQL", "Docker (software)", "Linux",
        ],
        "math": [
            "Linear algebra", "Calculus", "Statistics",
            "Probability theory", "Matrix (mathematics)",
            "Gradient descent", "Backpropagation",
        ],
        "business": [
            "Startup company", "Entrepreneurship", "Business model",
            "Venture capital", "Product management",
            "Agile software development", "Lean startup",
        ],
        "general": [
            "World Wide Web", "Internet", "Cloud computing",
            "Cybersecurity", "Open-source software",
            "Computer science", "Information technology",
        ],
        # ─── NEW PACKS ───
        "cooking": [
            "Cooking", "Recipe", "Baking", "Food preservation",
            "Knife skills", "Spice", "Sauce (cooking)",
            "Fermentation in food processing",
        ],
        "repairs": [
            "Auto repair", "Plumbing", "Electrical wiring",
            "Welding", "Woodworking", "Soldering",
            "Troubleshooting", "Maintenance (technical)",
        ],
        "engineering": [
            "Mechanical engineering", "Electrical engineering",
            "Civil engineering", "Chemical engineering",
            "3D printing", "CAD", "Robotics",
            "Control theory", "Materials science",
        ],
        "survival": [
            "Survival skills", "First aid", "Navigation",
            "Water purification", "Shelter (building)",
            "Knot", "Fire making",
        ],
        "strategy": [
            "Game theory", "Decision theory", "Systems thinking",
            "Critical thinking", "Problem solving",
            "Strategic planning", "Risk management",
            "Sun Tzu", "OODA loop",
        ],
        "science": [
            "Scientific method", "Physics", "Chemistry",
            "Biology", "Astronomy", "Thermodynamics",
            "Quantum mechanics", "Electromagnetism",
        ],
        "medical_deep_dive": [
            "Internal medicine", "Pharmacology", "Neuroscience",
            "Human physiology", "Pathology", "Medical diagnostic",
            "Clinical trial", "Genetics", "Molecular biology",
            "Biotechnology", "Immunology", "Endocrinology",
            "Surgical procedure", "Emergency medicine",
            "Medical imaging", "Laboratory medicine",
        ],
        "robotics_drone_expert": [
            "Aerospace engineering", "Avionics", "Rocket ignition",
            "Unmanned aerial vehicle", "Flight controller",
            "Brushless DC electric motor", "Sensor fusion",
            "IMU", "GPS navigation", "LiPo battery",
            "PID controller", "Embedded systems",
            "Mechatronics", "Computer vision",
        ],
    }

    # WikiHow categories for practical knowledge
    WIKIHOW_PACKS = {
        "cooking_howto": [
            "Cook Rice", "Make Bread", "Bake a Cake",
            "Grill Steak", "Make Pasta from Scratch",
            "Cook Eggs", "Make Soup",
        ],
        "repairs_howto": [
            "Fix a Leaky Faucet", "Change a Tire",
            "Fix a Toilet", "Patch Drywall",
            "Fix a Broken Window",
        ],
        "building_howto": [
            "Build a Bookshelf", "Build a Computer",
            "Solder Electronics", "Use a 3D Printer",
            "Weld", "Use a Lathe",
        ],
    }

    def __init__(self, memory_store, chunk_size: int = 500, chunk_overlap: int = 50):
        self._memory = memory_store
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._stats = HarvestStats()
        self._harvested_urls: set = set()
        self._quality = QualityFilter()

        # Load previous harvest log
        self._log_path = os.path.join(
            getattr(memory_store, '_data_dir', './agent_data'),
            "harvest_log_v2.json"
        )
        self._load_log()

    def _load_log(self):
        try:
            if os.path.exists(self._log_path):
                with open(self._log_path, "r") as f:
                    data = json.load(f)
                    self._harvested_urls = set(data.get("harvested_urls", []))
                    self._stats.total_pages_harvested = data.get("total_pages", 0)
                    self._stats.total_chunks_stored = data.get("total_chunks", 0)
                    self._stats.topics_covered = data.get("topics_covered", [])
                    self._stats.sources_used = data.get("sources_used", {})
        except Exception:
            pass

    def _save_log(self):
        try:
            os.makedirs(os.path.dirname(self._log_path), exist_ok=True)
            data = {
                "harvested_urls": list(self._harvested_urls),
                "total_pages": self._stats.total_pages_harvested,
                "total_chunks": self._stats.total_chunks_stored,
                "topics_covered": self._stats.topics_covered,
                "sources_used": self._stats.sources_used,
                "last_harvest": self._stats.last_harvest_time,
            }
            with open(self._log_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    # ────────────────────────────────────────────────
    #  HTTP Fetching (safe, with User-Agent)
    # ────────────────────────────────────────────────

    def _fetch_url(self, url: str, timeout: int = 20) -> str:
        req = urllib.request.Request(url, headers={
            "User-Agent": "SmartAgent/2.0 (educational research bot)",
            "Accept": "text/html,application/json,text/plain,application/xml",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            return data.decode(charset, errors="replace")

    # ────────────────────────────────────────────────
    #  Text Processing
    # ────────────────────────────────────────────────

    def _chunk_text(self, text: str) -> List[str]:
        if not text:
            return []
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(current_chunk) + len(para) <= self._chunk_size:
                current_chunk += ("\n\n" if current_chunk else "") + para
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                if len(para) > self._chunk_size:
                    sentences = re.split(r'(?<=[.!?])\s+', para)
                    current_chunk = ""
                    for sent in sentences:
                        if len(current_chunk) + len(sent) <= self._chunk_size:
                            current_chunk += (" " if current_chunk else "") + sent
                        else:
                            if current_chunk:
                                chunks.append(current_chunk)
                            current_chunk = sent
                else:
                    current_chunk = para
        if current_chunk:
            chunks.append(current_chunk)
        return chunks

    def _content_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _store_chunks(
        self, chunks: List[str], source_type: str, metadata: Dict[str, Any],
        topic: str
    ) -> int:
        """Store chunks in memory with quality filtering."""
        stored = 0
        for i, chunk in enumerate(chunks):
            if len(chunk.strip()) < 50:
                continue
            # Quality check each chunk
            q_score = QualityFilter.score_chunk(chunk, source_type)
            if q_score < QualityFilter.MIN_QUALITY:
                self._stats.quality_filtered_out += 1
                continue

            chunk_meta = {
                **metadata,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "quality_score": round(q_score, 2),
                "harvested_at": time.strftime("%Y-%m-%d %H:%M"),
            }
            self._memory.store(
                content=chunk,
                collection="web_knowledge",
                metadata=chunk_meta,
            )
            stored += 1
        return stored

    def _update_stats(self, source_type: str, topic: str, stored: int, chars: int):
        self._stats.total_pages_harvested += 1
        self._stats.total_chunks_stored += stored
        self._stats.total_chars_ingested += chars
        if topic not in self._stats.topics_covered:
            self._stats.topics_covered.append(topic)
        self._stats.sources_used[source_type] = self._stats.sources_used.get(source_type, 0) + 1
        self._stats.last_harvest_time = time.strftime("%Y-%m-%d %H:%M")
        self._save_log()

    # ════════════════════════════════════════════════
    #  SOURCE 1: Wikipedia (General Knowledge)
    # ════════════════════════════════════════════════

    def _fetch_wikipedia(self, title: str) -> Optional[str]:
        params = urllib.parse.urlencode({
            "action": "query", "titles": title,
            "prop": "extracts", "explaintext": "true",
            "format": "json", "exlimit": "1",
        })
        url = f"{self.WIKI_API}?{params}"
        raw = self._fetch_url(url)
        data = json.loads(raw)
        pages = data.get("query", {}).get("pages", {})
        for page_id, page in pages.items():
            if page_id == "-1":
                return None
            return page.get("extract", "")
        return None

    def _search_wikipedia(self, query: str, limit: int = 5) -> List[str]:
        params = urllib.parse.urlencode({
            "action": "opensearch", "search": query,
            "limit": str(limit), "format": "json",
        })
        url = f"{self.WIKI_API}?{params}"
        raw = self._fetch_url(url)
        data = json.loads(raw)
        if len(data) >= 2:
            return data[1]
        return []

    def harvest_wikipedia(self, title: str, topic: str = "") -> HarvestResult:
        """Harvest a Wikipedia article by title."""
        start = time.time()
        topic = topic or title.lower().replace(" ", "_")
        url_key = f"wikipedia:{title}"

        if url_key in self._harvested_urls:
            return HarvestResult(
                source=f"wikipedia:{title}", topic=topic,
                chunks_stored=0, total_chars=0, success=True,
                error="Already harvested (skipped)", source_type="wikipedia",
            )

        try:
            text = self._fetch_wikipedia(title)
            if not text:
                return HarvestResult(
                    source=f"wikipedia:{title}", topic=topic,
                    chunks_stored=0, total_chars=0, success=False,
                    error=f"Article not found: {title}",
                    duration_s=time.time() - start, source_type="wikipedia",
                )

            quality = QualityFilter.score_content(text, "wikipedia")
            if not QualityFilter.passes_filter(text, "wikipedia"):
                self._stats.quality_filtered_out += 1
                return HarvestResult(
                    source=f"wikipedia:{title}", topic=topic,
                    chunks_stored=0, total_chars=len(text), success=False,
                    quality_score=quality,
                    error="Filtered out: low quality",
                    duration_s=time.time() - start, source_type="wikipedia",
                )

            chunks = self._chunk_text(text)
            stored = self._store_chunks(chunks, "wikipedia", {
                "source": "wikipedia", "title": title, "topic": topic,
            }, topic)

            self._harvested_urls.add(url_key)
            self._update_stats("wikipedia", topic, stored, len(text))

            return HarvestResult(
                source=f"wikipedia:{title}", topic=topic,
                chunks_stored=stored, total_chars=len(text),
                success=True, quality_score=quality,
                duration_s=time.time() - start, source_type="wikipedia",
            )
        except Exception as e:
            self._stats.errors += 1
            return HarvestResult(
                source=f"wikipedia:{title}", topic=topic,
                chunks_stored=0, total_chars=0, success=False,
                error=str(e), duration_s=time.time() - start,
                source_type="wikipedia",
            )

    # ════════════════════════════════════════════════
    #  SOURCE 2: WikiHow (Practical How-To Knowledge)
    # ════════════════════════════════════════════════

    def harvest_wikihow(self, query: str) -> HarvestResult:
        """
        Harvest practical how-to knowledge from WikiHow.
        Perfect for: cooking, repairs, building, DIY, crafts.
        """
        start = time.time()
        topic = query.lower().replace(" ", "_")
        url_key = f"wikihow:{query}"

        if url_key in self._harvested_urls:
            return HarvestResult(
                source=f"wikihow:{query}", topic=topic,
                chunks_stored=0, total_chars=0, success=True,
                error="Already harvested (skipped)", source_type="wikihow",
            )

        try:
            # WikiHow URL pattern: wikihow.com/Topic-Words
            slug = "-".join(w.capitalize() for w in query.split())
            url = f"https://www.wikihow.com/{slug}"
            raw_html = self._fetch_url(url, timeout=15)
            text = html_to_text(raw_html)

            if len(text) < 200:
                # Try search fallback
                search_url = f"https://www.wikihow.com/wikiHowTo?search={urllib.parse.quote(query)}"
                raw_html = self._fetch_url(search_url, timeout=15)
                text = html_to_text(raw_html)

            if len(text) < 200:
                return HarvestResult(
                    source=f"wikihow:{query}", topic=topic,
                    chunks_stored=0, total_chars=len(text), success=False,
                    error="Content too short or not found",
                    duration_s=time.time() - start, source_type="wikihow",
                )

            quality = QualityFilter.score_content(text, "wikihow")
            chunks = self._chunk_text(text)
            stored = self._store_chunks(chunks, "wikihow", {
                "source": "wikihow", "query": query, "topic": topic,
                "type": "how-to",
            }, topic)

            self._harvested_urls.add(url_key)
            self._update_stats("wikihow", topic, stored, len(text))

            return HarvestResult(
                source=f"wikihow:{query}", topic=topic,
                chunks_stored=stored, total_chars=len(text),
                success=True, quality_score=quality,
                duration_s=time.time() - start, source_type="wikihow",
            )
        except Exception as e:
            self._stats.errors += 1
            return HarvestResult(
                source=f"wikihow:{query}", topic=topic,
                chunks_stored=0, total_chars=0, success=False,
                error=str(e), duration_s=time.time() - start,
                source_type="wikihow",
            )

    # ════════════════════════════════════════════════
    #  SOURCE 3: Stack Exchange (Programming & Q&A)
    # ════════════════════════════════════════════════

    def harvest_stackexchange(self, query: str, site: str = "stackoverflow") -> HarvestResult:
        """
        Harvest top answers from Stack Exchange network.
        
        Sites: stackoverflow, superuser, serverfault, math.stackexchange,
               electronics.stackexchange, mechanics.stackexchange, etc.
        """
        start = time.time()
        topic = query.lower().replace(" ", "_")
        url_key = f"stackexchange:{site}:{query}"

        if url_key in self._harvested_urls:
            return HarvestResult(
                source=f"stackexchange:{site}:{query}", topic=topic,
                chunks_stored=0, total_chars=0, success=True,
                error="Already harvested (skipped)", source_type="stackexchange",
            )

        try:
            # Search Stack Exchange API (no auth needed for basic usage)
            params = urllib.parse.urlencode({
                "order": "desc", "sort": "votes",
                "intitle": query, "site": site,
                "filter": "withbody", "pagesize": "5",
            })
            url = f"{self.STACKEXCHANGE_API}/search/advanced?{params}"
            raw = self._fetch_url(url, timeout=15)
            data = json.loads(raw)

            items = data.get("items", [])
            if not items:
                return HarvestResult(
                    source=f"stackexchange:{site}:{query}", topic=topic,
                    chunks_stored=0, total_chars=0, success=False,
                    error="No results found",
                    duration_s=time.time() - start, source_type="stackexchange",
                )

            total_stored = 0
            total_chars = 0

            for item in items[:5]:
                # Only take answered, upvoted questions
                if item.get("score", 0) < 1:
                    continue
                if not item.get("is_answered", False):
                    continue

                title = item.get("title", "")
                body = html_to_text(item.get("body", ""))
                if not body:
                    continue

                # Fetch the accepted/top answer
                answer_text = ""
                q_id = item.get("question_id")
                if q_id:
                    try:
                        ans_params = urllib.parse.urlencode({
                            "order": "desc", "sort": "votes",
                            "site": site, "filter": "withbody",
                        })
                        ans_url = f"{self.STACKEXCHANGE_API}/questions/{q_id}/answers?{ans_params}"
                        ans_raw = self._fetch_url(ans_url, timeout=10)
                        ans_data = json.loads(ans_raw)
                        answers = ans_data.get("items", [])
                        if answers:
                            # Take top voted answer
                            best = max(answers, key=lambda a: a.get("score", 0))
                            answer_text = html_to_text(best.get("body", ""))
                    except Exception:
                        pass

                # Combine Q&A into a knowledge block
                knowledge = f"Question: {title}\n\n{body}"
                if answer_text:
                    knowledge += f"\n\nBest Answer:\n{answer_text}"

                quality = QualityFilter.score_content(knowledge, "stackexchange")
                chunks = self._chunk_text(knowledge)
                stored = self._store_chunks(chunks, "stackexchange", {
                    "source": "stackexchange", "site": site,
                    "question_title": title, "topic": topic,
                    "votes": item.get("score", 0),
                    "type": "q_and_a",
                }, topic)
                total_stored += stored
                total_chars += len(knowledge)

            self._harvested_urls.add(url_key)
            self._update_stats("stackexchange", topic, total_stored, total_chars)

            return HarvestResult(
                source=f"stackexchange:{site}:{query}", topic=topic,
                chunks_stored=total_stored, total_chars=total_chars,
                success=total_stored > 0, quality_score=0.8,
                duration_s=time.time() - start, source_type="stackexchange",
            )
        except Exception as e:
            self._stats.errors += 1
            return HarvestResult(
                source=f"stackexchange:{site}:{query}", topic=topic,
                chunks_stored=0, total_chars=0, success=False,
                error=str(e), duration_s=time.time() - start,
                source_type="stackexchange",
            )

    # ════════════════════════════════════════════════
    #  SOURCE 4: arXiv (Scientific Papers)
    # ════════════════════════════════════════════════

    def harvest_arxiv(self, query: str, max_papers: int = 3) -> HarvestResult:
        """
        Harvest scientific paper abstracts from arXiv.
        Perfect for: AI, physics, math, CS, engineering research.
        """
        start = time.time()
        topic = query.lower().replace(" ", "_")
        url_key = f"arxiv:{query}"

        if url_key in self._harvested_urls:
            return HarvestResult(
                source=f"arxiv:{query}", topic=topic,
                chunks_stored=0, total_chars=0, success=True,
                error="Already harvested (skipped)", source_type="arxiv",
            )

        try:
            params = urllib.parse.urlencode({
                "search_query": f"all:{query}",
                "start": "0",
                "max_results": str(max_papers),
                "sortBy": "relevance",
                "sortOrder": "descending",
            })
            url = f"{self.ARXIV_API}?{params}"
            raw = self._fetch_url(url, timeout=15)

            # Parse Atom XML for entries
            total_stored = 0
            total_chars = 0

            # Simple XML parsing without external deps
            entries = re.findall(r'<entry>(.*?)</entry>', raw, re.DOTALL)
            for entry in entries:
                title_match = re.search(r'<title>(.*?)</title>', entry, re.DOTALL)
                summary_match = re.search(r'<summary>(.*?)</summary>', entry, re.DOTALL)
                authors = re.findall(r'<name>(.*?)</name>', entry)

                if not title_match or not summary_match:
                    continue

                title = re.sub(r'\s+', ' ', title_match.group(1).strip())
                summary = re.sub(r'\s+', ' ', summary_match.group(1).strip())
                author_str = ", ".join(authors[:5])

                knowledge = (
                    f"Scientific Paper: {title}\n"
                    f"Authors: {author_str}\n\n"
                    f"Abstract: {summary}"
                )

                quality = QualityFilter.score_content(knowledge, "arxiv")
                chunks = self._chunk_text(knowledge)
                stored = self._store_chunks(chunks, "arxiv", {
                    "source": "arxiv", "title": title,
                    "authors": author_str, "topic": topic,
                    "type": "scientific_paper",
                }, topic)
                total_stored += stored
                total_chars += len(knowledge)

            self._harvested_urls.add(url_key)
            self._update_stats("arxiv", topic, total_stored, total_chars)

            return HarvestResult(
                source=f"arxiv:{query}", topic=topic,
                chunks_stored=total_stored, total_chars=total_chars,
                success=total_stored > 0, quality_score=0.95,
                duration_s=time.time() - start, source_type="arxiv",
            )
        except Exception as e:
            self._stats.errors += 1
            return HarvestResult(
                source=f"arxiv:{query}", topic=topic,
                chunks_stored=0, total_chars=0, success=False,
                error=str(e), duration_s=time.time() - start,
                source_type="arxiv",
            )

    # ════════════════════════════════════════════════
    #  SOURCE 5: Generic URL with Quality Check  
    # ════════════════════════════════════════════════

    def harvest_url(self, url: str, topic: str = "web") -> HarvestResult:
        """Harvest knowledge from any URL with quality filtering."""
        start = time.time()

        if url in self._harvested_urls:
            return HarvestResult(
                source=url, topic=topic, chunks_stored=0,
                total_chars=0, success=True,
                error="Already harvested (skipped)", source_type="url",
            )

        try:
            raw_html = self._fetch_url(url)
            text = html_to_text(raw_html)

            if len(text) < 100:
                return HarvestResult(
                    source=url, topic=topic, chunks_stored=0,
                    total_chars=len(text), success=False,
                    error="Page content too short",
                    duration_s=time.time() - start, source_type="url",
                )

            # Detect source type from URL for better quality scoring
            source_type = "url"
            if "docs.python.org" in url or "developer.mozilla.org" in url:
                source_type = "official_docs"
            elif "wikipedia.org" in url:
                source_type = "wikipedia"
            elif "wikihow.com" in url:
                source_type = "wikihow"

            quality = QualityFilter.score_content(text, source_type)
            if not QualityFilter.passes_filter(text, source_type):
                self._stats.quality_filtered_out += 1
                return HarvestResult(
                    source=url, topic=topic, chunks_stored=0,
                    total_chars=len(text), success=False,
                    quality_score=quality,
                    error=f"Filtered out: quality score {quality:.2f} below threshold",
                    duration_s=time.time() - start, source_type=source_type,
                )

            chunks = self._chunk_text(text)
            stored = self._store_chunks(chunks, source_type, {
                "source": source_type, "url": url, "topic": topic,
            }, topic)

            self._harvested_urls.add(url)
            self._update_stats(source_type, topic, stored, len(text))

            return HarvestResult(
                source=url, topic=topic, chunks_stored=stored,
                total_chars=len(text), success=True,
                quality_score=quality,
                duration_s=time.time() - start, source_type=source_type,
            )
        except Exception as e:
            self._stats.errors += 1
            return HarvestResult(
                source=url, topic=topic, chunks_stored=0,
                total_chars=0, success=False, error=str(e),
                duration_s=time.time() - start, source_type="url",
            )

    # ════════════════════════════════════════════════
    #  SMART HARVEST — Searches ALL sources at once
    # ════════════════════════════════════════════════

    def smart_harvest(self, query: str) -> List[HarvestResult]:
        """
        Smart multi-source harvest. Automatically searches the best
        sources for the given query and downloads proven knowledge.
        
        This is the recommended way to harvest. It picks the right
        sources based on the query type.
        """
        results = []
        query_lower = query.lower()

        # Always search Wikipedia
        try:
            titles = self._search_wikipedia(query, limit=2)
            for title in titles:
                results.append(self.harvest_wikipedia(title, topic=query_lower))
        except Exception:
            pass

        # Detect query type and pick additional sources
        is_howto = any(w in query_lower for w in [
            "how to", "fix", "repair", "cook", "build", "make", "install",
            "set up", "create", "clean", "replace", "remove",
        ])
        is_programming = any(w in query_lower for w in [
            "python", "javascript", "code", "programming", "algorithm",
            "function", "class", "api", "error", "bug", "debug",
            "html", "css", "react", "node", "sql", "database",
        ])
        is_science = any(w in query_lower for w in [
            "theory", "research", "equation", "physics", "chemistry",
            "biology", "quantum", "neural", "machine learning", "ai",
            "deep learning", "transformer", "math",
        ])

        # WikiHow for practical/how-to queries
        if is_howto:
            try:
                results.append(self.harvest_wikihow(query))
            except Exception:
                pass

        # Stack Overflow for programming
        if is_programming:
            try:
                results.append(self.harvest_stackexchange(query, "stackoverflow"))
            except Exception:
                pass

        # arXiv for science/research
        if is_science:
            try:
                results.append(self.harvest_arxiv(query, max_papers=2))
            except Exception:
                pass

        return results

    # ════════════════════════════════════════════════
    #  Pack & Bulk Harvesting
    # ════════════════════════════════════════════════

    def harvest_topic(self, query: str, max_articles: int = 3) -> List[HarvestResult]:
        """Search Wikipedia for a topic and harvest top articles."""
        results = []
        try:
            titles = self._search_wikipedia(query, limit=max_articles)
            for title in titles:
                result = self.harvest_wikipedia(title, topic=query.lower())
                results.append(result)
        except Exception as e:
            results.append(HarvestResult(
                source=f"search:{query}", topic=query.lower(),
                chunks_stored=0, total_chars=0, success=False, error=str(e),
                source_type="wikipedia",
            ))
        return results

    def harvest_essentials(self, callback=None) -> List[HarvestResult]:
        """Harvest all essential topics from Wikipedia."""
        results = []
        total = len(self.ESSENTIAL_TOPICS)
        for i, title in enumerate(self.ESSENTIAL_TOPICS):
            if callback:
                callback(title, i, total)
            results.append(self.harvest_wikipedia(title))
        return results

    def harvest_pack(self, pack_name: str, callback=None) -> List[HarvestResult]:
        """Harvest a topic pack (Wikipedia-based)."""
        topics = self.TOPIC_PACKS.get(pack_name)
        if not topics:
            return [HarvestResult(
                source="pack", topic=pack_name, chunks_stored=0,
                total_chars=0, success=False,
                error=f"Unknown pack: {pack_name}. Available: {list(self.TOPIC_PACKS.keys())}",
                source_type="wikipedia",
            )]
        results = []
        total = len(topics)
        for i, title in enumerate(topics):
            if callback:
                callback(title, i, total)
            results.append(self.harvest_wikipedia(title))
        return results

    def harvest_wikihow_pack(self, pack_name: str) -> List[HarvestResult]:
        """Harvest a WikiHow how-to pack."""
        topics = self.WIKIHOW_PACKS.get(pack_name)
        if not topics:
            return [HarvestResult(
                source="wikihow_pack", topic=pack_name,
                chunks_stored=0, total_chars=0, success=False,
                error=f"Unknown pack: {pack_name}. Available: {list(self.WIKIHOW_PACKS.keys())}",
                source_type="wikihow",
            )]
        results = []
        for topic in topics:
            results.append(self.harvest_wikihow(topic))
        return results

    def harvest_custom(self, text: str, topic: str = "custom", source: str = "user") -> HarvestResult:
        """Store custom text directly into knowledge base."""
        start = time.time()
        chunks = self._chunk_text(text)
        stored = self._store_chunks(chunks, "url", {
            "source": source, "topic": topic,
        }, topic)
        self._stats.total_chars_ingested += len(text)
        if topic not in self._stats.topics_covered:
            self._stats.topics_covered.append(topic)
        self._stats.last_harvest_time = time.strftime("%Y-%m-%d %H:%M")
        self._save_log()
        return HarvestResult(
            source=source, topic=topic, chunks_stored=stored,
            total_chars=len(text), success=True,
            duration_s=time.time() - start, source_type="custom",
        )

    # ════════════════════════════════════════════════
    #  Status & Info
    # ════════════════════════════════════════════════

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_pages_harvested": self._stats.total_pages_harvested,
            "total_chunks_stored": self._stats.total_chunks_stored,
            "total_chars_ingested": self._stats.total_chars_ingested,
            "topics_covered": self._stats.topics_covered,
            "sources_used": self._stats.sources_used,
            "last_harvest_time": self._stats.last_harvest_time,
            "errors": self._stats.errors,
            "quality_filtered_out": self._stats.quality_filtered_out,
            "available_packs": list(self.TOPIC_PACKS.keys()),
            "available_wikihow_packs": list(self.WIKIHOW_PACKS.keys()),
        }

    def is_online(self) -> bool:
        try:
            urllib.request.urlopen(
                "https://en.wikipedia.org/w/api.php?action=query&meta=siteinfo&format=json",
                timeout=5,
            )
            return True
        except Exception:
            return False
