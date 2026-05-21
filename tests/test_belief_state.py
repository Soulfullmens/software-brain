"""
Tests for Layer 2 Step 1: BeliefState

These tests verify that BeliefState is a proper DATA CONTAINER:
- Holds entities, relations, predictions, contradictions
- Tracks coherence score
- Updates timestamp on changes
- NO LOGIC (no auto-resolution, no planning, no learning)

INVARIANTS:
- coherence_score is always in [0.0, 1.0]
- Empty state has coherence = 1.0
- Timestamp updates on mutations
"""

import pytest
from datetime import datetime, timedelta
import time

from src.cognition.belief_state import (
    BeliefState,
    ContradictionRef,
)
from src.cognition.entity import Entity
from src.cognition.relation import Relation
from src.cognition.prediction import Prediction


class TestBeliefStateCreation:
    """Tests for creating belief states."""
    
    def test_create_empty(self):
        """Empty belief state is valid and coherent."""
        state = BeliefState.create_empty()
        
        assert state.coherence_score == 1.0
        assert state.entity_count() == 0
        assert state.relation_count() == 0
        assert state.prediction_count() == 0
        assert state.contradiction_count() == 0
        assert state.is_healthy()
    
    def test_timestamp_set_on_creation(self):
        """Timestamp is set on creation."""
        before = datetime.now()
        state = BeliefState.create_empty()
        after = datetime.now()
        
        assert before <= state.timestamp <= after


class TestEntityOperations:
    """Tests for entity container operations."""
    
    def test_add_entity(self):
        """Can add an entity."""
        state = BeliefState.create_empty()
        # Use Entity.create or direct instantiation
        entity = Entity.create(
            type="person",
            name="Owner",
            source="test",
            confidence=0.9,
        )
        entity.id = "e1"  # Force ID for test
        
        state.add_entity(entity)
        
        assert state.entity_count() == 1
        assert state.get_entity("e1") is not None
        assert state.get_entity("e1").name == "Owner"
    
    def test_update_entity(self):
        """Adding entity with same ID updates it."""
        state = BeliefState.create_empty()
        
        e1 = Entity.create(type="person", name="Owner", source="test", confidence=0.9)
        e1.id = "e1"
        state.add_entity(e1)
        
        e1_updated = Entity.create(type="person", name="Owner Updated", source="test", confidence=0.95)
        e1_updated.id = "e1"
        state.add_entity(e1_updated)
        
        assert state.entity_count() == 1
        assert state.get_entity("e1").name == "Owner Updated"
    
    def test_remove_entity(self):
        """Can remove an entity."""
        state = BeliefState.create_empty()
        entity = Entity.create(type="object", name="Test", source="test", confidence=0.8)
        entity.id = "e1"
        state.add_entity(entity)
        
        result = state.remove_entity("e1")
        
        assert result is True
        assert state.entity_count() == 0
        assert state.get_entity("e1") is None
    
    def test_remove_nonexistent_entity(self):
        """Removing nonexistent entity returns False."""
        state = BeliefState.create_empty()
        
        result = state.remove_entity("nonexistent")
        
        assert result is False
    
    def test_get_nonexistent_entity(self):
        """Getting nonexistent entity returns None."""
        state = BeliefState.create_empty()
        
        assert state.get_entity("nonexistent") is None


class TestRelationOperations:
    """Tests for relation container operations."""
    
    def test_add_relation(self):
        """Can add a relation."""
        state = BeliefState.create_empty()
        relation = Relation.create(
            subject_id="e1",
            predicate="works_on",
            object_id="e2",
            source="test",
            confidence=0.8,
        )
        
        state.add_relation(relation)
        
        assert state.relation_count() == 1
    
    def test_get_relations_for_entity(self):
        """Can get relations involving an entity."""
        state = BeliefState.create_empty()
        
        r1 = Relation.create("e1", "knows", "e2", "test", confidence=0.8)
        r2 = Relation.create("e2", "helps", "e1", "test", confidence=0.7)
        r3 = Relation.create("e3", "ignores", "e4", "test", confidence=0.6)
        
        state.add_relation(r1)
        state.add_relation(r2)
        state.add_relation(r3)
        
        e1_relations = state.get_relations_for("e1")
        
        assert len(e1_relations) == 2
        assert all(r.subject_id == "e1" or r.object_id == "e1" for r in e1_relations)


class TestPredictionOperations:
    """Tests for prediction container operations."""
    
    def test_add_prediction(self):
        """Can add a prediction."""
        state = BeliefState.create_empty()
        prediction = Prediction.create(
            statement="Owner will test the code",
            probability=0.7,
            expected_by=datetime.now() + timedelta(hours=1),
        )
        prediction.id = "p1"
        
        state.add_prediction(prediction)
        
        assert state.prediction_count() == 1
    
    def test_get_active_predictions(self):
        """Can get predictions without outcomes."""
        state = BeliefState.create_empty()
        
        p1 = Prediction.create(statement="A", probability=0.8, expected_by=datetime.now())
        p2 = Prediction.create(statement="B", probability=0.7, expected_by=datetime.now())
        p2.outcome = "confirmed"
        p3 = Prediction.create(statement="C", probability=0.6, expected_by=datetime.now())
        
        state.add_prediction(p1)
        state.add_prediction(p2)
        state.add_prediction(p3)
        
        active = state.get_active_predictions()
        
        assert len(active) == 2
        assert all(p.outcome is None for p in active)


class TestContradictionOperations:
    """Tests for contradiction container operations."""
    
    def test_add_contradiction(self):
        """Can add a contradiction."""
        state = BeliefState.create_empty()
        contradiction = ContradictionRef(
            id="c1",
            belief_a="Owner is busy",
            belief_b="Owner is free",
            urgency=0.8,
            blocking=False,
        )
        
        state.add_contradiction(contradiction)
        
        assert state.contradiction_count() == 1
    
    def test_get_blocking_contradictions(self):
        """Can get blocking contradictions."""
        state = BeliefState.create_empty()
        
        c1 = ContradictionRef(id="c1", belief_a="A", belief_b="B", urgency=0.5, blocking=False)
        c2 = ContradictionRef(id="c2", belief_a="C", belief_b="D", urgency=0.9, blocking=True)
        c3 = ContradictionRef(id="c3", belief_a="E", belief_b="F", urgency=0.7, blocking=True)
        
        state.add_contradiction(c1)
        state.add_contradiction(c2)
        state.add_contradiction(c3)
        
        blocking = state.get_blocking_contradictions()
        
        assert len(blocking) == 2
        assert all(c.blocking for c in blocking)


class TestTimestampUpdates:
    """Tests for timestamp behavior."""
    
    def test_timestamp_updates_on_add_entity(self):
        """Timestamp updates when adding entity."""
        state = BeliefState.create_empty()
        old_timestamp = state.timestamp
        
        time.sleep(0.01)  # Ensure time passes
        
        entity = Entity.create(type="test", name="Test", source="test", confidence=0.9)
        state.add_entity(entity)
        
        assert state.timestamp > old_timestamp
    
    def test_timestamp_updates_on_add_relation(self):
        """Timestamp updates when adding relation."""
        state = BeliefState.create_empty()
        old_timestamp = state.timestamp
        
        time.sleep(0.01)
        
        relation = Relation.create("a", "x", "b", "test", confidence=0.8)
        state.add_relation(relation)
        
        assert state.timestamp > old_timestamp


class TestCoherenceQueries:
    """Tests for coherence-related queries."""
    
    def test_is_coherent_default(self):
        """Empty state is coherent."""
        state = BeliefState.create_empty()
        
        assert state.is_coherent(threshold=0.5)
        assert state.is_coherent(threshold=0.8)
    
    def test_is_coherent_with_low_score(self):
        """Low coherence fails threshold check."""
        state = BeliefState.create_empty()
        state.coherence_score = 0.3
        
        assert not state.is_coherent(threshold=0.5)
        assert state.is_coherent(threshold=0.2)
    
    def test_is_healthy(self):
        """Healthy requires coherence > 0.8."""
        state = BeliefState.create_empty()
        
        state.coherence_score = 0.9
        assert state.is_healthy()
        
        state.coherence_score = 0.8  # Exactly at threshold
        assert not state.is_healthy()  # Must be ABOVE
        
        state.coherence_score = 0.5
        assert not state.is_healthy()
    
    def test_needs_owner_input_low_coherence(self):
        """Needs owner input when coherence < 0.5."""
        state = BeliefState.create_empty()
        state.coherence_score = 0.4
        
        assert state.needs_owner_input()
    
    def test_needs_owner_input_pending_questions(self):
        """Needs owner input when questions pending."""
        state = BeliefState.create_empty()
        state.pending_questions.append("What did you mean?")
        
        assert state.needs_owner_input()
    
    def test_summary(self):
        """Summary returns correct structure."""
        state = BeliefState.create_empty()
        entity = Entity.create(type="test", name="Test", source="test", confidence=0.9)
        state.add_entity(entity)
        
        summary = state.summary()
        
        assert "timestamp" in summary
        assert summary["entity_count"] == 1
        assert summary["coherence_score"] == 1.0
        assert summary["is_healthy"] is True


class TestBeliefStateInvariants:
    """Tests for critical invariants."""
    
    def test_coherence_score_range(self):
        """Coherence score should be validated if set."""
        state = BeliefState.create_empty()
        
        # Valid values
        state.coherence_score = 0.0
        assert state.coherence_score == 0.0
        
        state.coherence_score = 1.0
        assert state.coherence_score == 1.0
        
        state.coherence_score = 0.5
        assert state.coherence_score == 0.5
    
    def test_empty_state_is_valid(self):
        """Empty state satisfies all invariants."""
        state = BeliefState.create_empty()
        
        assert 0.0 <= state.coherence_score <= 1.0
        assert state.timestamp is not None
        assert isinstance(state.entities, dict)
        assert isinstance(state.relations, list)
        assert isinstance(state.predictions, list)
        assert isinstance(state.contradictions, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
