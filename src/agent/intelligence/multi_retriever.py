"""
multi_retriever.py — Multi-Strategy Retrieval Engine

Inspired by MiroFish's 3-tier retrieval system:
    - InsightForge (deep analysis with sub-questions)
    - PanoramaSearch (broad graph scan with temporal facts)
    - QuickSearch (fast keyword matching)

CAPABILITIES:
    1. DeepSearch — decomposes query into sub-questions, retrieves for each
    2. BroadSearch — gets full entity neighborhood including expired facts
    3. QuickSearch — fast keyword/semantic matching
    4. AutoRetrieve — automatically picks the best strategy
    5. Unified RetrievalResult with confidence scoring
"""
import time
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from enum import Enum


# ═══════════════════════════════════════════════════════
# DATA TYPES
# ═══════════════════════════════════════════════════════

class RetrievalStrategy(Enum):
    DEEP = "deep"           # Sub-question decomposition + multi-retrieval
    BROAD = "broad"         # Full neighborhood scan
    QUICK = "quick"         # Fast keyword match
    AUTO = "auto"           # Automatically choose


@dataclass
class RetrievalResult:
    """Unified retrieval result across all strategies."""
    query: str
    strategy: str
    facts: List[str] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    sub_queries: List[str] = field(default_factory=list)
    active_facts: List[str] = field(default_factory=list)
    historical_facts: List[str] = field(default_factory=list)
    confidence: float = 0.0
    retrieval_time_ms: float = 0

    @property
    def total_items(self) -> int:
        return len(self.facts) + len(self.entities) + len(self.relationships)

    def to_text(self) -> str:
        """Convert to LLM-readable text format."""
        parts = [
            f"## Retrieval Results ({self.strategy})",
            f"Query: {self.query}",
            f"Found: {len(self.facts)} facts, {len(self.entities)} entities, "
            f"{len(self.relationships)} relationships",
        ]

        if self.sub_queries:
            parts.append("\n### Sub-Questions Analyzed:")
            for i, sq in enumerate(self.sub_queries, 1):
                parts.append(f"  {i}. {sq}")

        if self.facts:
            parts.append("\n### Key Facts:")
            for i, fact in enumerate(self.facts[:15], 1):
                parts.append(f"  {i}. \"{fact}\"")

        if self.entities:
            parts.append("\n### Related Entities:")
            for ent in self.entities[:10]:
                parts.append(f"  - **{ent.get('name', '?')}** ({ent.get('type', 'entity')})")

        if self.historical_facts:
            parts.append(f"\n### Historical/Expired Facts ({len(self.historical_facts)}):")
            for i, fact in enumerate(self.historical_facts[:5], 1):
                parts.append(f"  {i}. [EXPIRED] \"{fact}\"")

        return "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "strategy": self.strategy,
            "facts": self.facts,
            "entities": self.entities,
            "relationships": self.relationships,
            "confidence": self.confidence,
            "total_items": self.total_items,
        }


# ═══════════════════════════════════════════════════════
# SUB-QUESTION DECOMPOSITION PROMPT
# ═══════════════════════════════════════════════════════

DECOMPOSE_PROMPT = """Break down this complex question into 3-5 simpler sub-questions that would help answer it completely.

QUESTION: {query}

Return a JSON array of sub-questions:
["sub-question 1", "sub-question 2", "sub-question 3"]

Return ONLY the JSON array, no additional text.
"""


# ═══════════════════════════════════════════════════════
# MULTI-STRATEGY RETRIEVER
# ═══════════════════════════════════════════════════════

class MultiRetriever:
    """
    Multi-strategy retrieval engine with 3 modes:
    Deep (sub-question analysis), Broad (neighborhood scan), Quick (keyword match).

    Usage:
        retriever = MultiRetriever(knowledge_graph=kg, llm_fn=llm.generate)
        result = retriever.retrieve("What is OpenAI's strategy?", strategy="auto")
        print(result.to_text())
    """

    def __init__(self, knowledge_graph=None, llm_fn: Callable = None):
        """
        Args:
            knowledge_graph: KnowledgeGraph instance for graph-based retrieval
            llm_fn: LLM function for sub-question decomposition (optional)
        """
        self._kg = knowledge_graph
        self._llm_fn = llm_fn
        self._stats = {
            "deep_searches": 0,
            "broad_searches": 0,
            "quick_searches": 0,
            "auto_selections": 0,
        }

    def set_knowledge_graph(self, kg):
        """Set or update the knowledge graph."""
        self._kg = kg

    def retrieve(self, query: str,
                 strategy: str = "auto",
                 limit: int = 20) -> RetrievalResult:
        """
        Retrieve information using the specified strategy.

        Args:
            query: The search query
            strategy: "deep", "broad", "quick", or "auto"
            limit: Max results per sub-query

        Returns:
            RetrievalResult with facts, entities, relationships
        """
        start = time.time()

        if strategy == "auto":
            strategy = self._auto_select_strategy(query)
            self._stats["auto_selections"] += 1

        if strategy == "deep":
            result = self._deep_search(query, limit)
            self._stats["deep_searches"] += 1
        elif strategy == "broad":
            result = self._broad_search(query, limit)
            self._stats["broad_searches"] += 1
        else:
            result = self._quick_search(query, limit)
            self._stats["quick_searches"] += 1

        result.retrieval_time_ms = (time.time() - start) * 1000
        return result

    # ═══════════════════════════════════════════════════════
    # STRATEGY 1: DEEP SEARCH (InsightForge-inspired)
    # ═══════════════════════════════════════════════════════

    def _deep_search(self, query: str, limit: int) -> RetrievalResult:
        """
        Deep search: decompose query into sub-questions, search for each,
        then synthesize results.
        """
        # Decompose into sub-questions
        sub_queries = self._decompose_query(query)

        all_facts = []
        all_entities = []
        all_relationships = []
        seen_facts = set()

        for sq in sub_queries:
            if self._kg:
                search_result = self._kg.search(sq, limit=limit)
                for fact in search_result.facts:
                    if fact not in seen_facts:
                        all_facts.append(fact)
                        seen_facts.add(fact)
                for node in search_result.nodes:
                    ent_dict = {"name": node.name, "type": node.entity_type,
                                "summary": node.summary}
                    if ent_dict not in all_entities:
                        all_entities.append(ent_dict)
                for edge in search_result.edges:
                    rel_dict = {"source": edge.source_id, "target": edge.target_id,
                                "relationship": edge.relationship, "fact": edge.fact}
                    all_relationships.append(rel_dict)

        confidence = min(1.0, len(all_facts) / max(limit, 1))

        return RetrievalResult(
            query=query, strategy="deep",
            facts=all_facts[:limit],
            entities=all_entities[:limit],
            relationships=all_relationships[:limit],
            sub_queries=sub_queries,
            confidence=confidence,
        )

    def _decompose_query(self, query: str) -> List[str]:
        """Decompose a complex query into sub-questions."""
        if self._llm_fn:
            try:
                prompt = DECOMPOSE_PROMPT.format(query=query)
                response = self._llm_fn(prompt)

                # Parse JSON array
                parsed = self._parse_json_array(response)
                if parsed and len(parsed) >= 2:
                    return parsed[:5]
            except Exception:
                pass

        # Fallback: create sub-questions from key terms
        words = query.split()
        key_terms = [w for w in words if len(w) > 3 and w[0].isupper()]
        sub_queries = [query]  # Always include original

        if key_terms:
            for term in key_terms[:3]:
                sub_queries.append(f"What is {term}?")
                sub_queries.append(f"How is {term} related to {query[:50]}?")

        return sub_queries[:5]

    # ═══════════════════════════════════════════════════════
    # STRATEGY 2: BROAD SEARCH (PanoramaSearch-inspired)
    # ═══════════════════════════════════════════════════════

    def _broad_search(self, query: str, limit: int) -> RetrievalResult:
        """
        Broad search: get full entity neighborhood including expired facts.
        Shows the complete picture — active AND historical.
        """
        if not self._kg:
            return RetrievalResult(query=query, strategy="broad")

        # First find relevant entities
        search = self._kg.search(query, limit=5)

        all_facts = []
        active = []
        historical = []
        all_entities = []
        all_relationships = []
        seen = set()

        for node in search.nodes:
            # Get full neighborhood (2 hops deep)
            neighborhood = self._kg.get_entity_neighborhood(node.name, depth=2, active_only=False)

            for n in neighborhood.nodes:
                ent = {"name": n.name, "type": n.entity_type, "summary": n.summary}
                if n.name not in seen:
                    all_entities.append(ent)
                    seen.add(n.name)

            for edge in neighborhood.edges:
                if edge.fact:
                    all_facts.append(edge.fact)
                    if edge.is_active:
                        active.append(edge.fact)
                    else:
                        historical.append(edge.fact)

                all_relationships.append({
                    "source": edge.source_id, "target": edge.target_id,
                    "relationship": edge.relationship, "fact": edge.fact,
                    "active": edge.is_active,
                })

        return RetrievalResult(
            query=query, strategy="broad",
            facts=all_facts[:limit],
            entities=all_entities[:limit],
            relationships=all_relationships[:limit],
            active_facts=active[:limit],
            historical_facts=historical[:limit],
            confidence=min(1.0, len(all_facts) / max(limit, 1)),
        )

    # ═══════════════════════════════════════════════════════
    # STRATEGY 3: QUICK SEARCH
    # ═══════════════════════════════════════════════════════

    def _quick_search(self, query: str, limit: int) -> RetrievalResult:
        """Quick keyword search — fastest strategy."""
        if not self._kg:
            return RetrievalResult(query=query, strategy="quick")

        search = self._kg.search(query, limit=limit)

        entities = [{"name": n.name, "type": n.entity_type, "summary": n.summary}
                    for n in search.nodes]
        relationships = [{"source": e.source_id, "target": e.target_id,
                          "relationship": e.relationship, "fact": e.fact}
                         for e in search.edges]

        return RetrievalResult(
            query=query, strategy="quick",
            facts=search.facts[:limit],
            entities=entities[:limit],
            relationships=relationships[:limit],
            confidence=search.score,
        )

    # ═══════════════════════════════════════════════════════
    # AUTO-SELECTION
    # ═══════════════════════════════════════════════════════

    def _auto_select_strategy(self, query: str) -> str:
        """Automatically choose the best retrieval strategy."""
        query_lower = query.lower()
        word_count = len(query.split())

        # Deep: complex questions, multi-part, analysis keywords
        deep_signals = ["why", "how", "compare", "analyze", "explain", "what are the",
                        "relationship between", "impact of", "effect of"]
        if any(s in query_lower for s in deep_signals) or word_count > 8:
            return "deep"

        # Broad: overview, timeline, history keywords
        broad_signals = ["overview", "history", "timeline", "everything about",
                         "all about", "full picture", "connection"]
        if any(s in query_lower for s in broad_signals):
            return "broad"

        # Quick: simple lookups
        return "quick"

    @staticmethod
    def _parse_json_array(text: str) -> Optional[List[str]]:
        """Parse a JSON array from text."""
        try:
            result = __import__("json").loads(text)
            if isinstance(result, list):
                return [str(item) for item in result]
        except Exception:
            pass

        # Try extracting from code block
        match = re.search(r'\[[\s\S]*?\]', text)
        if match:
            try:
                result = __import__("json").loads(match.group())
                if isinstance(result, list):
                    return [str(item) for item in result]
            except Exception:
                pass

        return None

    def get_stats(self) -> Dict[str, Any]:
        return dict(self._stats)
