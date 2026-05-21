"""
BeliefState - The Core Container

This is the central data structure for the World Model.
It holds the agent's current understanding of reality.

RULES:
- This is a DATA CONTAINER, not a logic engine
- No decision-making here
- No auto-resolution of contradictions
- No planning, no learning, no perception

The BeliefState answers:
- What entities exist?
- What relations hold?
- What predictions are active?
- What contradictions are unresolved?
- How coherent is this overall?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Union
import uuid

# Full object types
from .entity import Entity
from .relation import Relation
from .prediction import Prediction
from src.core.identity import Identity





@dataclass
class ContradictionRef:
    """Lightweight reference to a contradiction."""
    id: str
    belief_a: str
    belief_b: str
    urgency: float
    blocking: bool = False
    detected_at: datetime = field(default_factory=datetime.now)


@dataclass
class BeliefState:
    """
    The complete belief state at a moment in time.
    
    This is ONLY a container. It holds:
    - Entities (things that exist)
    - Relations (connections between entities)
    - Predictions (what we expect)
    - Contradictions (unresolved conflicts)
    - Coherence score (overall state quality)
    
    INVARIANTS:
    - coherence_score is always in [0.0, 1.0]
    - timestamp reflects when this state was created/updated
    - All collections can be empty
    """
    
    # When this belief state was created/last updated
    timestamp: datetime
    
    # The agent this state belongs to (Layer 0 anchor)
    identity: Optional[Identity] = None
    
    # Entities: things that exist in the understood world
    
    # Entities: things that exist in the understood world
    # Key = entity_id, Value = Entity object
    entities: dict[str, Entity] = field(default_factory=dict)
    
    # Relations: connections between entities
    relations: list[Relation] = field(default_factory=list)
    
    # Active predictions about what will happen
    predictions: list[Prediction] = field(default_factory=list)
    
    # Unresolved contradictions
    contradictions: list[ContradictionRef] = field(default_factory=list)
    
    # How coherent is this belief state (0.0 - 1.0)
    # Calculated by coherence engine, not set manually
    coherence_score: float = 1.0
    
    # Optional: pending questions for owner
    pending_questions: list[str] = field(default_factory=list)
    
    @classmethod
    def create_empty(cls, identity: Optional[Identity] = None) -> BeliefState:
        """Create a fresh, empty belief state."""
        return cls(
            timestamp=datetime.now(),
            coherence_score=1.0,  # Empty state is fully coherent
            identity=identity
        )
    
    # =========== ENTITY OPERATIONS (CONTAINER ONLY) ===========
    
    def add_entity(self, entity: Entity) -> None:
        """Add or update an entity."""
        self.entities[entity.id] = entity
        self.timestamp = datetime.now()
    
    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get an entity by ID."""
        return self.entities.get(entity_id)
    
    def remove_entity(self, entity_id: str) -> bool:
        """Remove an entity. Returns True if removed."""
        if entity_id in self.entities:
            del self.entities[entity_id]
            self.timestamp = datetime.now()
            return True
        return False
    
    def entity_count(self) -> int:
        """Count entities."""
        return len(self.entities)
    
    # =========== RELATION OPERATIONS (CONTAINER ONLY) ===========
    
    def add_relation(self, relation: Relation) -> None:
        """Add a relation."""
        self.relations.append(relation)
        self.timestamp = datetime.now()
    
    def get_relations_for(self, entity_id: str) -> list[Relation]:
        """Get all relations involving an entity."""
        return [
            r for r in self.relations
            if r.subject_id == entity_id or r.object_id == entity_id
        ]
    
    def relation_count(self) -> int:
        """Count relations."""
        return len(self.relations)
    
    # =========== PREDICTION OPERATIONS (CONTAINER ONLY) ===========
    
    def add_prediction(self, prediction: Prediction) -> None:
        """Add a prediction."""
        self.predictions.append(prediction)
        self.timestamp = datetime.now()
    
    def get_active_predictions(self) -> list[Prediction]:
        """Get predictions that haven't been resolved."""
        return [p for p in self.predictions if p.outcome is None]
    
    def prediction_count(self) -> int:
        """Count all predictions."""
        return len(self.predictions)
    
    # =========== CONTRADICTION OPERATIONS (CONTAINER ONLY) ===========
    
    def add_contradiction(self, contradiction: ContradictionRef) -> None:
        """Add a contradiction."""
        self.contradictions.append(contradiction)
        self.timestamp = datetime.now()
    
    def get_blocking_contradictions(self) -> list[ContradictionRef]:
        """Get contradictions that block action."""
        return [c for c in self.contradictions if c.blocking]
    
    def contradiction_count(self) -> int:
        """Count contradictions."""
        return len(self.contradictions)
    
    # =========== STATE QUERIES (NO LOGIC) ===========
    
    def is_coherent(self, threshold: float = 0.5) -> bool:
        """Check if coherence is above threshold."""
        return self.coherence_score >= threshold
    
    def is_healthy(self) -> bool:
        """Check if state is in normal operating range (coherence > 0.8)."""
        return self.coherence_score > 0.8
    
    def needs_owner_input(self) -> bool:
        """Check if state has pending questions or low coherence."""
        return len(self.pending_questions) > 0 or self.coherence_score < 0.5
    
    def summary(self) -> dict[str, Any]:
        """Get a summary of the belief state."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "entity_count": self.entity_count(),
            "relation_count": self.relation_count(),
            "prediction_count": self.prediction_count(),
            "contradiction_count": self.contradiction_count(),
            "coherence_score": self.coherence_score,
            "is_healthy": self.is_healthy(),
            "pending_questions": len(self.pending_questions),
        }
