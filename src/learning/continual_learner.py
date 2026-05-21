"""
Continual Learning Module — Gets Smarter Every Day Without Retraining

PURPOSE: The agent learns from every interaction and grows its knowledge
continuously, without ever needing to retrain the base model.

THE PROBLEM WITH TRADITIONAL ML:
    - Train a model → deploy → it's frozen → needs retraining to learn new things
    - Retraining = expensive (GPUs, time, data collection)
    - Fine-tuning = catastrophic forgetting (forgets old stuff)

OUR SOLUTION: Memory-Based Continual Learning
    - Base model stays frozen (no weight updates)
    - New knowledge → stored in Vector Memory
    - Patterns → extracted and stored as semantic facts
    - Skills → captured in procedural memory
    - User preferences → tracked and strengthened over time
    - Internet data → ingested and chunked into web_knowledge

HOW IT WORKS:
    ┌───────────────┐    ┌──────────────────┐    ┌─────────────┐
    │  Interaction   │───►│  Pattern          │───►│  Vector     │
    │  (chat, task,  │    │  Extractor        │    │  Memory     │
    │   error, web)  │    │  (what to learn?) │    │  Store      │
    │               │    │                    │    │             │
    └───────────────┘    └──────────────────┘    └─────────────┘
                                                        │
    ┌───────────────┐    ┌──────────────────┐          │
    │  Retrieval     │◄───│  Knowledge        │◄─────────┘
    │  (next query   │    │  Consolidation    │
    │   uses this)   │    │  (merge, prune,   │
    │               │    │   strengthen)      │
    └───────────────┘    └──────────────────┘

INSPIRED BY:
    - Elastic Weight Consolidation (Kirkpatrick et al., 2017)
      → But we protect memory entries instead of weights
    - Experience Replay (Lin, 1992)
      → We replay important memories by retrieving them
    - Complementary Learning Systems (McClelland et al., 1995)
      → Fast learning (vector store) + slow consolidation

NO CATASTROPHIC FORGETTING because we never modify the base model.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ..memory.vector_store import VectorMemoryStore, RetrievalResult


# ────────────────────────────────────────────────────────
#  Data Structures
# ────────────────────────────────────────────────────────

@dataclass
class LearningEvent:
    """A single learning event (something the agent should learn from)."""
    event_type: str       # interaction | correction | error | web_ingest | observation
    content: str          # The raw content
    extracted_facts: List[str]  # Extracted knowledge
    source: str           # Where it came from
    timestamp: str
    importance: float     # 0.0 - 1.0


@dataclass
class ConsolidationResult:
    """Result of a knowledge consolidation pass."""
    memories_reviewed: int
    duplicates_merged: int
    weak_memories_pruned: int
    patterns_extracted: int
    timestamp: str


@dataclass
class ContinualLearnerStats:
    """Statistics about the continual learner."""
    total_events_processed: int
    facts_extracted: int
    corrections_applied: int
    consolidations_run: int
    last_consolidation: Optional[str]
    knowledge_growth_rate: float  # entries per day


# ────────────────────────────────────────────────────────
#  Pattern Extraction Prompts
# ────────────────────────────────────────────────────────

EXTRACT_FACTS_PROMPT = """Given this interaction, extract any facts, preferences, or knowledge worth remembering.
Return ONLY a JSON array of strings. Each string should be a single atomic fact.
If there's nothing worth learning, return an empty array [].

Examples:
- "The user prefers Python over JavaScript"
- "The project uses FastAPI for the backend"
- "The user's name is Abdul"
- "Dubai property prices increased 15% in 2025"

Interaction:
{content}

JSON array of facts:"""

EXTRACT_CORRECTION_PROMPT = """The user corrected the AI. Extract what was wrong and what the correct answer is.
Return a JSON object with "wrong" and "correct" fields.

Interaction:
{content}

JSON:"""


# ────────────────────────────────────────────────────────
#  Continual Learner
# ────────────────────────────────────────────────────────

class ContinualLearner:
    """
    Memory-based continual learning engine.
    
    The agent gets smarter with every interaction WITHOUT retraining.
    All new knowledge goes into the Vector Memory Store, which the
    Small Model Bridge retrieves at inference time.
    
    USAGE:
        learner = ContinualLearner(vector_store)
        
        # After every interaction
        learner.learn_from_interaction(
            user_message="My favorite color is blue",
            agent_response="Noted! Your favorite color is blue.",
        )
        
        # After a user correction
        learner.learn_from_correction(
            original_response="Your project uses Django",
            correction="No, it uses FastAPI",
        )
        
        # Ingest web data
        learner.learn_from_web(
            url="https://example.com/article",
            content="Full article text...",
        )
        
        # Periodic consolidation (merge duplicates, prune weak)
        learner.consolidate()
    """

    def __init__(
        self,
        vector_store: VectorMemoryStore,
        llm_generate: Optional[Any] = None,
        auto_consolidate_every: int = 100,
    ):
        """
        Args:
            vector_store: The vector memory store
            llm_generate: Optional callable(prompt) → str for fact extraction
            auto_consolidate_every: Run consolidation every N events
        """
        self._store = vector_store
        self._llm_generate = llm_generate
        self._auto_consolidate_every = auto_consolidate_every

        # State
        self._events_processed = 0
        self._facts_extracted = 0
        self._corrections_applied = 0
        self._consolidations_run = 0
        self._last_consolidation: Optional[datetime] = None
        self._daily_counts: Dict[str, int] = {}  # date → count

    # ────────────────────────────────────────────────
    #  Learning from Interactions
    # ────────────────────────────────────────────────

    def learn_from_interaction(
        self,
        user_message: str,
        agent_response: str,
        importance: float = 0.5,
    ) -> LearningEvent:
        """
        Learn from a user-agent interaction.
        
        Extracts useful facts and stores them in memory.
        This is called after every conversation turn.
        """
        self._events_processed += 1
        content = f"USER: {user_message}\nAGENT: {agent_response}"

        # Extract facts
        facts = self._extract_facts(content)

        # Store the interaction itself (episodic)
        self._store.store(
            content=content,
            collection="episodic",
            source="interaction",
            importance=importance,
            confidence=0.9,
        )

        # Store each extracted fact (semantic)
        for fact in facts:
            self._store.store(
                content=fact,
                collection="semantic",
                source="interaction_extraction",
                importance=importance + 0.1,
                confidence=0.75,
                dedup=True,
            )
            self._facts_extracted += 1

        # Track daily count
        today = datetime.now().strftime("%Y-%m-%d")
        self._daily_counts[today] = self._daily_counts.get(today, 0) + 1

        # Auto-consolidate if threshold reached
        if self._events_processed % self._auto_consolidate_every == 0:
            self.consolidate()

        return LearningEvent(
            event_type="interaction",
            content=content,
            extracted_facts=facts,
            source="user_interaction",
            timestamp=datetime.now().isoformat(),
            importance=importance,
        )

    def learn_from_correction(
        self,
        original_response: str,
        correction: str,
        context: str = "",
    ) -> LearningEvent:
        """
        Learn from a user correction. This is high-value learning —
        the agent was WRONG and the user has the correct answer.
        
        Stores both:
        1. The correct fact (high confidence)
        2. The wrong statement (to avoid repeating)
        """
        self._events_processed += 1
        self._corrections_applied += 1

        content = (
            f"CORRECTION — Agent said: {original_response}\n"
            f"User corrected: {correction}\n"
            f"Context: {context}"
        )

        # Store the correct fact with high importance
        self._store.store(
            content=f"CORRECTED FACT: {correction} (Agent previously said: {original_response})",
            collection="semantic",
            source="user_correction",
            importance=0.9,
            confidence=0.95,
            metadata={"type": "correction", "original": original_response},
        )

        # Store the interaction as episodic
        self._store.store(
            content=content,
            collection="episodic",
            source="correction",
            importance=0.8,
            confidence=0.95,
        )

        return LearningEvent(
            event_type="correction",
            content=content,
            extracted_facts=[correction],
            source="user_correction",
            timestamp=datetime.now().isoformat(),
            importance=0.9,
        )

    def learn_from_error(
        self,
        error_description: str,
        solution: str,
        context: str = "",
    ) -> LearningEvent:
        """
        Learn from an error and its fix.
        Stores as procedural memory (how to fix things).
        """
        self._events_processed += 1

        content = f"ERROR: {error_description}\nFIX: {solution}"
        if context:
            content += f"\nCONTEXT: {context}"

        self._store.store(
            content=content,
            collection="procedural",
            source="error_learning",
            importance=0.7,
            confidence=0.8,
            metadata={"type": "error_fix"},
        )

        return LearningEvent(
            event_type="error",
            content=content,
            extracted_facts=[f"When '{error_description}' occurs, fix: {solution}"],
            source="error_observation",
            timestamp=datetime.now().isoformat(),
            importance=0.7,
        )

    def learn_from_web(
        self,
        url: str,
        content: str,
        topic: str = "",
    ) -> LearningEvent:
        """
        Learn from web content. Chunks and stores in web_knowledge.
        This is how the agent "eats internet data."
        """
        self._events_processed += 1

        ids = self._store.ingest_text(
            text=content,
            source=url,
            collection="web_knowledge",
            chunk_size=500,
            overlap=50,
        )

        # Also extract high-level facts
        facts = self._extract_facts(content[:2000])  # First 2000 chars
        for fact in facts:
            self._store.store(
                content=fact,
                collection="semantic",
                source=url,
                importance=0.4,
                confidence=0.6,
                dedup=True,
            )
            self._facts_extracted += 1

        return LearningEvent(
            event_type="web_ingest",
            content=f"Ingested {len(ids)} chunks from {url}",
            extracted_facts=facts,
            source=url,
            timestamp=datetime.now().isoformat(),
            importance=0.4,
        )

    def learn_skill(
        self,
        skill_name: str,
        description: str,
        steps: List[str],
        examples: Optional[List[str]] = None,
    ) -> LearningEvent:
        """
        Learn a new skill/procedure. Stored in procedural memory.
        Like teaching a human how to do something step by step.
        """
        self._events_processed += 1

        parts = [f"SKILL: {skill_name}", f"DESCRIPTION: {description}", "STEPS:"]
        for i, step in enumerate(steps, 1):
            parts.append(f"  {i}. {step}")
        if examples:
            parts.append("EXAMPLES:")
            for ex in examples:
                parts.append(f"  - {ex}")

        content = "\n".join(parts)

        self._store.store(
            content=content,
            collection="procedural",
            source="skill_learning",
            importance=0.8,
            confidence=0.85,
            metadata={"type": "skill", "skill_name": skill_name},
        )

        return LearningEvent(
            event_type="observation",
            content=content,
            extracted_facts=[f"Learned skill: {skill_name}"],
            source="skill_learning",
            timestamp=datetime.now().isoformat(),
            importance=0.8,
        )

    # ────────────────────────────────────────────────
    #  Knowledge Consolidation
    # ────────────────────────────────────────────────

    def consolidate(self) -> ConsolidationResult:
        """
        Consolidate knowledge: merge duplicates, prune weak entries,
        extract cross-entry patterns.
        
        Like human sleep — the brain consolidates memories,
        strengthens important ones, discards noise.
        """
        self._consolidations_run += 1
        self._last_consolidation = datetime.now()

        merged = 0
        pruned = 0
        patterns = 0
        reviewed = 0

        # Review semantic + procedural for duplicates and weak entries
        for collection_name in ["semantic", "procedural"]:
            try:
                results = self._store.retrieve(
                    query="important knowledge facts",
                    collection=collection_name,
                    limit=50,
                    min_relevance=0.0,
                )
                reviewed += len(results)

                # Track seen entries: id → (content, confidence)
                seen: dict = {}  # id → (content, confidence)
                to_delete = []   # ids to remove

                for r in results:
                    r_conf = float(r.metadata.get("confidence", 0.5))
                    r_imp = float(r.metadata.get("importance", 0.5))

                    # Prune weak memories (low importance + low confidence)
                    if r_imp < 0.3 and r_conf < 0.4:
                        to_delete.append(r.id)
                        pruned += 1
                        continue

                    # Find near-duplicate pairs and keep the stronger one
                    is_dup = False
                    for prev_id, (prev_content, prev_conf) in seen.items():
                        if self._text_similarity(r.content, prev_content) > 0.85:
                            # Keep whichever has higher confidence, delete the other
                            if r_conf >= prev_conf:
                                to_delete.append(prev_id)
                                del seen[prev_id]
                                seen[r.id] = (r.content, r_conf)
                            else:
                                to_delete.append(r.id)
                            merged += 1
                            is_dup = True
                            break
                    if not is_dup:
                        seen[r.id] = (r.content, r_conf)

                # Actually delete the duplicates and weak entries
                for del_id in to_delete:
                    try:
                        self._store.delete(del_id, collection_name)
                    except Exception:
                        pass

            except Exception:
                continue

        return ConsolidationResult(
            memories_reviewed=reviewed,
            duplicates_merged=merged,
            weak_memories_pruned=pruned,
            patterns_extracted=patterns,
            timestamp=datetime.now().isoformat(),
        )

    # ────────────────────────────────────────────────
    #  Fact Extraction
    # ────────────────────────────────────────────────

    def _extract_facts(self, content: str) -> List[str]:
        """
        Extract learnable facts from content.
        Uses LLM if available, falls back to rule-based extraction.
        """
        # Try LLM extraction first
        if self._llm_generate:
            try:
                prompt = EXTRACT_FACTS_PROMPT.format(content=content[:1500])
                response = self._llm_generate(prompt)
                # Parse JSON array from response
                facts = json.loads(response.strip())
                if isinstance(facts, list):
                    return [str(f) for f in facts if f]
            except Exception:
                pass

        # Fallback: rule-based extraction
        return self._rule_based_extract(content)

    def _rule_based_extract(self, content: str) -> List[str]:
        """Simple rule-based fact extraction (no LLM needed)."""
        facts = []
        lines = content.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Look for declarative statements
            lower = line.lower()

            # Preference patterns
            for pattern in ["i prefer", "i like", "i use", "i want",
                          "my favorite", "my name is", "i work",
                          "our project", "we use", "the project"]:
                if pattern in lower:
                    # Clean up the fact
                    fact = line
                    if fact.startswith("USER: "):
                        fact = fact[6:]
                    facts.append(fact)
                    break

            # Definition patterns
            for pattern in [" is ", " means ", " refers to ", " is defined as "]:
                if pattern in lower and len(line) < 200:
                    fact = line
                    if fact.startswith("USER: "):
                        fact = fact[6:]
                    if fact.startswith("AGENT: "):
                        fact = fact[7:]
                    facts.append(fact)
                    break

        # Deduplicate
        return list(dict.fromkeys(facts))

    def _text_similarity(self, a: str, b: str) -> float:
        """Quick text similarity using word overlap (Jaccard)."""
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)

    # ────────────────────────────────────────────────
    #  Stats
    # ────────────────────────────────────────────────

    def get_stats(self) -> ContinualLearnerStats:
        """Get statistics about the continual learner."""
        # Calculate growth rate
        growth_rate = 0.0
        if self._daily_counts:
            total_days = len(self._daily_counts)
            total_entries = sum(self._daily_counts.values())
            growth_rate = total_entries / max(total_days, 1)

        return ContinualLearnerStats(
            total_events_processed=self._events_processed,
            facts_extracted=self._facts_extracted,
            corrections_applied=self._corrections_applied,
            consolidations_run=self._consolidations_run,
            last_consolidation=(
                self._last_consolidation.isoformat()
                if self._last_consolidation else None
            ),
            knowledge_growth_rate=growth_rate,
        )
