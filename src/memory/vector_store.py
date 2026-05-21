"""
Vector Memory Store — The "Big Memory" Layer

PURPOSE: Persistent, embedding-based long-term memory that a small model
can use to access unlimited knowledge without retraining.

ARCHITECTURE:
    ┌─────────────────────────────────────────────────┐
    │  Vector Store (ChromaDB)                        │
    │  ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
    │  │ Episodic  │ │ Semantic │ │ Procedural     │  │
    │  │ (events)  │ │ (facts)  │ │ (skills/how-to)│  │
    │  └──────────┘ └──────────┘ └────────────────┘  │
    │  ┌──────────────────────────────────────────┐   │
    │  │ Few-Shot Prototypes                       │   │
    │  │ (learned from 1-5 examples)               │   │
    │  └──────────────────────────────────────────┘   │
    └─────────────────────────────────────────────────┘

DESIGN PRINCIPLES:
- Memory stores experience, not truth (inherits from existing contract)
- Embedding-based retrieval = instant recall without retraining
- Show once → remember forever
- Grows smarter with every interaction
- Small footprint: 2-6GB total

COLLECTIONS:
- "episodic"    — What happened (events, interactions, experiences)
- "semantic"    — What seems true (facts, beliefs, knowledge)
- "procedural"  — How to do things (skills, procedures, code patterns)
- "prototypes"  — Few-shot learned categories (1-shot recognition)
- "web_knowledge" — Ingested internet data (articles, docs, pages)

PERSISTENCE: ChromaDB with local SQLite + HNSW index on disk
EMBEDDINGS: sentence-transformers (all-MiniLM-L6-v2) — 384 dims, ~80MB
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ────────────────────────────────────────────────────────
#  Data Structures
# ────────────────────────────────────────────────────────

@dataclass
class MemoryEntry:
    """A single memory entry with embedding metadata."""
    id: str
    content: str
    collection: str           # episodic | semantic | procedural | prototypes | web_knowledge
    metadata: Dict[str, Any]  # source, timestamp, importance, confidence, etc.
    embedding: Optional[List[float]] = None

    @classmethod
    def create(
        cls,
        content: str,
        collection: str,
        source: str = "interaction",
        importance: float = 0.5,
        confidence: float = 0.8,
        extra_metadata: Optional[Dict] = None,
    ) -> MemoryEntry:
        """Create a new memory entry."""
        meta = {
            "source": source,
            "importance": importance,
            "confidence": confidence,
            "created_at": datetime.now().isoformat(),
            "access_count": 0,
            "last_accessed": datetime.now().isoformat(),
        }
        if extra_metadata:
            meta.update(extra_metadata)
        return cls(
            id=str(uuid.uuid4()),
            content=content,
            collection=collection,
            metadata=meta,
        )


@dataclass
class RetrievalResult:
    """Result from a memory retrieval query."""
    id: str
    content: str
    collection: str
    metadata: Dict[str, Any]
    relevance_score: float  # 0.0 - 1.0 (higher = more relevant)
    distance: float         # raw embedding distance


@dataclass
class VectorStoreStats:
    """Statistics about the vector store."""
    total_entries: int
    entries_by_collection: Dict[str, int]
    storage_path: str
    embedding_model: str
    embedding_dimensions: int


# ────────────────────────────────────────────────────────
#  Embedding Provider
# ────────────────────────────────────────────────────────

class EmbeddingProvider:
    """
    Generate embeddings using sentence-transformers with LRU caching.
    
    Default model: all-MiniLM-L6-v2 (~80MB, 384 dimensions)
    - Fast enough for real-time
    - Good quality for retrieval
    - Small enough for edge deployment
    - LRU cache for repeated queries (huge speedup)
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", cache_size: int = 2048):
        self.model_name = model_name
        self._model = None
        self._dimensions = 384  # default for MiniLM
        # LRU embedding cache — avoids recomputing for repeated queries
        self._cache: Dict[str, List[float]] = {}
        self._cache_order: List[str] = []
        self._cache_max = cache_size
        self._cache_hits = 0
        self._cache_misses = 0

    def _load_model(self):
        """Lazy-load the embedding model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                self._dimensions = self._model.get_sentence_embedding_dimension()
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for vector memory. "
                    "Install with: pip install sentence-transformers"
                )

    def _cache_key(self, text: str) -> str:
        """Hash text for cache lookup."""
        return hashlib.md5(text.encode()).hexdigest()

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts (with caching)."""
        self._load_model()
        results = [None] * len(texts)
        uncached_indices = []
        uncached_texts = []

        for i, t in enumerate(texts):
            key = self._cache_key(t)
            if key in self._cache:
                results[i] = self._cache[key]
                self._cache_hits += 1
            else:
                uncached_indices.append(i)
                uncached_texts.append(t)
                self._cache_misses += 1

        if uncached_texts:
            new_embeddings = self._model.encode(uncached_texts, show_progress_bar=False)
            for idx, emb in zip(uncached_indices, new_embeddings):
                emb_list = emb.tolist()
                results[idx] = emb_list
                key = self._cache_key(texts[idx])
                self._cache[key] = emb_list
                self._cache_order.append(key)
                # Evict oldest if cache full
                if len(self._cache_order) > self._cache_max:
                    old_key = self._cache_order.pop(0)
                    self._cache.pop(old_key, None)

        return results

    def embed_one(self, text: str) -> List[float]:
        """Generate embedding for a single text (cached)."""
        return self.embed([text])[0]

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def cache_stats(self) -> Dict[str, int]:
        return {"hits": self._cache_hits, "misses": self._cache_misses,
                "size": len(self._cache), "max": self._cache_max}


# ────────────────────────────────────────────────────────
#  Vector Memory Store
# ────────────────────────────────────────────────────────

# The 5 memory collections
COLLECTIONS = [
    "episodic",       # What happened
    "semantic",       # What seems true
    "procedural",     # How to do things
    "prototypes",     # Few-shot learned categories
    "web_knowledge",  # Ingested internet data
]


class VectorMemoryStore:
    """
    Persistent vector memory using ChromaDB.
    
    This is the "Big Memory" that makes a small model powerful.
    Instead of baking knowledge into billions of parameters,
    we store it in an efficient, searchable vector database.
    
    USAGE:
        store = VectorMemoryStore("./agent_data/vector_memory")
        
        # Store a memory
        store.store("The owner prefers dark mode", "semantic",
                    source="interaction", importance=0.7)
        
        # Retrieve relevant memories
        results = store.retrieve("What does the owner prefer?", limit=5)
        
        # Store a few-shot prototype
        store.store_prototype("kitkat", "A chocolate wafer bar by Nestle",
                            category="food", examples=["red wrapper", "break me off"])
        
        # Recognize from prototype
        matches = store.match_prototype("chocolate bar with red wrapper")
    """

    def __init__(
        self,
        persist_dir: str = "./agent_data/vector_memory",
        embedding_model: str = "all-MiniLM-L6-v2",
    ):
        self._persist_dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)

        # Initialize embedding provider
        self._embedder = EmbeddingProvider(embedding_model)

        # Initialize ChromaDB
        self._client = None
        self._collections: Dict[str, Any] = {}
        self._init_chromadb()

    def _init_chromadb(self):
        """Initialize ChromaDB with persistent storage."""
        try:
            import chromadb
            from chromadb.config import Settings

            self._client = chromadb.PersistentClient(
                path=self._persist_dir,
                settings=Settings(anonymized_telemetry=False),
            )

            # Create or get each collection
            for name in COLLECTIONS:
                self._collections[name] = self._client.get_or_create_collection(
                    name=name,
                    metadata={"hnsw:space": "cosine"},  # cosine similarity
                )

        except ImportError:
            raise ImportError(
                "chromadb is required for vector memory. "
                "Install with: pip install chromadb"
            )

    # ────────────────────────────────────────────────
    #  Core Operations
    # ────────────────────────────────────────────────

    def store(
        self,
        content: str,
        collection: str = "semantic",
        source: str = "interaction",
        importance: float = 0.5,
        confidence: float = 0.8,
        metadata: Optional[Dict[str, Any]] = None,
        dedup: bool = True,
    ) -> str:
        """
        Store a memory entry with its embedding.
        
        Args:
            content: The text to remember
            collection: Which collection (episodic/semantic/procedural/prototypes/web_knowledge)
            source: Where this came from
            importance: How important (0.0-1.0)
            confidence: How certain (0.0-1.0)
            metadata: Additional metadata
            dedup: Skip if very similar content exists (cosine > 0.95)
        
        Returns:
            The memory ID
        """
        if collection not in COLLECTIONS:
            raise ValueError(f"Unknown collection: {collection}. Must be one of {COLLECTIONS}")

        # Deduplication check
        if dedup:
            existing = self.retrieve(content, collection=collection, limit=1)
            if existing and existing[0].relevance_score > 0.95:
                return existing[0].id

        # Build metadata
        entry_meta = {
            "source": source,
            "importance": str(importance),
            "confidence": str(confidence),
            "created_at": datetime.now().isoformat(),
            "access_count": "0",
            "last_accessed": datetime.now().isoformat(),
        }
        if metadata:
            # ChromaDB metadata values must be str, int, float, or bool
            for k, v in metadata.items():
                entry_meta[k] = str(v) if not isinstance(v, (str, int, float, bool)) else v

        entry_id = str(uuid.uuid4())

        # Generate embedding and store
        embedding = self._embedder.embed_one(content)
        self._collections[collection].add(
            ids=[entry_id],
            embeddings=[embedding],
            documents=[content],
            metadatas=[entry_meta],
        )

        return entry_id

    def retrieve(
        self,
        query: str,
        collection: Optional[str] = None,
        limit: int = 10,
        min_relevance: float = 0.0,
        where: Optional[Dict] = None,
    ) -> List[RetrievalResult]:
        """
        Retrieve relevant memories using semantic search.
        
        This is the core "recall" operation — the agent thinks of
        a question/context, and the most relevant memories surface.
        
        Args:
            query: What to search for (natural language)
            collection: Search specific collection, or None for all
            limit: Maximum results
            min_relevance: Minimum relevance score (0.0-1.0)
            where: ChromaDB metadata filter
        
        Returns:
            List of RetrievalResult sorted by relevance (highest first)
        """
        query_embedding = self._embedder.embed_one(query)
        results: List[RetrievalResult] = []

        collections_to_search = (
            [collection] if collection else COLLECTIONS
        )

        for coll_name in collections_to_search:
            coll = self._collections.get(coll_name)
            if coll is None:
                continue

            count = coll.count()
            if count == 0:
                continue

            n_results = min(limit, count)
            try:
                query_result = coll.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results,
                    where=where,
                )
            except Exception:
                continue

            if not query_result or not query_result["ids"] or not query_result["ids"][0]:
                continue

            for i, doc_id in enumerate(query_result["ids"][0]):
                distance = query_result["distances"][0][i]
                # ChromaDB cosine distance: 0 = identical, 2 = opposite
                # Convert to relevance score: 1.0 = identical, 0.0 = opposite
                relevance = 1.0 - (distance / 2.0)

                if relevance < min_relevance:
                    continue

                doc = query_result["documents"][0][i] if query_result["documents"] else ""
                meta = query_result["metadatas"][0][i] if query_result["metadatas"] else {}

                results.append(RetrievalResult(
                    id=doc_id,
                    content=doc,
                    collection=coll_name,
                    metadata=meta,
                    relevance_score=relevance,
                    distance=distance,
                ))

        # Sort by relevance (highest first)
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:limit]

    def retrieve_for_context(
        self,
        query: str,
        max_tokens: int = 2000,
        limit: int = 20,
        collections: Optional[List[str]] = None,
    ) -> str:
        """
        Retrieve memories and format them as context for the LLM.
        
        Args:
            query: The user's question or current context
            max_tokens: Approximate token budget for context
            limit: Maximum memories to consider
            collections: Which collections to search (default: episodic, semantic, procedural)
        """
        # Default: only fast, small collections. Skip web_knowledge (1700+ entries = slow)
        search_collections = collections or ["episodic", "semantic", "procedural"]
        
        results = []
        query_embedding = self._embedder.embed_one(query)
        
        for coll_name in search_collections:
            coll = self._collections.get(coll_name)
            if coll is None:
                continue
            count = coll.count()
            if count == 0:
                continue
            n_results = min(limit, count)
            try:
                qr = coll.query(query_embeddings=[query_embedding], n_results=n_results)
            except Exception:
                continue
            if not qr or not qr["ids"] or not qr["ids"][0]:
                continue
            for i, doc_id in enumerate(qr["ids"][0]):
                distance = qr["distances"][0][i]
                relevance = 1.0 - (distance / 2.0)
                if relevance < 0.3:
                    continue
                doc = qr["documents"][0][i] if qr["documents"] else ""
                results.append((relevance, coll_name, doc))
        
        results.sort(key=lambda x: x[0], reverse=True)

        if not results:
            return ""

        context_parts = []
        char_budget = max_tokens * 4

        for relevance, coll_name, content in results[:limit]:
            entry = f"[{coll_name}|{relevance:.2f}] {content}"
            if len("\n".join(context_parts)) + len(entry) > char_budget:
                break
            context_parts.append(entry)

        if not context_parts:
            return ""

        return (
            "=== RETRIEVED MEMORIES ===\n"
            + "\n".join(context_parts)
            + "\n=== END MEMORIES ===\n"
        )

    # ────────────────────────────────────────────────
    #  Few-Shot Prototype Operations
    # ────────────────────────────────────────────────

    def store_prototype(
        self,
        name: str,
        description: str,
        category: str = "general",
        examples: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Store a few-shot prototype for one-shot learning.
        
        Like a human seeing a KitKat once and remembering forever:
        1. Store the prototype with its description & examples
        2. Future queries match against it via embedding similarity
        3. No retraining needed — just memory
        
        Args:
            name: Prototype name (e.g., "kitkat", "spam_email")
            description: What this thing is
            category: Category grouping
            examples: Optional example descriptions
        
        Returns:
            Prototype memory ID
        """
        # Combine all info into a rich representation
        parts = [f"PROTOTYPE: {name}", f"DESCRIPTION: {description}"]
        if examples:
            for i, ex in enumerate(examples, 1):
                parts.append(f"EXAMPLE {i}: {ex}")

        combined = "\n".join(parts)

        proto_meta = {
            "prototype_name": name,
            "category": category,
            "type": "prototype",
            "example_count": str(len(examples) if examples else 0),
        }
        if metadata:
            proto_meta.update({k: str(v) for k, v in metadata.items()})

        return self.store(
            content=combined,
            collection="prototypes",
            source="few_shot_learning",
            importance=0.9,
            confidence=0.85,
            metadata=proto_meta,
        )

    def match_prototype(
        self,
        query: str,
        category: Optional[str] = None,
        threshold: float = 0.5,
        limit: int = 5,
    ) -> List[RetrievalResult]:
        """
        Match a query against stored prototypes.
        
        This IS the few-shot recognition: no retraining,
        just semantic similarity against stored prototypes.
        
        Args:
            query: What to recognize/classify
            category: Optional category filter
            threshold: Minimum similarity for a match
            limit: Maximum matches to return
        
        Returns:
            Matching prototypes sorted by relevance
        """
        where = {"category": category} if category else None
        return self.retrieve(
            query=query,
            collection="prototypes",
            limit=limit,
            min_relevance=threshold,
            where=where,
        )

    # ────────────────────────────────────────────────
    #  Knowledge Ingestion
    # ────────────────────────────────────────────────

    def ingest_text(
        self,
        text: str,
        source: str,
        collection: str = "web_knowledge",
        chunk_size: int = 500,
        overlap: int = 50,
    ) -> List[str]:
        """
        Ingest a large text (article, doc, webpage) into memory.
        
        Chunks the text and stores each chunk with embeddings.
        This is how the agent "eats internet data" and remembers it.
        
        Args:
            text: The full text to ingest
            source: Where it came from (URL, file, etc.)
            collection: Which collection
            chunk_size: Characters per chunk
            overlap: Character overlap between chunks
        
        Returns:
            List of memory IDs for stored chunks
        """
        chunks = self._chunk_text(text, chunk_size, overlap)
        ids = []

        for i, chunk in enumerate(chunks):
            chunk_meta = {
                "chunk_index": i,
                "total_chunks": len(chunks),
                "source_url": source,
            }
            mid = self.store(
                content=chunk,
                collection=collection,
                source=source,
                importance=0.4,
                confidence=0.7,
                metadata=chunk_meta,
                dedup=True,
            )
            ids.append(mid)

        return ids

    def _chunk_text(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        """Split text into overlapping chunks at sentence boundaries."""
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size

            # Try to break at a sentence boundary
            if end < len(text):
                # Look for sentence-ending punctuation near the boundary
                for boundary_char in ['. ', '.\n', '! ', '? ', '\n\n']:
                    boundary = text.rfind(boundary_char, start + chunk_size // 2, end + 100)
                    if boundary != -1:
                        end = boundary + len(boundary_char)
                        break

            chunks.append(text[start:end].strip())
            start = end - overlap

        return [c for c in chunks if c]

    # ────────────────────────────────────────────────
    #  Maintenance
    # ────────────────────────────────────────────────

    def delete(self, memory_id: str, collection: Optional[str] = None) -> bool:
        """Delete a specific memory entry."""
        collections_to_check = [collection] if collection else COLLECTIONS
        for coll_name in collections_to_check:
            coll = self._collections.get(coll_name)
            if coll is None:
                continue
            try:
                coll.delete(ids=[memory_id])
                return True
            except Exception:
                continue
        return False

    def get_stats(self) -> VectorStoreStats:
        """Get statistics about the vector store."""
        counts = {}
        total = 0
        for name in COLLECTIONS:
            coll = self._collections.get(name)
            count = coll.count() if coll else 0
            counts[name] = count
            total += count

        return VectorStoreStats(
            total_entries=total,
            entries_by_collection=counts,
            storage_path=self._persist_dir,
            embedding_model=self._embedder.model_name,
            embedding_dimensions=self._embedder.dimensions,
        )

    def clear_collection(self, collection: str) -> int:
        """Clear all entries from a collection. Returns count deleted."""
        if collection not in COLLECTIONS:
            raise ValueError(f"Unknown collection: {collection}")
        coll = self._collections[collection]
        count = coll.count()
        if count > 0:
            # ChromaDB: delete all by getting all IDs
            all_ids = coll.get()["ids"]
            if all_ids:
                coll.delete(ids=all_ids)
        return count
