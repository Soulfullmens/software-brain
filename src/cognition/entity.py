"""
Entity - Belief Carrier for Things That Exist

An Entity represents something the agent believes exists in the world.
This is NOT truth - entities can be wrong, decay, and be contradicted.

RULES:
- Entities carry confidence (probabilistic, not boolean)
- Entities decay over time
- Entities track evidence
- Entities do NOTHING else (no inference, no merging, no resolution)

Decay rate: λ = 0.01 per day (slow - things don't vanish easily)
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


# Locked from spec
ENTITY_DECAY_RATE = 0.01  # per day
INACTIVE_THRESHOLD = 0.2


@dataclass
class Evidence:
    """A piece of evidence supporting or contradicting a belief."""
    source: str
    timestamp: datetime
    strength: float  # Positive for support, negative for contradiction
    
    @classmethod
    def supporting(cls, source: str, strength: float = 0.2) -> Evidence:
        """Create supporting evidence."""
        return cls(source=source, timestamp=datetime.now(), strength=abs(strength))
    
    @classmethod
    def contradicting(cls, source: str, strength: float = 0.15) -> Evidence:
        """Create contradicting evidence."""
        return cls(source=source, timestamp=datetime.now(), strength=-abs(strength))


@dataclass
class Entity:
    """
    A belief about something that exists.
    
    This is a BELIEF CARRIER, not a knowledge store.
    The entity can be wrong. It decays. It can be contradicted.
    
    NO LOGIC HERE:
    - No inference
    - No merging
    - No belief resolution
    - No world updates
    """
    id: str
    type: str                           # person, object, concept, event, place
    name: str
    
    # Properties with values (no confidence per property in v0)
    properties: dict[str, Any] = field(default_factory=dict)
    
    # Belief strength
    confidence: float = 0.8
    decay_rate: float = ENTITY_DECAY_RATE
    
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
        type: str,
        name: str,
        source: str,
        confidence: float = 0.8,
        properties: Optional[dict[str, Any]] = None,
    ) -> Entity:
        """Create a new entity belief."""
        now = datetime.now()
        entity = cls(
            id=str(uuid.uuid4()),
            type=type,
            name=name,
            properties=properties or {},
            confidence=confidence,
            created_at=now,
            last_reinforced=now,
            last_accessed=now,
        )
        # Initial evidence
        entity.evidence.append(Evidence.supporting(source, 0.3))
        return entity
    
    def decay(self, now: Optional[datetime] = None) -> float:
        """
        Apply exponential decay.
        
        Uses: confidence(t) = confidence₀ × e^(−λΔt)
        Reference time is max(last_reinforced, last_accessed).
        """
        now = now or datetime.now()
        reference = max(self.last_reinforced, self.last_accessed)
        delta_days = (now - reference).total_seconds() / 86400
        self.confidence = self.confidence * math.exp(-self.decay_rate * delta_days)
        return self.confidence
    
    def reinforce(self, strength: float, source: str) -> float:
        """
        Reinforce this entity belief.
        
        Uses: new = old + α(1 - old)
        This prevents runaway certainty.
        """
        self.confidence = self.confidence + strength * (1.0 - self.confidence)
        self.last_reinforced = datetime.now()
        self.evidence.append(Evidence.supporting(source, strength))
        return self.confidence
    
    def contradict(self, penalty: float, source: str) -> float:
        """
        Contradict this entity belief.
        
        Reduces confidence and increments contradiction count.
        """
        self.confidence = max(0.0, self.confidence - penalty)
        self.contradiction_count += 1
        self.evidence.append(Evidence.contradicting(source, penalty))
        return self.confidence
    
    def access(self) -> None:
        """Mark this entity as accessed (affects decay reference)."""
        self.last_accessed = datetime.now()
    
    def is_active(self) -> bool:
        """Check if entity is above inactive threshold."""
        return self.confidence >= INACTIVE_THRESHOLD
    
    def is_reliable(self) -> bool:
        """Check if entity is reliable (high confidence, low contradictions)."""
        return self.confidence >= 0.6 and self.contradiction_count < 3
    
    def set_property(self, key: str, value: Any) -> None:
        """Set a property value."""
        self.properties[key] = value
    
    def get_property(self, key: str, default: Any = None) -> Any:
        """Get a property value."""
        return self.properties.get(key, default)
    
    def evidence_count(self) -> int:
        """Count total evidence pieces."""
        return len(self.evidence)
    
    def supporting_evidence_count(self) -> int:
        """Count supporting evidence."""
        return sum(1 for e in self.evidence if e.strength > 0)
    
    def contradicting_evidence_count(self) -> int:
        """Count contradicting evidence."""
        return sum(1 for e in self.evidence if e.strength < 0)
