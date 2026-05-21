"""
intelligence/ — Swarm Intelligence Modules (MiroFish-Inspired)

Cognitive upgrade layer for the Agentic Engine Pro.
Adds knowledge graphs, entity extraction, ReACT reasoning,
multi-strategy retrieval, temporal memory, and adaptive personas.
"""
from .knowledge_graph import KnowledgeGraph
from .entity_extractor import EntityExtractor
from .react_loop import ReACTLoop
from .multi_retriever import MultiRetriever
from .persona_engine import PersonaEngine

__all__ = [
    "KnowledgeGraph",
    "EntityExtractor",
    "ReACTLoop",
    "MultiRetriever",
    "PersonaEngine",
]
