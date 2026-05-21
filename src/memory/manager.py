"""
Memory Manager

THE ONLY PUBLIC INTERFACE TO MEMORY.

No other layer touches memory directly.
World Model queries Memory Manager.
World Model feeds Memory Manager.
Memory NEVER decides belief.

ALLOWED OPERATIONS:
- store_episode(event)
- store_fact(statement)
- reinforce(memory_id)
- contradict(memory_id)
- decay_all()
- query(text, limit)

FORBIDDEN:
- "overwrite truth"
- "always trust memory"
- "store everything"
- "never forget"
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from .short_term import ShortTermMemory, STMEntry
from .episodic import EpisodicMemory, Episode
from .semantic import SemanticMemory, Fact
from .meta import MetaMemory, Unknown
from src.core.identity import Identity


@dataclass
class MemoryStats:
    """Statistics about the memory system."""
    stm_entries: int
    episodic_active: int
    episodic_total: int
    semantic_active: int
    semantic_total: int
    meta_active: int
    last_decay: Optional[datetime]


class MemoryManager:
    """
    Unified interface to all memory systems.
    
    This is the ONLY entry point for memory operations.
    No other layer should directly access episodic, semantic,
    or meta memory classes.
    
    CONTRACT:
    - Memory stores experience, not truth
    - Memory can be wrong
    - Memory decays
    - Memory never overrides the World Model
    """
    
    
    def __init__(self, data_dir: Path, stm_size: int = 50, identity: Optional[Identity] = None):
        """
        Initialize the memory manager.
        
        Args:
            data_dir: Directory for persistent storage
            stm_size: Maximum size of short-term memory
            identity: Layer 0 Identity (Owner of the memory)
        """
        self.identity = identity
        self._data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize memory systems
        self._stm = ShortTermMemory(max_size=stm_size)
        self._episodic = EpisodicMemory(data_dir / "episodic.db")
        self._semantic = SemanticMemory(data_dir / "semantic.db")
        self._meta = MetaMemory(data_dir / "meta.db")
        
        self._last_decay: Optional[datetime] = None
    
    # =========== SHORT-TERM MEMORY ===========
    
    def add_to_context(self, content: str, metadata: Optional[dict] = None) -> STMEntry:
        """Add content to short-term working memory."""
        return self._stm.add(content, metadata)
    
    def get_recent_context(self, n: int = 10) -> list[STMEntry]:
        """Get recent short-term memory entries."""
        return self._stm.get_recent(n)
    
    def set_focus(self, topics: list[str]) -> None:
        """Set current attention focus."""
        self._stm.set_attention(topics)
    
    def get_focus(self) -> list[str]:
        """Get current attention focus."""
        return self._stm.get_attention()
    
    def clear_context(self) -> None:
        """Clear short-term memory (e.g., session end)."""
        self._stm.clear()
    
    # =========== EPISODIC MEMORY ===========
    
    def store_episode(
        self,
        content: str,
        importance: float,
        source: str,
        confidence: float = 0.9,
    ) -> Episode:
        """
        Store a new episodic memory (something that happened).
        
        Args:
            content: Description of what happened
            importance: How significant (0.0 - 1.0)
            source: Where this information came from
            confidence: How certain we are (default 0.9)
        
        Returns:
            The created Episode
        """
        episode = Episode.create(
            content=content,
            importance=importance,
            source=source,
            confidence=confidence,
        )
        self._episodic.store(episode)
        return episode
    
    def get_recent_episodes(self, hours: int = 24, limit: int = 50) -> list[Episode]:
        """Get recent episodes."""
        return self._episodic.get_recent(hours=hours, limit=limit)
    
    def get_important_episodes(self, limit: int = 20) -> list[Episode]:
        """Get the most important active episodes."""
        return self._episodic.get_active(limit=limit)
    
    # =========== SEMANTIC MEMORY ===========
    
    def store_fact(
        self,
        statement: str,
        source: str,
        confidence: float = 0.7,
    ) -> Fact:
        """
        Store a believed fact.
        
        IMPORTANT: This is what the agent BELIEVES, not truth.
        
        Args:
            statement: The believed fact
            source: Where this came from
            confidence: How certain (default 0.7 - not too high)
        
        Returns:
            The created Fact
        """
        fact = Fact.create(
            statement=statement,
            source=source,
            confidence=confidence,
        )
        self._semantic.store(fact)
        return fact
    
    def find_facts(self, search_term: str, limit: int = 10) -> list[Fact]:
        """Find facts matching a search term."""
        return self._semantic.find_by_content(search_term, limit=limit)
    
    def get_reliable_facts(self, limit: int = 50) -> list[Fact]:
        """Get the most reliable facts."""
        return self._semantic.get_reliable(limit=limit)
    
    # =========== META-MEMORY ===========
    
    def add_unknown(
        self,
        question: str,
        priority: float = 0.5,
    ) -> Unknown:
        """
        Add something we don't know.
        
        This drives curiosity and question generation.
        
        Args:
            question: What we want to know
            priority: How important (0.0 - 1.0)
        
        Returns:
            The created Unknown
        """
        unknown = Unknown.create(question=question, priority=priority)
        self._meta.store(unknown)
        return unknown
    
    def get_top_questions(self, limit: int = 5) -> list[Unknown]:
        """Get the highest priority unanswered questions."""
        return self._meta.get_top_questions(limit=limit)
    
    def resolve_question(self, unknown_id: str) -> Optional[Unknown]:
        """Mark a question as answered."""
        return self._meta.resolve(unknown_id)
    
    # =========== UNIVERSAL OPERATIONS ===========
    
    def reinforce(
        self,
        memory_id: str,
        memory_type: str = "auto",
        strength: float = 0.2,
    ) -> Optional[Union[Episode, Fact]]:
        """
        Reinforce a memory (evidence supports it).
        
        Args:
            memory_id: The memory ID
            memory_type: "episodic", "semantic", or "auto" (try both)
            strength: Reinforcement strength (0.1 - 0.3)
        
        Returns:
            The reinforced memory, or None if not found
        """
        if memory_type in ("episodic", "auto"):
            result = self._episodic.reinforce(memory_id, strength)
            if result:
                return result
        
        if memory_type in ("semantic", "auto"):
            result = self._semantic.reinforce(memory_id, strength)
            if result:
                return result
        
        return None
    
    def contradict(
        self,
        memory_id: str,
        memory_type: str = "auto",
        penalty: float = 0.15,
    ) -> Optional[Union[Episode, Fact]]:
        """
        Contradict a memory (evidence against it).
        
        Args:
            memory_id: The memory ID
            memory_type: "episodic", "semantic", or "auto" (try both)
            penalty: Confidence reduction (0.1 - 0.2)
        
        Returns:
            The contradicted memory, or None if not found
        """
        if memory_type in ("episodic", "auto"):
            result = self._episodic.contradict(memory_id, penalty)
            if result:
                return result
        
        if memory_type in ("semantic", "auto"):
            result = self._semantic.contradict(memory_id, penalty)
            if result:
                return result
        
        return None
    
    def decay_all(self, current_time: Optional[datetime] = None) -> dict[str, int]:
        """
        Apply decay to all memory types.
        
        Should be called periodically (e.g., session start).
        
        Returns:
            Dict of counts of newly inactive memories by type
        """
        current_time = current_time or datetime.now()
        
        results = {
            "episodic": self._episodic.decay_all(current_time),
            "semantic": self._semantic.decay_all(current_time),
            "meta": self._meta.decay_all(current_time),
        }
        
        self._last_decay = current_time
        return results
    
    def get_stats(self) -> MemoryStats:
        """Get statistics about the memory system."""
        return MemoryStats(
            stm_entries=len(self._stm),
            episodic_active=self._episodic.count_active(),
            episodic_total=self._episodic.count_total(),
            semantic_active=self._semantic.count_active(),
            semantic_total=self._semantic.count_total(),
            meta_active=self._meta.count_active(),
            last_decay=self._last_decay,
        )
    
    # =========== ADVANCED QUERIES ===========
    
    def query(
        self,
        text: str,
        limit: int = 5,
    ) -> dict[str, list]:
        """
        Query across all memory types.
        
        For v0, this is simple text matching.
        Later: will use embeddings for semantic search.
        
        Args:
            text: Search query
            limit: Max results per type
        
        Returns:
            Dict with "episodes", "facts", "unknowns" lists
        """
        # WARNING:
        # This method returns MEMORY EVIDENCE, not truth.
        # World Model MUST decide belief formation.
        # Do NOT consume these objects directly for reasoning.
        
        # TODO: Add embedding-based search
        
        return {
            "episodes": [],  # Will implement with embeddings
            "facts": self._semantic.find_by_content(text, limit=limit),
            "unknowns": self._meta.find_similar(text, limit=limit),
        }
