"""
Tests for Entity - Belief Carrier

Required tests:
1. Decay follows exponential formula
2. Reinforcement increases confidence but < 1.0
3. Contradiction lowers confidence and increments count
4. is_active() flips at threshold
5. Evidence list updates correctly
6. Access affects decay reference
"""

import pytest
import math
import time
from datetime import datetime, timedelta

from src.cognition.entity import Entity, Evidence, ENTITY_DECAY_RATE, INACTIVE_THRESHOLD


class TestEntityCreation:
    """Tests for entity creation."""
    
    def test_create_entity(self):
        """Can create an entity with basic properties."""
        entity = Entity.create(
            type="person",
            name="Owner",
            source="observation",
        )
        
        assert entity.type == "person"
        assert entity.name == "Owner"
        assert entity.confidence == 0.8  # Default
        assert entity.decay_rate == ENTITY_DECAY_RATE
        assert entity.evidence_count() == 1  # Initial evidence
    
    def test_create_with_properties(self):
        """Can create entity with custom properties."""
        entity = Entity.create(
            type="project",
            name="software-brain",
            source="context",
            properties={"language": "Python", "version": "0.1"},
        )
        
        assert entity.get_property("language") == "Python"
        assert entity.get_property("version") == "0.1"
        assert entity.get_property("missing") is None
    
    def test_create_with_confidence(self):
        """Can set initial confidence."""
        entity = Entity.create(
            type="concept",
            name="test",
            source="test",
            confidence=0.5,
        )
        
        assert entity.confidence == 0.5


class TestEntityDecay:
    """Tests for entity decay - CRITICAL."""
    
    def test_decay_formula_correct(self):
        """Decay follows exponential formula: c(t) = c₀ × e^(−λΔt)"""
        entity = Entity.create(type="test", name="test", source="test", confidence=1.0)
        entity.decay_rate = 0.1  # Fast for testing
        
        # Simulate 5 days
        future = datetime.now() + timedelta(days=5)
        entity.decay(future)
        
        # Expected: 1.0 * e^(-0.1 * 5) = e^(-0.5) ≈ 0.6065
        expected = math.exp(-0.1 * 5)
        assert entity.confidence == pytest.approx(expected, rel=0.01)
    
    def test_decay_with_default_rate(self):
        """Entity decay rate is slow (λ = 0.01)."""
        entity = Entity.create(type="test", name="test", source="test", confidence=0.9)
        initial = entity.confidence
        
        # After 30 days
        future = datetime.now() + timedelta(days=30)
        entity.decay(future)
        
        # e^(-0.01 * 30) ≈ 0.74
        expected = initial * math.exp(-ENTITY_DECAY_RATE * 30)
        assert entity.confidence == pytest.approx(expected, rel=0.01)
    
    def test_decay_uses_access_time(self):
        """Decay references max(last_reinforced, last_accessed)."""
        entity = Entity.create(type="test", name="test", source="test", confidence=0.9)
        entity.decay_rate = 0.1  # Fast for testing
        
        # Access the entity (should reset decay reference)
        entity.access()
        
        # Decay from now (access just happened, so minimal decay)
        entity.decay(datetime.now())
        
        # Should still be very close to original
        assert entity.confidence > 0.85


class TestEntityReinforcement:
    """Tests for entity reinforcement - CRITICAL."""
    
    def test_reinforcement_formula_correct(self):
        """Reinforcement: new = old + α(1 - old)"""
        entity = Entity.create(type="test", name="test", source="test", confidence=0.6)
        
        entity.reinforce(0.2, "confirmation")
        
        # Expected: 0.6 + 0.2*(1-0.6) = 0.6 + 0.08 = 0.68
        assert entity.confidence == pytest.approx(0.68, rel=0.01)
    
    def test_reinforcement_never_exceeds_one(self):
        """Reinforcement cannot push confidence above 1.0."""
        entity = Entity.create(type="test", name="test", source="test", confidence=0.95)
        
        for _ in range(10):
            entity.reinforce(0.3, "test")
        
        assert entity.confidence < 1.0
    
    def test_reinforcement_adds_evidence(self):
        """Reinforcement adds to evidence list."""
        entity = Entity.create(type="test", name="test", source="test")
        initial_count = entity.evidence_count()
        
        entity.reinforce(0.2, "additional_evidence")
        
        assert entity.evidence_count() == initial_count + 1
        assert entity.supporting_evidence_count() >= 2
    
    def test_reinforcement_updates_timestamp(self):
        """Reinforcement updates last_reinforced."""
        entity = Entity.create(type="test", name="test", source="test")
        old_time = entity.last_reinforced
        
        time.sleep(0.01)
        entity.reinforce(0.2, "test")
        
        assert entity.last_reinforced > old_time


class TestEntityContradiction:
    """Tests for entity contradiction - CRITICAL."""
    
    def test_contradiction_reduces_confidence(self):
        """Contradiction reduces confidence."""
        entity = Entity.create(type="test", name="test", source="test", confidence=0.8)
        
        entity.contradict(0.15, "counter_evidence")
        
        assert entity.confidence == pytest.approx(0.65, rel=0.01)
    
    def test_contradiction_increments_count(self):
        """Contradiction increments contradiction_count."""
        entity = Entity.create(type="test", name="test", source="test")
        
        assert entity.contradiction_count == 0
        entity.contradict(0.1, "test1")
        assert entity.contradiction_count == 1
        entity.contradict(0.1, "test2")
        assert entity.contradiction_count == 2
    
    def test_contradiction_floors_at_zero(self):
        """Confidence cannot go below zero."""
        entity = Entity.create(type="test", name="test", source="test", confidence=0.1)
        
        entity.contradict(0.5, "test")
        
        assert entity.confidence == 0.0
    
    def test_contradiction_adds_negative_evidence(self):
        """Contradiction adds negative evidence."""
        entity = Entity.create(type="test", name="test", source="test")
        
        entity.contradict(0.1, "disproof")
        
        assert entity.contradicting_evidence_count() >= 1


class TestEntityActive:
    """Tests for is_active() threshold - CRITICAL."""
    
    def test_below_threshold_inactive(self):
        """Entity below threshold is inactive."""
        entity = Entity.create(type="test", name="test", source="test", confidence=0.15)
        
        assert not entity.is_active()
    
    def test_at_threshold_active(self):
        """Entity at exactly threshold is active."""
        entity = Entity.create(type="test", name="test", source="test", confidence=INACTIVE_THRESHOLD)
        
        assert entity.is_active()
    
    def test_decay_causes_inactive(self):
        """Decay can push entity below threshold."""
        entity = Entity.create(type="test", name="test", source="test", confidence=0.25)
        entity.decay_rate = 0.1  # Fast for testing
        
        assert entity.is_active()
        
        # After 30 days: 0.25 * e^(-0.1 * 30) = 0.25 * e^(-3) ≈ 0.012
        future = datetime.now() + timedelta(days=30)
        entity.decay(future)
        
        assert not entity.is_active()


class TestEntityEvidence:
    """Tests for evidence tracking."""
    
    def test_initial_evidence(self):
        """Entity starts with initial evidence."""
        entity = Entity.create(type="test", name="test", source="initial_source")
        
        assert entity.evidence_count() == 1
        assert entity.evidence[0].source == "initial_source"
    
    def test_evidence_accumulates(self):
        """Evidence accumulates from reinforcement and contradiction."""
        entity = Entity.create(type="test", name="test", source="start")
        
        entity.reinforce(0.2, "support1")
        entity.reinforce(0.1, "support2")
        entity.contradict(0.1, "counter1")
        
        assert entity.evidence_count() == 4
        assert entity.supporting_evidence_count() == 3
        assert entity.contradicting_evidence_count() == 1


class TestEntityReliability:
    """Tests for reliability checks."""
    
    def test_reliable_entity(self):
        """High confidence, low contradictions = reliable."""
        entity = Entity.create(type="test", name="test", source="test", confidence=0.8)
        
        assert entity.is_reliable()
    
    def test_unreliable_low_confidence(self):
        """Low confidence = not reliable."""
        entity = Entity.create(type="test", name="test", source="test", confidence=0.5)
        
        assert not entity.is_reliable()
    
    def test_unreliable_high_contradictions(self):
        """Many contradictions = not reliable."""
        entity = Entity.create(type="test", name="test", source="test", confidence=0.8)
        entity.contradiction_count = 5
        
        assert not entity.is_reliable()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
