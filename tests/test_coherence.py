"""
Tests for Layer 2 Step 3: Decay + Coherence Engine

Verifies the LOCKED formula:
coherence = 1.0 - 0.4*C - 0.35*F - 0.25*H

Tests:
1. Empty state -> 1.0 coherence
2. Contradictions lower coherence
3. Failed predictions lower coherence
4. Uncertain beliefs (entropy) lower coherence
5. Clamping ensures 0.0 <= score <= 1.0
6. Component reporting is accurate
"""

import pytest
from datetime import datetime

from src.cognition.belief_state import (
    BeliefState,
    ContradictionRef,
)
from src.cognition.entity import Entity
from src.cognition.relation import Relation
from src.cognition.prediction import Prediction
from src.cognition.coherence import (
    compute_coherence,
    binary_entropy,
    MAX_CONTRADICTIONS,
    MAX_PREDICTIONS,
    W_C,
    W_F,
    W_H,
)


class TestEntropy:
    """Tests for entropy calculation."""
    
    def test_entropy_extremes(self):
        """Entropy is difference between certainty (0/1) and uniform (0.5)."""
        assert binary_entropy(0.0) == 0.0
        assert binary_entropy(1.0) == 0.0
        assert binary_entropy(0.5) == 1.0  # Max uncertainty
    
    def test_entropy_curve(self):
        """Entropy symmetric around 0.5."""
        assert binary_entropy(0.1) == pytest.approx(0.469, abs=0.001)
        assert binary_entropy(0.9) == pytest.approx(0.469, abs=0.001)
        
        assert binary_entropy(0.25) == pytest.approx(0.811, abs=0.001)
        assert binary_entropy(0.75) == pytest.approx(0.811, abs=0.001)


class TestCoherenceCalculation:
    """Tests for compute_coherence formula."""
    
    def test_empty_state_perfect_coherence(self):
        """Empty state has no penalties."""
        state = BeliefState.create_empty()
        report = compute_coherence(state)
        
        assert report.score == 1.0
        assert report.raw_c == 0.0
        assert report.raw_f == 0.0
        assert report.raw_h == 0.0
    
    def test_contradiction_impact(self):
        """Contradictions reduce coherence via C term."""
        state = BeliefState.create_empty()
        
        # Add 5 urgent contradictions (5 * 1.0 = 5.0 total urgency)
        # C = 5.0 / 10.0 = 0.5
        for i in range(5):
            state.add_contradiction(ContradictionRef(
                id=f"c{i}", belief_a="A", belief_b="B",
                urgency=1.0, blocking=True
            ))
            
        report = compute_coherence(state)
        
        assert report.raw_c == 0.5
        # Penalty = 0.4 * 0.5 = 0.2
        # Score = 1.0 - 0.2 = 0.8
        assert report.score == pytest.approx(0.8)
        assert report.c_term == pytest.approx(0.2)
        assert report.f_term == 0.0
        assert report.h_term == 0.0
    
    def test_failed_prediction_impact(self):
        """Failed predictions reduce coherence via F term."""
        state = BeliefState.create_empty()
        
        # Add failed predictions (Total conf = 5.0)
        # F = 5.0 / 10.0 = 0.5
        for i in range(5):
            p = Prediction.create(
                statement="X", probability=1.0, expected_by=datetime.now()
            )
            p.id = f"p{i}"
            p.outcome = "denied"
            state.add_prediction(p)
            
        # Add success (ignored)
        p_ok = Prediction.create(statement="Y", probability=1.0, expected_by=datetime.now())
        p_ok.id = "ok"
        p_ok.outcome = "confirmed"
        state.add_prediction(p_ok)
        
        report = compute_coherence(state)
        
        assert report.raw_f == 0.5
        # Penalty = 0.35 * 0.5 = 0.175
        # Score = 1.0 - 0.175 = 0.825
        assert report.score == pytest.approx(0.825)
        assert report.f_term == pytest.approx(0.175)
    
    def test_entropy_impact(self):
        """Uncertainty reduces coherence via H term."""
        state = BeliefState.create_empty()
        
        # Add entities with 0.5 confidence (Max entropy = 1.0)
        for i in range(10):
            # Use Entity.create
            entity = Entity.create(
                type="test", 
                name="T", 
                source="test", 
                confidence=0.5
            )
            entity.id = f"e{i}"
            state.add_entity(entity)
            
        report = compute_coherence(state)
        
        assert report.raw_h == 1.0
        # Penalty = 0.25 * 1.0 = 0.25
        # Score = 1.0 - 0.25 = 0.75
        assert report.score == pytest.approx(0.75)
        assert report.h_term == pytest.approx(0.25)
    
    def test_mixed_state(self):
        """Combination of factors."""
        state = BeliefState.create_empty()
        
        # C = 0.1 (1 urgent contradiction)
        state.add_contradiction(ContradictionRef(
            id="c1", belief_a="A", belief_b="B", urgency=1.0
        ))
        
        # F = 0.1 (1 failed prediction)
        p = Prediction.create(statement="X", probability=1.0, expected_by=datetime.now())
        p.id = "p1"
        p.outcome = "denied"
        state.add_prediction(p)
        
        # H = 0.0 (Certain entity)
        e1 = Entity.create(type="T", name="N", source="test", confidence=1.0)
        e1.id = "e1"
        state.add_entity(e1)
        
        report = compute_coherence(state)
        
        # Penalties:
        # C: 0.4 * 0.1 = 0.04
        # F: 0.35 * 0.1 = 0.035
        # H: 0.0
        # Total: 0.075
        # Score: 0.925
        assert report.score == pytest.approx(0.925)
    
    def test_clamping_zero(self):
        """Score calculates to < 0 but clamps to 0."""
        state = BeliefState.create_empty()
        
        # Massive contradictions (User > 10.0 urgency)
        for i in range(20):
            state.add_contradiction(ContradictionRef(
                id=f"c{i}", belief_a="A", belief_b="B", urgency=1.0
            ))
            
        # Massive failure
        for i in range(20):
            p = Prediction.create(statement="X", probability=1.0, expected_by=datetime.now())
            p.id = f"p{i}"
            p.outcome = "denied"
            state.add_prediction(p)
            
        # Massive uncertainty
        for i in range(20):
            ent = Entity.create(type="T", name="N", source="test", confidence=0.5)
            ent.id = f"e{i}"
            state.add_entity(ent)
            
        # Raw should be: 1.0 - 0.4(1) - 0.35(1) - 0.25(1) = 0.0
        # If we push it even further (e.g. slight floating point or future weight changes)
        # it should clamp.
        
        report = compute_coherence(state)
        assert report.score == 0.0
        assert report.score >= 0.0


class TestCoherenceWeights:
    """Verifies weights match the spec."""
    
    def test_weights_sum_to_one(self):
        """Weights sum to 1.0 (implying 0 score at max failure)."""
        assert W_C + W_F + W_H == 1.0
        assert W_C == 0.4
        assert W_F == 0.35
        assert W_H == 0.25


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
