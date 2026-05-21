"""
knowledge_graph.py — Local Knowledge Graph Engine

Inspired by MiroFish's GraphRAG (graph_builder.py + Zep integration),
but implemented as a ZERO-DEPENDENCY local graph with JSON persistence.

CAPABILITIES:
    1. Entity nodes with typed attributes and summaries
    2. Relationship edges with temporal metadata (valid_from, expired_at)
    3. Multi-hop graph traversal — follow chains of relationships
    4. Semantic search via keyword matching + TF-IDF scoring
    5. Entity neighborhood queries — all facts connected to an entity
    6. Automatic merging — same-name entities get merged, not duplicated
    7. Graph statistics and health metrics
    8. JSON persistence to disk

GOES BEYOND MiroFish:
    - No external dependency (no Zep, no cloud)
    - Built-in entity merging
    - Multi-hop traversal with configurable depth
    - Fact confidence scoring
"""
import os
import json
import time
import hashlib
import threading
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List, Set, Tuple
from datetime import datetime
from collections import defaultdict
import math


# ═══════════════════════════════════════════════════════
# DATA TYPES
# ═══════════════════════════════════════════════════════

@dataclass
class GraphNode:
    """An entity in the knowledge graph."""
    id: str
    name: str
    entity_type: str                    # person, organization, concept, event, etc.
    summary: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    mention_count: int = 1              # How many times this entity has been referenced
    confidence: float = 1.0             # 0.0 - 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "GraphNode":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class GraphEdge:
    """A relationship between two entities."""
    id: str
    source_id: str
    target_id: str
    relationship: str                   # "works_at", "caused_by", etc.
    fact: str = ""                      # The actual fact text
    weight: float = 1.0                 # Relationship strength
    confidence: float = 1.0
    # Temporal metadata (MiroFish-inspired)
    valid_from: float = field(default_factory=time.time)
    expired_at: Optional[float] = None  # None = still valid
    created_at: float = field(default_factory=time.time)
    source: str = "extraction"          # "extraction", "user", "inference"

    @property
    def is_active(self) -> bool:
        """Is this fact currently valid?"""
        if self.expired_at is None:
            return True
        return time.time() < self.expired_at

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "GraphEdge":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class SearchResult:
    """Result from a graph search."""
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    facts: List[str]
    query: str
    score: float = 0.0

    def to_text(self) -> str:
        parts = [f"Graph search: '{self.query}' ({len(self.facts)} facts found)"]
        for i, fact in enumerate(self.facts[:20], 1):
            parts.append(f"  {i}. {fact}")
        return "\n".join(parts)


# ═══════════════════════════════════════════════════════
# KNOWLEDGE GRAPH ENGINE
# ═══════════════════════════════════════════════════════

class KnowledgeGraph:
    """
    Local knowledge graph with entity/relationship storage,
    multi-hop traversal, and temporal fact tracking.

    Usage:
        kg = KnowledgeGraph()
        kg.add_entity("OpenAI", "organization", summary="AI research lab")
        kg.add_entity("Sam Altman", "person", summary="CEO of OpenAI")
        kg.add_relationship("Sam Altman", "OpenAI", "leads", fact="Sam Altman is CEO of OpenAI")

        results = kg.search("OpenAI leadership")
        neighborhood = kg.get_entity_neighborhood("OpenAI")
    """

    def __init__(self, storage_path: str = "agent_data/knowledge_graph.json"):
        self.storage_path = storage_path
        self._nodes: Dict[str, GraphNode] = {}          # id -> node
        self._edges: Dict[str, GraphEdge] = {}          # id -> edge
        self._name_index: Dict[str, str] = {}           # lowercase name -> node id
        self._type_index: Dict[str, Set[str]] = defaultdict(set)  # type -> set of node ids
        self._adjacency: Dict[str, Set[str]] = defaultdict(set)   # node_id -> set of edge ids
        self._lock = threading.Lock()

        self._stats = {
            "nodes_created": 0,
            "edges_created": 0,
            "merges": 0,
            "searches": 0,
        }

        # Load from disk
        self._load()

    # ═══════════════════════════════════════════════════════
    # ENTITY OPERATIONS
    # ═══════════════════════════════════════════════════════

    def add_entity(self, name: str, entity_type: str,
                   summary: str = "", attributes: Dict[str, Any] = None,
                   confidence: float = 1.0) -> GraphNode:
        """
        Add an entity to the graph. If it already exists (by name), merge.

        Args:
            name: Entity name (e.g. "OpenAI")
            entity_type: Type category (e.g. "organization", "person")
            summary: Text summary of the entity
            attributes: Key-value attributes
            confidence: 0.0-1.0 confidence in this entity

        Returns:
            The created or merged GraphNode
        """
        with self._lock:
            key = name.lower().strip()

            # Check for existing entity (merge)
            if key in self._name_index:
                existing = self._nodes[self._name_index[key]]
                existing.mention_count += 1
                existing.updated_at = time.time()
                if summary and len(summary) > len(existing.summary):
                    existing.summary = summary
                if attributes:
                    existing.attributes.update(attributes)
                existing.confidence = max(existing.confidence, confidence)
                self._stats["merges"] += 1
                self._auto_save()
                return existing

            # Create new
            node_id = self._generate_id(f"node_{name}")
            node = GraphNode(
                id=node_id, name=name, entity_type=entity_type.lower(),
                summary=summary, attributes=attributes or {},
                confidence=confidence
            )

            self._nodes[node_id] = node
            self._name_index[key] = node_id
            self._type_index[entity_type.lower()].add(node_id)
            self._stats["nodes_created"] += 1
            self._auto_save()
            return node

    def get_entity(self, name: str) -> Optional[GraphNode]:
        """Get entity by name."""
        key = name.lower().strip()
        node_id = self._name_index.get(key)
        return self._nodes.get(node_id) if node_id else None

    def get_entity_by_id(self, node_id: str) -> Optional[GraphNode]:
        """Get entity by ID."""
        return self._nodes.get(node_id)

    def get_entities_by_type(self, entity_type: str) -> List[GraphNode]:
        """Get all entities of a specific type."""
        ids = self._type_index.get(entity_type.lower(), set())
        return [self._nodes[nid] for nid in ids if nid in self._nodes]

    def list_entities(self, limit: int = 50) -> List[GraphNode]:
        """List all entities, sorted by mention count."""
        nodes = sorted(self._nodes.values(), key=lambda n: -n.mention_count)
        return nodes[:limit]

    # ═══════════════════════════════════════════════════════
    # RELATIONSHIP OPERATIONS
    # ═══════════════════════════════════════════════════════

    def add_relationship(self, source_name: str, target_name: str,
                         relationship: str, fact: str = "",
                         weight: float = 1.0, confidence: float = 1.0,
                         source: str = "extraction") -> Optional[GraphEdge]:
        """
        Add a relationship between two entities.
        Creates the entities if they don't exist.

        Args:
            source_name: Source entity name
            target_name: Target entity name
            relationship: Relationship type (e.g. "leads", "caused_by")
            fact: The actual fact text describing this relationship
            weight: Relationship strength (0.0 - 1.0)
            confidence: Confidence in this fact
            source: Where this fact came from

        Returns:
            The created GraphEdge, or None on error
        """
        with self._lock:
            # Ensure both entities exist
            source_key = source_name.lower().strip()
            target_key = target_name.lower().strip()

            if source_key not in self._name_index:
                self._create_entity_internal(source_name, "entity")
            if target_key not in self._name_index:
                self._create_entity_internal(target_name, "entity")

            source_id = self._name_index[source_key]
            target_id = self._name_index[target_key]

            # Create edge
            edge_id = self._generate_id(f"edge_{source_name}_{relationship}_{target_name}")
            edge = GraphEdge(
                id=edge_id, source_id=source_id, target_id=target_id,
                relationship=relationship.lower(), fact=fact,
                weight=weight, confidence=confidence, source=source
            )

            self._edges[edge_id] = edge
            self._adjacency[source_id].add(edge_id)
            self._adjacency[target_id].add(edge_id)
            self._stats["edges_created"] += 1
            self._auto_save()
            return edge

    def _create_entity_internal(self, name: str, entity_type: str):
        """Create entity without lock (called from within locked context)."""
        key = name.lower().strip()
        node_id = self._generate_id(f"node_{name}")
        node = GraphNode(id=node_id, name=name, entity_type=entity_type)
        self._nodes[node_id] = node
        self._name_index[key] = node_id
        self._type_index[entity_type].add(node_id)

    def get_relationships(self, entity_name: str,
                          active_only: bool = True) -> List[GraphEdge]:
        """Get all relationships for an entity."""
        key = entity_name.lower().strip()
        node_id = self._name_index.get(key)
        if not node_id:
            return []

        edge_ids = self._adjacency.get(node_id, set())
        edges = [self._edges[eid] for eid in edge_ids if eid in self._edges]

        if active_only:
            edges = [e for e in edges if e.is_active]

        return edges

    def expire_relationship(self, edge_id: str):
        """Mark a relationship as expired (no longer valid)."""
        if edge_id in self._edges:
            self._edges[edge_id].expired_at = time.time()
            self._auto_save()

    # ═══════════════════════════════════════════════════════
    # GRAPH TRAVERSAL & SEARCH
    # ═══════════════════════════════════════════════════════

    def get_entity_neighborhood(self, entity_name: str,
                                 depth: int = 1,
                                 active_only: bool = True) -> SearchResult:
        """
        Get all entities and facts connected to an entity,
        up to `depth` hops away.
        """
        key = entity_name.lower().strip()
        start_id = self._name_index.get(key)
        if not start_id:
            return SearchResult(nodes=[], edges=[], facts=[], query=entity_name)

        visited_nodes: Set[str] = set()
        visited_edges: Set[str] = set()
        frontier = {start_id}

        for _ in range(depth):
            next_frontier = set()
            for node_id in frontier:
                if node_id in visited_nodes:
                    continue
                visited_nodes.add(node_id)

                for edge_id in self._adjacency.get(node_id, set()):
                    if edge_id in visited_edges:
                        continue
                    edge = self._edges.get(edge_id)
                    if not edge:
                        continue
                    if active_only and not edge.is_active:
                        continue

                    visited_edges.add(edge_id)
                    # Add the other end to frontier
                    other = edge.target_id if edge.source_id == node_id else edge.source_id
                    next_frontier.add(other)

            frontier = next_frontier

        # Include nodes from the final frontier that weren't visited yet
        visited_nodes.update(frontier)

        nodes = [self._nodes[nid] for nid in visited_nodes if nid in self._nodes]
        edges = [self._edges[eid] for eid in visited_edges if eid in self._edges]
        facts = [e.fact for e in edges if e.fact]

        return SearchResult(
            nodes=nodes, edges=edges, facts=facts,
            query=entity_name, score=1.0
        )

    def search(self, query: str, limit: int = 20) -> SearchResult:
        """
        Search the graph using keyword matching with TF-IDF-like scoring.

        Args:
            query: Search query string
            limit: Max results to return

        Returns:
            SearchResult with matching nodes, edges, and facts
        """
        self._stats["searches"] += 1
        query_terms = set(query.lower().split())

        # Score nodes
        node_scores: List[Tuple[float, GraphNode]] = []
        for node in self._nodes.values():
            score = self._score_text(query_terms, node.name, node.summary,
                                     node.entity_type, str(node.attributes))
            if score > 0:
                node_scores.append((score * node.confidence, node))

        # Score edges (facts)
        edge_scores: List[Tuple[float, GraphEdge]] = []
        for edge in self._edges.values():
            if not edge.is_active:
                continue
            score = self._score_text(query_terms, edge.fact, edge.relationship)
            if score > 0:
                edge_scores.append((score * edge.confidence, edge))

        # Sort by score
        node_scores.sort(key=lambda x: -x[0])
        edge_scores.sort(key=lambda x: -x[0])

        top_nodes = [n for _, n in node_scores[:limit]]
        top_edges = [e for _, e in edge_scores[:limit]]
        facts = [e.fact for e in top_edges if e.fact]

        best_score = node_scores[0][0] if node_scores else 0
        return SearchResult(
            nodes=top_nodes, edges=top_edges, facts=facts,
            query=query, score=best_score
        )

    def _score_text(self, query_terms: Set[str], *texts: str) -> float:
        """Simple TF-IDF-like scoring."""
        combined = " ".join(t.lower() for t in texts if t)
        if not combined:
            return 0.0

        doc_terms = combined.split()
        if not doc_terms:
            return 0.0

        score = 0.0
        for term in query_terms:
            tf = sum(1 for t in doc_terms if term in t) / len(doc_terms)
            # IDF approximation: rarer terms score higher
            doc_freq = sum(1 for n in self._nodes.values()
                          if term in n.name.lower() or term in n.summary.lower())
            idf = math.log(max(len(self._nodes), 1) / max(doc_freq, 1) + 1)
            score += tf * idf

        return score

    # ═══════════════════════════════════════════════════════
    # TEMPORAL QUERIES (MiroFish-inspired)
    # ═══════════════════════════════════════════════════════

    def get_active_facts(self, entity_name: str = None) -> List[str]:
        """Get only currently valid facts."""
        edges = self._edges.values()
        if entity_name:
            key = entity_name.lower().strip()
            node_id = self._name_index.get(key)
            if node_id:
                edge_ids = self._adjacency.get(node_id, set())
                edges = [self._edges[eid] for eid in edge_ids if eid in self._edges]

        return [e.fact for e in edges if e.is_active and e.fact]

    def get_historical_facts(self, entity_name: str = None) -> List[str]:
        """Get expired/superseded facts."""
        edges = self._edges.values()
        if entity_name:
            key = entity_name.lower().strip()
            node_id = self._name_index.get(key)
            if node_id:
                edge_ids = self._adjacency.get(node_id, set())
                edges = [self._edges[eid] for eid in edge_ids if eid in self._edges]

        return [e.fact for e in edges if not e.is_active and e.fact]

    # ═══════════════════════════════════════════════════════
    # PERSISTENCE
    # ═══════════════════════════════════════════════════════

    def _auto_save(self):
        """Save to disk (called after mutations)."""
        try:
            self.save()
        except Exception:
            pass

    def save(self):
        """Persist graph to JSON file."""
        os.makedirs(os.path.dirname(self.storage_path) or ".", exist_ok=True)
        data = {
            "nodes": {nid: n.to_dict() for nid, n in self._nodes.items()},
            "edges": {eid: e.to_dict() for eid, e in self._edges.items()},
            "stats": self._stats,
            "saved_at": time.time(),
        }
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load(self):
        """Load graph from JSON file."""
        if not os.path.exists(self.storage_path):
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for nid, ndata in data.get("nodes", {}).items():
                node = GraphNode.from_dict(ndata)
                self._nodes[nid] = node
                self._name_index[node.name.lower().strip()] = nid
                self._type_index[node.entity_type].add(nid)

            for eid, edata in data.get("edges", {}).items():
                edge = GraphEdge.from_dict(edata)
                self._edges[eid] = edge
                self._adjacency[edge.source_id].add(eid)
                self._adjacency[edge.target_id].add(eid)

            self._stats = data.get("stats", self._stats)
        except Exception as e:
            print(f"[KnowledgeGraph] Warning: Failed to load graph: {e}")

    # ═══════════════════════════════════════════════════════
    # UTILITIES
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def _generate_id(seed: str) -> str:
        """Generate a deterministic but unique ID."""
        raw = f"{seed}_{time.time()}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "active_edges": sum(1 for e in self._edges.values() if e.is_active),
            "expired_edges": sum(1 for e in self._edges.values() if not e.is_active),
            "entity_types": list(self._type_index.keys()),
        }

    def clear(self):
        """Clear the entire graph."""
        self._nodes.clear()
        self._edges.clear()
        self._name_index.clear()
        self._type_index.clear()
        self._adjacency.clear()
        self._auto_save()
