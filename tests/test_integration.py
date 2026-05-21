"""
Tests for Layer 2 Step 4: Claim Integration

Verifies locked rules:
1. Reinforce if claim confidence >= 0.6
2. Contradict if claim confidence < 0.4
3. New entity created at low confidence (claim * 0.5)
4. Uncertain claim (0.4-0.6) does nothing to existing
5. Integration does NOT compute coherence
6. State timestamp updates
"""

import pytest
from datetime import datetime

from src.cognition.belief_state import BeliefState
from src.cognition.claim import Claim
from src.cognition.integration import integrate_claim
from src.cognition.entity import Entity
from src.cognition.relation import Relation
from src.learning.policy import LearningPolicy


class TestEntityIntegration:
    """Tests for entity claim integration."""
    
    def test_new_entity_creation(self):
        """Rule 2: New entity created at low confidence."""
        state = BeliefState.create_empty()
        claim = Claim(
            type="entity",
            content="Owner exists",
            target_id="e1",
            confidence=0.8,
            source="test",
            timestamp=datetime.now(),
            payload={"name": "Owner", "type": "person"}
        )
        
        integrate_claim(state, claim)
        
        assert state.entity_count() == 1
        entity = state.get_entity("e1")
        assert entity.name == "Owner"
        # Initial conf = claim(0.8) * 0.5 = 0.4
        assert entity.confidence == pytest.approx(0.4)
    
    def test_existing_entity_reinforcement(self):
        """Rule 1a: Reinforce if confidence >= 0.6."""
        state = BeliefState.create_empty()
        # Setup existing entity
        e1 = Entity.create(type="p", name="Ow", source="prev", confidence=0.5)
        e1.id = "e1"
        state.add_entity(e1)
        
        claim = Claim(
            type="entity",
            content="Owner still here",
            target_id="e1",
            confidence=0.9,
            source="vision",
            timestamp=datetime.now()
        )
        
        integrate_claim(state, claim)
        
        assert state.get_entity("e1").confidence > 0.5
        assert state.get_entity("e1").evidence_count() > 1
    
    def test_existing_entity_contradiction(self):
        """Rule 1b: Contradict if confidence < 0.4."""
        state = BeliefState.create_empty()
        e1 = Entity.create(type="p", name="Ow", source="prev", confidence=0.8)
        e1.id = "e1"
        state.add_entity(e1)
        
        claim = Claim(
            type="entity",
            content="Owner not found",
            target_id="e1",
            confidence=0.1,
            source="sys",
            timestamp=datetime.now()
        )
        
        integrate_claim(state, claim)
        
        assert state.get_entity("e1").confidence < 0.8
        assert state.get_entity("e1").contradiction_count == 1
    
    def test_uncertain_claim_ignored(self):
        """Rule 1c: Ignore if 0.4 <= confidence < 0.6."""
        state = BeliefState.create_empty()
        e1 = Entity.create(type="p", name="Ow", source="prev", confidence=0.8)
        e1.id = "e1"
        state.add_entity(e1)
        
        claim = Claim(
            type="entity",
            content="Maybe owner?",
            target_id="e1",
            confidence=0.5,
            source="uncertain",
            timestamp=datetime.now()
        )
        
        integrate_claim(state, claim)
        
        assert state.get_entity("e1").confidence == 0.8  # Unchanged
        assert state.get_entity("e1").evidence_count() == 1  # No new evidence
    
    def test_low_confidence_creation_ignored(self):
        """Rule 2 variant: Do not create if claim confidence too low."""
        state = BeliefState.create_empty()
        claim = Claim(
            type="entity",
            content="Faint ghost",
            target_id="new1",
            confidence=0.3,
            source="test",
            timestamp=datetime.now()
        )
        
        integrate_claim(state, claim)
        
        assert state.entity_count() == 0


class TestIntegrationPolicy:
    """Tests for policy influence on integration."""
    
    def test_source_trust_reduces_confidence(self):
        """Untrusted source reduces effective confidence."""
        state = BeliefState.create_empty()
        # Setup untrusted policy
        policy = LearningPolicy()
        policy.source_trust["unreliable"] = 0.5
        
        # Claim has high confidence (0.8), but effective is 0.4 (0.8 * 0.5)
        # Should TRIGGER creation (>=0.4) but LOW confidence (0.4 * 0.5 = 0.2)
        # Wait, creation rule: if effective >= 0.4: init = effective * 0.5
        
        claim = Claim(
            type="entity",
            content="Ghost",
            target_id="e1",
            confidence=0.8,
            source="unreliable",
            timestamp=datetime.now()
        )
        
        integrate_claim(state, claim, policy)
        
        # It should exist
        assert state.entity_count() == 1
        entity = state.get_entity("e1")
        # Effective = 0.4. Created with 0.4 * 0.5 = 0.2
        assert entity.confidence == pytest.approx(0.2)
        
        # If trust was even lower (0.1), effective would be 0.08 -> Ignored
        policy.source_trust["bad"] = 0.1
        claim2 = Claim(
            type="entity", content="Bad", target_id="e2", confidence=0.8, source="bad", timestamp=datetime.now()
        )
        integrate_claim(state, claim2, policy)
        assert state.get_entity("e2") is None

    def test_policy_params_adjust_reinforcement(self):
        """Reinforcement uses policy parameters."""
        state = BeliefState.create_empty()
        e1 = Entity.create("p", "O", "trusted", 0.6)
        e1.id = "e1"
        state.add_entity(e1)
        
        policy = LearningPolicy()
        # Custom params: huge slope
        policy.reinforcement_base = 0.1
        policy.reinforcement_slope = 1.0 
        
        claim = Claim(
            type="entity", content="Exists", target_id="e1", confidence=0.8, source="trusted", timestamp=datetime.now()
        )
        # Trust default 1.0. Effective = 0.8.
        # Strength = base + (0.8 - 0.6) * slope
        #          = 0.1  + 0.2 * 1.0 = 0.3
        
        integrate_claim(state, claim, policy)
        
        # Expected new confidence: 0.6 + 0.3(1 - 0.6) = 0.6 + 0.12 = 0.72
        assert state.get_entity("e1").confidence == pytest.approx(0.72)


class TestRelationIntegration:
    """Tests for relation claim integration."""
    
    def test_new_relation_creation(self):
        """Rule 2: New relation created at low confidence."""
        state = BeliefState.create_empty()
        claim = Claim(
            type="relation",
            content="A connects B",
            target_id="r1",
            confidence=0.8,
            source="test",
            timestamp=datetime.now(),
            payload={"subject_id": "a", "predicate": "to", "object_id": "b"}
        )
        
        integrate_claim(state, claim)
        
        assert state.relation_count() == 1
        rel = state.relations[0]
        assert rel.id == "r1"
        assert rel.confidence == pytest.approx(0.4)
    
    def test_existing_relation_update(self):
        """Rule 1a: Reinforce existing relation."""
        state = BeliefState.create_empty()
        r1 = Relation.create("a", "p", "b", "test", confidence=0.5)
        r1.id = "r1"
        state.add_relation(r1)
        
        claim = Claim(
            type="relation",
            content="Confirmed",
            target_id="r1",
            confidence=0.8,
            source="test",
            timestamp=datetime.now()
        )
        
        integrate_claim(state, claim)
        
        assert state.relations[0].confidence > 0.5


class TestIntegrationConstraints:
    """Tests for negative constraints."""
    
    def test_no_coherence_computation(self):
        """Rule 5: Does NOT compute coherence (score remains default)."""
        state = BeliefState.create_empty()
        # Manually set wrong score to verify it's NOT updated
        state.coherence_score = 0.5
        
        claim = Claim(
            type="entity",
            content="New",
            target_id="new",
            confidence=0.9,
            source="test",
            timestamp=datetime.now(),
            payload={"name": "N", "type": "T"}
        )
        
        integrate_claim(state, claim)
        
        # Should still be 0.5 - integration shouldn't run compute_coherence
        assert state.coherence_score == 0.5
    
    def test_timestamp_updated(self):
        """State timestamp updates on mutation."""
        import time
        state = BeliefState.create_empty()
        old_ts = state.timestamp
        time.sleep(0.001)  # Ensure timestamp advances
        
        claim = Claim(
            type="entity",
            content="New",
            target_id="new",
            confidence=0.9,
            source="test",
            timestamp=datetime.now(),
            payload={"name": "N", "type": "T"}
        )
        integrate_claim(state, claim)
        
        assert state.timestamp > old_ts


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
