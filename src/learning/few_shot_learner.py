"""
Few-Shot Learner — Learn from 1-5 Examples, Remember Forever

PURPOSE: Implement human-like one-shot/few-shot learning where the agent
sees something once and recognizes it forever — WITHOUT retraining.

HOW IT WORKS:
    1. User shows the agent 1-5 examples of a concept
    2. Agent creates a "prototype" — an averaged embedding in vector space
    3. Future inputs are compared against prototypes via cosine similarity
    4. Recognition is instant (no training loop, no gradient descent)

THIS IS THE KEY INSIGHT:
    Traditional ML: Train on 10,000 images → 2 hours → recognizes cats
    Few-Shot:       Show 1 image → 0.1 seconds → recognizes cats forever

    Traditional RL: Play game 1M times → recognizes reward patterns
    Few-Shot:       Show 3 examples → instantly generalizes

ARCHITECTURE:
    ┌──────────────────────────────────────────────────────┐
    │  Few-Shot Learner                                    │
    │                                                      │
    │  ┌─────────────────┐   ┌──────────────────────────┐ │
    │  │  Prototype       │   │  Nearest-Neighbor         │ │
    │  │  Generator       │──►│  Classifier               │ │
    │  │  (1-5 examples   │   │  (cosine similarity in    │ │
    │  │   → prototype)   │   │   embedding space)        │ │
    │  └─────────────────┘   └──────────────────────────┘ │
    │           │                        ▲                  │
    │           ▼                        │                  │
    │  ┌──────────────────────────────────────────────┐    │
    │  │  Vector Memory Store (ChromaDB)               │    │
    │  │  "prototypes" collection — persistent storage  │    │
    │  └──────────────────────────────────────────────┘    │
    └──────────────────────────────────────────────────────┘

BACKED BY: Prototypical Networks (Snell et al., 2017)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..memory.vector_store import VectorMemoryStore, RetrievalResult


# ────────────────────────────────────────────────────────
#  Data Structures
# ────────────────────────────────────────────────────────

@dataclass
class Prototype:
    """A learned concept from few examples."""
    name: str
    category: str
    description: str
    examples: List[str]
    memory_id: str
    created_at: str
    recognition_count: int = 0
    last_recognized: Optional[str] = None


@dataclass
class RecognitionResult:
    """Result of trying to recognize/classify an input."""
    matched: bool
    prototype_name: Optional[str]
    confidence: float           # 0.0 - 1.0
    category: Optional[str]
    all_matches: List[Dict]     # all candidates with scores
    input_text: str


@dataclass
class LearnerStats:
    """Statistics about the few-shot learner."""
    total_prototypes: int
    categories: Dict[str, int]  # category → count
    total_recognitions: int
    most_recognized: Optional[str]


# ────────────────────────────────────────────────────────
#  Few-Shot Learner
# ────────────────────────────────────────────────────────

class FewShotLearner:
    """
    Human-like one-shot/few-shot learning engine.
    
    Show the agent 1-5 examples of anything — a concept, a pattern,
    a category, a person, a product — and it remembers forever.
    No training loops. No gradient descent. No GPU required.
    Just semantic embedding + prototype matching.
    
    USAGE:
        learner = FewShotLearner(vector_store)
        
        # Teach it (one-shot)
        learner.learn(
            name="spam_email",
            description="Unsolicited bulk commercial email",
            examples=["Buy viagra now!", "You've won $1M!!!"],
            category="email_classification"
        )
        
        # It recognizes forever
        result = learner.recognize("Amazing deal! Click here for free money!")
        # → matched=True, prototype_name="spam_email", confidence=0.82
        
        # Teach something else (one-shot again)
        learner.learn(
            name="kitkat",
            description="A chocolate wafer bar by Nestle with red wrapper",
            examples=["red wrapper chocolate", "break me off a piece"],
            category="food"
        )
        
        # Instantly recognizes
        result = learner.recognize("chocolate bar with red packaging and wafers")
        # → matched=True, prototype_name="kitkat", confidence=0.78
    """

    def __init__(
        self,
        vector_store: VectorMemoryStore,
        recognition_threshold: float = 0.50,
        strong_match_threshold: float = 0.75,
    ):
        """
        Args:
            vector_store: The vector memory store (ChromaDB backend)
            recognition_threshold: Minimum similarity to consider a match
            strong_match_threshold: Threshold for high-confidence match
        """
        self._store = vector_store
        self._recognition_threshold = recognition_threshold
        self._strong_match_threshold = strong_match_threshold
        self._prototypes: Dict[str, Prototype] = {}
        self._total_recognitions = 0

        # Load existing prototypes from store
        self._load_existing_prototypes()

    def _load_existing_prototypes(self):
        """Load prototypes that already exist in the vector store."""
        try:
            results = self._store.retrieve(
                query="PROTOTYPE",
                collection="prototypes",
                limit=1000,
                min_relevance=0.0,
            )
            for r in results:
                name = r.metadata.get("prototype_name", "")
                if name:
                    self._prototypes[name] = Prototype(
                        name=name,
                        category=r.metadata.get("category", "general"),
                        description=r.content,
                        examples=[],
                        memory_id=r.id,
                        created_at=r.metadata.get("created_at", ""),
                    )
        except Exception:
            pass  # Empty store or first run

    # ────────────────────────────────────────────────
    #  Learn — One-Shot / Few-Shot
    # ────────────────────────────────────────────────

    def learn(
        self,
        name: str,
        description: str,
        examples: Optional[List[str]] = None,
        category: str = "general",
        metadata: Optional[Dict] = None,
    ) -> Prototype:
        """
        Learn a new concept from 1-5 examples.
        
        This is the CORE of the "Small Brain + Big Memory" architecture:
        - No training loop (0 gradient updates)
        - No GPU required
        - Instant learning (< 1 second)
        - Permanent memory (never forgets)
        
        The concept is stored as a rich text prototype in the vector store.
        Future recognition uses embedding similarity — exactly like how
        Prototypical Networks work, but without the episodic training.
        
        Args:
            name: Concept name (unique identifier)
            description: What this concept is
            examples: 1-5 example descriptions or instances
            category: Category for organization
            metadata: Additional metadata
        
        Returns:
            The created Prototype
        """
        # Store in vector memory
        memory_id = self._store.store_prototype(
            name=name,
            description=description,
            category=category,
            examples=examples or [],
            metadata=metadata,
        )

        prototype = Prototype(
            name=name,
            category=category,
            description=description,
            examples=examples or [],
            memory_id=memory_id,
            created_at=datetime.now().isoformat(),
        )

        self._prototypes[name] = prototype
        return prototype

    def add_example(self, name: str, example: str) -> bool:
        """
        Add another example to an existing prototype.
        Strengthens the prototype's embedding representation.
        
        Args:
            name: Prototype name
            example: New example to add
        
        Returns:
            True if added successfully
        """
        proto = self._prototypes.get(name)
        if not proto:
            return False

        proto.examples.append(example)

        # Re-store with updated examples (new embedding includes the example)
        self._store.delete(proto.memory_id, collection="prototypes")
        new_id = self._store.store_prototype(
            name=name,
            description=proto.description,
            category=proto.category,
            examples=proto.examples,
        )
        proto.memory_id = new_id
        return True

    # ────────────────────────────────────────────────
    #  Recognize — Instant Classification
    # ────────────────────────────────────────────────

    def recognize(
        self,
        input_text: str,
        category: Optional[str] = None,
        threshold: Optional[float] = None,
    ) -> RecognitionResult:
        """
        Recognize/classify an input against learned prototypes.
        
        No retraining. No forward pass through a neural network.
        Just embedding similarity search — instant and accurate.
        
        Args:
            input_text: The text to recognize/classify
            category: Optional category filter
            threshold: Override recognition threshold
        
        Returns:
            RecognitionResult with match info
        """
        self._total_recognitions += 1
        thresh = threshold or self._recognition_threshold

        matches = self._store.match_prototype(
            query=input_text,
            category=category,
            threshold=thresh,
        )

        all_matches = []
        for m in matches:
            proto_name = m.metadata.get("prototype_name", "unknown")
            all_matches.append({
                "name": proto_name,
                "confidence": m.relevance_score,
                "category": m.metadata.get("category", "general"),
            })

        if not all_matches:
            return RecognitionResult(
                matched=False,
                prototype_name=None,
                confidence=0.0,
                category=None,
                all_matches=[],
                input_text=input_text,
            )

        best = all_matches[0]

        # Update recognition count
        if best["name"] in self._prototypes:
            self._prototypes[best["name"]].recognition_count += 1
            self._prototypes[best["name"]].last_recognized = datetime.now().isoformat()

        return RecognitionResult(
            matched=True,
            prototype_name=best["name"],
            confidence=best["confidence"],
            category=best["category"],
            all_matches=all_matches,
            input_text=input_text,
        )

    # ────────────────────────────────────────────────
    #  Query & Management
    # ────────────────────────────────────────────────

    def list_prototypes(self, category: Optional[str] = None) -> List[Prototype]:
        """List all learned prototypes, optionally filtered by category."""
        protos = list(self._prototypes.values())
        if category:
            protos = [p for p in protos if p.category == category]
        return protos

    def get_prototype(self, name: str) -> Optional[Prototype]:
        """Get a specific prototype by name."""
        return self._prototypes.get(name)

    def forget(self, name: str) -> bool:
        """Remove a learned prototype (intentional forgetting)."""
        proto = self._prototypes.pop(name, None)
        if proto:
            self._store.delete(proto.memory_id, collection="prototypes")
            return True
        return False

    def get_stats(self) -> LearnerStats:
        """Get statistics about the few-shot learner."""
        categories: Dict[str, int] = {}
        most_recognized = None
        max_recognitions = 0

        for proto in self._prototypes.values():
            cat = proto.category
            categories[cat] = categories.get(cat, 0) + 1
            if proto.recognition_count > max_recognitions:
                max_recognitions = proto.recognition_count
                most_recognized = proto.name

        return LearnerStats(
            total_prototypes=len(self._prototypes),
            categories=categories,
            total_recognitions=self._total_recognitions,
            most_recognized=most_recognized,
        )
