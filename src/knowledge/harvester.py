"""
Knowledge Harvester — Download the Internet Into Your Memory

PURPOSE: When online, actively harvest knowledge from the internet
and store it in vector memory. When offline, your agent has a "brain
full of knowledge" to work with — no internet needed.

SOURCES:
    - Wikipedia (general knowledge, science, technology, history)
    - Programming docs (Python, JS, APIs)
    - Custom URLs you provide
    - RSS/news feeds for current events

HOW IT WORKS:
    1. Fetch content from URLs or topic searches
    2. Clean and chunk the text
    3. Store chunks in vector memory (web_knowledge collection)
    4. When offline, semantic search finds relevant chunks

STORAGE:
    - All knowledge goes into "web_knowledge" collection in ChromaDB
    - Each chunk is ~300-500 tokens with metadata (source, topic, timestamp)
    - Knowledge persists across restarts (ChromaDB is on disk)
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
#  Text extractor from HTML
# ────────────────────────────────────────────────────────

class _HTMLTextExtractor(HTMLParser):
    """Extract plain text from HTML, skipping scripts/styles."""

    SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "header", "aside"}

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
    # Clean up whitespace
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
    error: Optional[str] = None
    duration_s: float = 0.0


@dataclass
class HarvestStats:
    """Overall harvesting statistics."""
    total_pages_harvested: int = 0
    total_chunks_stored: int = 0
    total_chars_ingested: int = 0
    topics_covered: List[str] = field(default_factory=list)
    last_harvest_time: Optional[str] = None
    errors: int = 0


# ────────────────────────────────────────────────────────
#  Knowledge Harvester
# ────────────────────────────────────────────────────────

class KnowledgeHarvester:
    """
    Downloads knowledge from the internet into vector memory.

    When you're online: Run harvester to fill up your memory.
    When you're offline: All that knowledge is searchable locally.

    Usage:
        from src.memory.vector_store import VectorMemoryStore
        store = VectorMemoryStore("./agent_data/smart_demo")
        harvester = KnowledgeHarvester(store)

        # Harvest specific topics
        harvester.harvest_topic("machine learning")
        harvester.harvest_topic("Python programming")

        # Harvest a specific URL
        harvester.harvest_url("https://docs.python.org/3/tutorial/index.html")

        # Auto-harvest essentials for a well-rounded agent
        results = harvester.harvest_essentials()
    """

    # Wikipedia API for clean text
    WIKI_API = "https://en.wikipedia.org/w/api.php"

    # Essential topics for a well-rounded AI agent
    ESSENTIAL_TOPICS = [
        # Core CS & Programming
        "Python (programming language)",
        "JavaScript",
        "Machine learning",
        "Artificial intelligence",
        "Neural network",
        "Deep learning",
        "Natural language processing",
        "Computer science",
        "Algorithm",
        "Data structure",
        "Object-oriented programming",
        "API",
        "Database",
        "SQL",
        "Git (software)",
        "Linux",
        "Docker (software)",

        # Math & Science
        "Linear algebra",
        "Calculus",
        "Statistics",
        "Probability theory",

        # AI-Specific
        "Large language model",
        "Transformer (deep learning architecture)",
        "Reinforcement learning",
        "Vector database",
        "Retrieval-augmented generation",
        "Few-shot learning",
        "Transfer learning",

        # General knowledge
        "World Wide Web",
        "Internet",
        "Cloud computing",
        "Cybersecurity",
        "Open-source software",
        "Software engineering",
        "Startup company",
        "Entrepreneurship",
    ]

    # Quick knowledge packs — focused topic bundles
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
    }

    def __init__(self, memory_store, chunk_size: int = 500, chunk_overlap: int = 50):
        """
        Args:
            memory_store: VectorMemoryStore instance
            chunk_size: Max characters per chunk
            chunk_overlap: Character overlap between chunks
        """
        self._memory = memory_store
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._stats = HarvestStats()
        self._harvested_urls: set = set()

        # Load previous harvest log if exists
        self._log_path = os.path.join(
            getattr(memory_store, '_data_dir', './agent_data'),
            "harvest_log.json"
        )
        self._load_log()

    def _load_log(self):
        """Load previous harvest log to avoid re-downloading."""
        try:
            if os.path.exists(self._log_path):
                with open(self._log_path, "r") as f:
                    data = json.load(f)
                    self._harvested_urls = set(data.get("harvested_urls", []))
                    self._stats.total_pages_harvested = data.get("total_pages", 0)
                    self._stats.total_chunks_stored = data.get("total_chunks", 0)
                    self._stats.topics_covered = data.get("topics_covered", [])
        except Exception:
            pass

    def _save_log(self):
        """Save harvest log."""
        try:
            os.makedirs(os.path.dirname(self._log_path), exist_ok=True)
            data = {
                "harvested_urls": list(self._harvested_urls),
                "total_pages": self._stats.total_pages_harvested,
                "total_chunks": self._stats.total_chunks_stored,
                "topics_covered": self._stats.topics_covered,
                "last_harvest": self._stats.last_harvest_time,
            }
            with open(self._log_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    # ────────────────────────────────────────────────
    #  Fetching
    # ────────────────────────────────────────────────

    def _fetch_url(self, url: str, timeout: int = 15) -> str:
        """Fetch a URL and return the raw text content."""
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "SmartAgent-KnowledgeHarvester/1.0 (educational research bot)",
                "Accept": "text/html,application/json,text/plain",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            return data.decode(charset, errors="replace")

    def _fetch_wikipedia(self, title: str) -> Optional[str]:
        """Fetch a Wikipedia article's plain text content."""
        params = urllib.parse.urlencode({
            "action": "query",
            "titles": title,
            "prop": "extracts",
            "explaintext": "true",
            "format": "json",
            "exlimit": "1",
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
        """Search Wikipedia and return a list of article titles."""
        params = urllib.parse.urlencode({
            "action": "opensearch",
            "search": query,
            "limit": str(limit),
            "format": "json",
        })
        url = f"{self.WIKI_API}?{params}"
        raw = self._fetch_url(url)
        data = json.loads(raw)
        if len(data) >= 2:
            return data[1]  # List of titles
        return []

    # ────────────────────────────────────────────────
    #  Text Processing
    # ────────────────────────────────────────────────

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks for vector storage."""
        if not text:
            return []

        # Clean text
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)

        # Split by paragraphs first
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
                # If single paragraph is too long, split by sentences
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
        """Generate a hash for deduplication."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    # ────────────────────────────────────────────────
    #  Harvesting Methods
    # ────────────────────────────────────────────────

    def harvest_wikipedia(self, title: str, topic: str = "") -> HarvestResult:
        """
        Harvest a Wikipedia article by title.

        Args:
            title: Wikipedia article title (e.g., "Machine learning")
            topic: Category tag for the knowledge

        Returns:
            HarvestResult
        """
        start = time.time()
        topic = topic or title.lower().replace(" ", "_")
        url_key = f"wikipedia:{title}"

        if url_key in self._harvested_urls:
            return HarvestResult(
                source=f"wikipedia:{title}",
                topic=topic,
                chunks_stored=0,
                total_chars=0,
                success=True,
                error="Already harvested (skipped)",
                duration_s=0,
            )

        try:
            text = self._fetch_wikipedia(title)
            if not text:
                return HarvestResult(
                    source=f"wikipedia:{title}",
                    topic=topic,
                    chunks_stored=0,
                    total_chars=0,
                    success=False,
                    error=f"Article not found: {title}",
                    duration_s=time.time() - start,
                )

            chunks = self._chunk_text(text)
            stored = 0
            for i, chunk in enumerate(chunks):
                if len(chunk.strip()) < 50:
                    continue
                chunk_id = f"wiki_{self._content_hash(chunk)}_{i}"
                self._memory.store(
                    content=chunk,
                    collection="web_knowledge",
                    metadata={
                        "source": "wikipedia",
                        "title": title,
                        "topic": topic,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                        "harvested_at": time.strftime("%Y-%m-%d %H:%M"),
                    },
                )
                stored += 1

            self._harvested_urls.add(url_key)
            self._stats.total_pages_harvested += 1
            self._stats.total_chunks_stored += stored
            self._stats.total_chars_ingested += len(text)
            if topic not in self._stats.topics_covered:
                self._stats.topics_covered.append(topic)
            self._stats.last_harvest_time = time.strftime("%Y-%m-%d %H:%M")
            self._save_log()

            return HarvestResult(
                source=f"wikipedia:{title}",
                topic=topic,
                chunks_stored=stored,
                total_chars=len(text),
                success=True,
                duration_s=time.time() - start,
            )

        except Exception as e:
            self._stats.errors += 1
            return HarvestResult(
                source=f"wikipedia:{title}",
                topic=topic,
                chunks_stored=0,
                total_chars=0,
                success=False,
                error=str(e),
                duration_s=time.time() - start,
            )

    def harvest_topic(self, query: str, max_articles: int = 3) -> List[HarvestResult]:
        """
        Search Wikipedia for a topic and harvest the top articles.

        Args:
            query: Search query (e.g., "quantum computing")
            max_articles: Max articles to harvest per query

        Returns:
            List of HarvestResults
        """
        results = []
        try:
            titles = self._search_wikipedia(query, limit=max_articles)
            for title in titles:
                result = self.harvest_wikipedia(title, topic=query.lower())
                results.append(result)
        except Exception as e:
            results.append(HarvestResult(
                source=f"search:{query}",
                topic=query.lower(),
                chunks_stored=0,
                total_chars=0,
                success=False,
                error=str(e),
            ))
        return results

    def harvest_url(self, url: str, topic: str = "web") -> HarvestResult:
        """
        Harvest knowledge from any URL.

        Args:
            url: The URL to fetch and store
            topic: Category tag

        Returns:
            HarvestResult
        """
        start = time.time()

        if url in self._harvested_urls:
            return HarvestResult(
                source=url, topic=topic, chunks_stored=0,
                total_chars=0, success=True,
                error="Already harvested (skipped)",
            )

        try:
            raw_html = self._fetch_url(url)
            text = html_to_text(raw_html)

            if len(text) < 100:
                return HarvestResult(
                    source=url, topic=topic, chunks_stored=0,
                    total_chars=len(text), success=False,
                    error="Page content too short",
                    duration_s=time.time() - start,
                )

            chunks = self._chunk_text(text)
            stored = 0
            for i, chunk in enumerate(chunks):
                if len(chunk.strip()) < 50:
                    continue
                chunk_id = f"url_{self._content_hash(url + chunk)}_{i}"
                self._memory.store(
                    content=chunk,
                    collection="web_knowledge",
                    metadata={
                        "source": "url",
                        "url": url,
                        "topic": topic,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                        "harvested_at": time.strftime("%Y-%m-%d %H:%M"),
                    },
                )
                stored += 1

            self._harvested_urls.add(url)
            self._stats.total_pages_harvested += 1
            self._stats.total_chunks_stored += stored
            self._stats.total_chars_ingested += len(text)
            if topic not in self._stats.topics_covered:
                self._stats.topics_covered.append(topic)
            self._stats.last_harvest_time = time.strftime("%Y-%m-%d %H:%M")
            self._save_log()

            return HarvestResult(
                source=url, topic=topic, chunks_stored=stored,
                total_chars=len(text), success=True,
                duration_s=time.time() - start,
            )

        except Exception as e:
            self._stats.errors += 1
            return HarvestResult(
                source=url, topic=topic, chunks_stored=0,
                total_chars=0, success=False, error=str(e),
                duration_s=time.time() - start,
            )

    def harvest_essentials(self, callback=None) -> List[HarvestResult]:
        """
        Harvest all essential topics. Run this once when you have internet
        to build a strong offline knowledge base.

        Args:
            callback: Optional function(topic, i, total) called per topic for progress

        Returns:
            List of all HarvestResults
        """
        results = []
        total = len(self.ESSENTIAL_TOPICS)
        for i, title in enumerate(self.ESSENTIAL_TOPICS):
            if callback:
                callback(title, i, total)
            result = self.harvest_wikipedia(title)
            results.append(result)
        return results

    def harvest_pack(self, pack_name: str, callback=None) -> List[HarvestResult]:
        """
        Harvest a specific topic pack.

        Args:
            pack_name: One of "ai_fundamentals", "programming", "math", "business", "general"
            callback: Optional progress callback

        Returns:
            List of HarvestResults
        """
        topics = self.TOPIC_PACKS.get(pack_name)
        if not topics:
            return [HarvestResult(
                source="pack", topic=pack_name, chunks_stored=0,
                total_chars=0, success=False,
                error=f"Unknown pack: {pack_name}. Available: {list(self.TOPIC_PACKS.keys())}",
            )]

        results = []
        total = len(topics)
        for i, title in enumerate(topics):
            if callback:
                callback(title, i, total)
            result = self.harvest_wikipedia(title)
            results.append(result)
        return results

    def harvest_custom(self, text: str, topic: str = "custom", source: str = "user") -> HarvestResult:
        """
        Store custom text directly into knowledge base.
        Useful for pasting in documentation, notes, or any text.

        Args:
            text: The text to store
            topic: Category tag
            source: Source label
        """
        start = time.time()
        chunks = self._chunk_text(text)
        stored = 0
        for i, chunk in enumerate(chunks):
            if len(chunk.strip()) < 30:
                continue
            chunk_id = f"custom_{self._content_hash(chunk)}_{i}"
            self._memory.store(
                content=chunk,
                collection="web_knowledge",
                metadata={
                    "source": source,
                    "topic": topic,
                    "chunk_index": i,
                    "harvested_at": time.strftime("%Y-%m-%d %H:%M"),
                },
            )
            stored += 1

        self._stats.total_chunks_stored += stored
        self._stats.total_chars_ingested += len(text)
        if topic not in self._stats.topics_covered:
            self._stats.topics_covered.append(topic)
        self._stats.last_harvest_time = time.strftime("%Y-%m-%d %H:%M")
        self._save_log()

        return HarvestResult(
            source=source, topic=topic, chunks_stored=stored,
            total_chars=len(text), success=True,
            duration_s=time.time() - start,
        )

    # ────────────────────────────────────────────────
    #  Status & Info 
    # ────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get harvesting statistics."""
        return {
            "total_pages_harvested": self._stats.total_pages_harvested,
            "total_chunks_stored": self._stats.total_chunks_stored,
            "total_chars_ingested": self._stats.total_chars_ingested,
            "topics_covered": self._stats.topics_covered,
            "last_harvest_time": self._stats.last_harvest_time,
            "errors": self._stats.errors,
            "available_packs": list(self.TOPIC_PACKS.keys()),
        }

    def is_online(self) -> bool:
        """Check if we have internet connectivity."""
        try:
            urllib.request.urlopen("https://en.wikipedia.org/w/api.php?action=query&meta=siteinfo&format=json", timeout=5)
            return True
        except Exception:
            return False
