"""
Relation - Belief Carrier for Connections Between Entities

A Relation represents something the agent believes about how two entities
are connected. Relations are WEAKER beliefs than entities:
- They decay faster (λ = 0.07 vs 0.01)
- They get contradicted more often
- They are ephemeral by nature

RULES:
- Relations carry confidence
- Relations decay faster than entities
- Relations track evidence
- Relations do NOTHING else (no inference, no merging, no resolution)

Decay rate: λ = 0.07 per day (faster - connections are contextual)
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum

from .entity import Evidence


# Locked from spec - FASTER than entity decay
RELATION_DECAY_RATE = 0.07  # per day
INACTIVE_THRESHOLD = 0.2


class TemporalScope(Enum):
    """When does this relation hold?"""
    PAST = "past"
    PRESENT = "present"
    ONGOING = "ongoing"
    FUTURE = "future"


@dataclass
class Relation:
    """
    A belief about a connection between two entities.
    
    Relations are WEAKER than entities. They decay faster.
    They are ephemeral and contextual.
    
    NO LOGIC HERE:
    - No entity existence checking
    - No inference
    - No automatic cleanup
    - No resolution
    """
    id: str
    subject_id: str                     # Entity doing something
    predicate: str                      # The relationship type
    object_id: str                      # Entity being acted upon
    
    # Belief strength (lower default than entity)
    confidence: float = 0.7
    decay_rate: float = RELATION_DECAY_RATE
    
    # Temporal scope
    temporal: TemporalScope = TemporalScope.PRESENT
    
    # Temporal tracking
    created_at: datetime = field(default_factory=datetime.now)
    last_reinforced: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    
    # Evidence chain
    evidence: list[Evidence] = field(default_factory=list)
    
    # Contradiction tracking
    contradiction_count: int = 0
    
    @classmethod
    def create(
        cls,
        subject_id: str,
        predicate: str,
        object_id: str,
        source: str,
        confidence: float = 0.7,
        temporal: TemporalScope = TemporalScope.PRESENT,
    ) -> Relation:
        """Create a new relation belief."""
        now = datetime.now()
        relation = cls(
            id=str(uuid.uuid4()),
            subject_id=subject_id,
            predicate=predicate,
            object_id=object_id,
            confidence=confidence,
            temporal=temporal,
            created_at=now,
            last_reinforced=now,
            last_accessed=now,
        )
        # Initial evidence
        relation.evidence.append(Evidence.supporting(source, 0.2))
        return relation
    
    def decay(self, now: Optional[datetime] = None) -> float:
        """
        Apply exponential decay.
        
        Relations decay FASTER than entities.
        Uses: confidence(t) = confidence₀ × e^(−λΔt)
        """
        now = now or datetime.now()
        reference = max(self.last_reinforced, self.last_accessed)
        delta_days = (now - reference).total_seconds() / 86400
        self.confidence = self.confidence * math.exp(-self.decay_rate * delta_days)
        return self.confidence
    
    def reinforce(self, strength: float, source: str) -> float:
        """
        Reinforce this relation belief.
        
        Uses: new = old + α(1 - old)
        """
        self.confidence = self.confidence + strength * (1.0 - self.confidence)
        self.last_reinforced = datetime.now()
        self.evidence.append(Evidence.supporting(source, strength))
        return self.confidence
    
    def contradict(self, penalty: float, source: str) -> float:
        """
        Contradict this relation belief.
        
        Reduces confidence and increments contradiction count.
        """
        self.confidence = max(0.0, self.confidence - penalty)
        self.contradiction_count += 1
        self.evidence.append(Evidence.contradicting(source, penalty))
        return self.confidence
    
    def access(self) -> None:
        """Mark this relation as accessed (affects decay reference)."""
        self.last_accessed = datetime.now()
    
    def is_active(self) -> bool:
        """Check if relation is above inactive threshold."""
        return self.confidence >= INACTIVE_THRESHOLD
    
    def involves(self, entity_id: str) -> bool:
        """Check if this relation involves a specific entity."""
        return self.subject_id == entity_id or self.object_id == entity_id
    
    def triple(self) -> tuple[str, str, str]:
        """Return the (subject, predicate, object) triple."""
        return (self.subject_id, self.predicate, self.object_id)
    
    def evidence_count(self) -> int:
        """Count total evidence pieces."""
        return len(self.evidence)
