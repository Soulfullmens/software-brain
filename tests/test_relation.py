"""
Tests for Relation - Belief Carrier for Connections

Required tests:
1. Decay follows exponential formula
2. Reinforcement increases confidence but < 1.0
3. Contradiction lowers confidence and increments count
4. is_active() flips at threshold
5. Faster decay than Entity
6. Can exist independently of Entity object
"""

import pytest
import math
import time
from datetime import datetime, timedelta

from src.cognition.relation import (
    Relation,
    RELATION_DECAY_RATE,
    INACTIVE_THRESHOLD,
    TemporalScope,
)
from src.cognition.entity import ENTITY_DECAY_RATE


class TestRelationCreation:
    """Tests for relation creation."""
    
    def test_create_relation(self):
        """Can create a relation with basic properties."""
        relation = Relation.create(
            subject_id="owner_1",
            predicate="works_on",
            object_id="project_1",
            source="observation",
        )
        
        assert relation.subject_id == "owner_1"
        assert relation.predicate == "works_on"
        assert relation.object_id == "project_1"
        assert relation.confidence == 0.7  # Default lower than entity
        assert relation.decay_rate == RELATION_DECAY_RATE
        assert relation.evidence_count() == 1
    
    def test_create_with_temporal_scope(self):
        """Can set temporal scope."""
        relation = Relation.create(
            subject_id="a",
            predicate="knew",
            object_id="b",
            source="history",
            temporal=TemporalScope.PAST,
        )
        
        assert relation.temporal == TemporalScope.PAST
    
    def test_relation_triple(self):
        """Can get (subject, predicate, object) triple."""
        relation = Relation.create("s", "p", "o", "test")
        
        assert relation.triple() == ("s", "p", "o")


class TestRelationDecayFasterThanEntity:
    """Tests for relation decay being faster than entity - CRITICAL."""
    
    def test_decay_rate_higher_than_entity(self):
        """Relation decay rate is higher than entity decay rate."""
        assert RELATION_DECAY_RATE > ENTITY_DECAY_RATE
        # Relation: 0.07, Entity: 0.01
        assert RELATION_DECAY_RATE == 0.07
        assert ENTITY_DECAY_RATE == 0.01
    
    def test_relation_decays_faster(self):
        """Given same initial confidence, relation decays faster."""
        from src.cognition.entity import Entity
        
        entity = Entity.create(type="test", name="test", source="test", confidence=0.8)
        relation = Relation.create("a", "rel", "b", "test", confidence=0.8)
        
        # After 10 days
        future = datetime.now() + timedelta(days=10)
        entity.decay(future)
        relation.decay(future)
        
        # Relation should have decayed more
        assert relation.confidence < entity.confidence


class TestRelationDecay:
    """Tests for relation decay."""
    
    def test_decay_formula_correct(self):
        """Decay follows exponential formula."""
        relation = Relation.create("a", "rel", "b", "test", confidence=1.0)
        
        # Simulate 5 days
        future = datetime.now() + timedelta(days=5)
        relation.decay(future)
        
        # Expected: 1.0 * e^(-0.07 * 5) = e^(-0.35) ≈ 0.705
        expected = math.exp(-RELATION_DECAY_RATE * 5)
        assert relation.confidence == pytest.approx(expected, rel=0.01)
    
    def test_decay_uses_access_time(self):
        """Decay references max(last_reinforced, last_accessed)."""
        relation = Relation.create("a", "rel", "b", "test", confidence=0.8)
        
        # Access the relation
        relation.access()
        
        # Decay from now (access just happened)
        relation.decay(datetime.now())
        
        # Should still be close to original
        assert relation.confidence > 0.75


class TestRelationReinforcement:
    """Tests for relation reinforcement."""
    
    def test_reinforcement_formula_correct(self):
        """Reinforcement: new = old + α(1 - old)"""
        relation = Relation.create("a", "rel", "b", "test", confidence=0.5)
        
        relation.reinforce(0.2, "confirmation")
        
        # Expected: 0.5 + 0.2*(1-0.5) = 0.5 + 0.1 = 0.6
        assert relation.confidence == pytest.approx(0.6, rel=0.01)
    
    def test_reinforcement_never_exceeds_one(self):
        """Reinforcement cannot push confidence above 1.0."""
        relation = Relation.create("a", "rel", "b", "test", confidence=0.95)
        
        for _ in range(10):
            relation.reinforce(0.3, "test")
        
        assert relation.confidence < 1.0
    
    def test_reinforcement_adds_evidence(self):
        """Reinforcement adds to evidence list."""
        relation = Relation.create("a", "rel", "b", "test")
        initial = relation.evidence_count()
        
        relation.reinforce(0.2, "evidence")
        
        assert relation.evidence_count() == initial + 1


class TestRelationContradiction:
    """Tests for relation contradiction."""
    
    def test_contradiction_reduces_confidence(self):
        """Contradiction reduces confidence."""
        relation = Relation.create("a", "rel", "b", "test", confidence=0.8)
        
        relation.contradict(0.2, "counter")
        
        assert relation.confidence == pytest.approx(0.6, rel=0.01)
    
    def test_contradiction_increments_count(self):
        """Contradiction increments contradiction_count."""
        relation = Relation.create("a", "rel", "b", "test")
        
        assert relation.contradiction_count == 0
        relation.contradict(0.1, "test1")
        assert relation.contradiction_count == 1
        relation.contradict(0.1, "test2")
        assert relation.contradiction_count == 2
    
    def test_contradiction_floors_at_zero(self):
        """Confidence cannot go below zero."""
        relation = Relation.create("a", "rel", "b", "test", confidence=0.1)
        
        relation.contradict(0.5, "test")
        
        assert relation.confidence == 0.0


class TestRelationActive:
    """Tests for is_active() threshold."""
    
    def test_below_threshold_inactive(self):
        """Relation below threshold is inactive."""
        relation = Relation.create("a", "rel", "b", "test", confidence=0.15)
        
        assert not relation.is_active()
    
    def test_at_threshold_active(self):
        """Relation at exactly threshold is active."""
        relation = Relation.create("a", "rel", "b", "test", confidence=INACTIVE_THRESHOLD)
        
        assert relation.is_active()
    
    def test_decay_causes_inactive(self):
        """Decay can push relation below threshold."""
        relation = Relation.create("a", "rel", "b", "test", confidence=0.3)
        
        assert relation.is_active()
        
        # After 20 days: 0.3 * e^(-0.07 * 20) = 0.3 * e^(-1.4) ≈ 0.074
        future = datetime.now() + timedelta(days=20)
        relation.decay(future)
        
        assert not relation.is_active()


class TestRelationIndependence:
    """Tests for relation independence from Entity objects."""
    
    def test_relation_exists_without_entity_objects(self):
        """Relation can exist with just entity IDs."""
        # We only have IDs, no actual Entity objects
        relation = Relation.create(
            subject_id="nonexistent_entity_1",
            predicate="imagines",
            object_id="nonexistent_entity_2",
            source="test",
        )
        
        # This is valid - relation doesn't check entity existence
        assert relation.subject_id == "nonexistent_entity_1"
        assert relation.is_active()
    
    def test_involves_entity(self):
        """Can check if relation involves an entity."""
        relation = Relation.create("e1", "rel", "e2", "test")
        
        assert relation.involves("e1")
        assert relation.involves("e2")
        assert not relation.involves("e3")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
