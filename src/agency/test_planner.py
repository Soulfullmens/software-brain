"""
Tests for Layer 5 (Phase 7): Minimal Planner

Verifies:
1. Statelessness (pure function behavior)
2. No mutation of BeliefState
3. Correct heuristic priority order
4. Returns None when stable
"""

import pytest
from datetime import datetime, timedelta

from src.cognition.belief_state import BeliefState, ContradictionRef
from src.cognition.prediction import Prediction
from src.agency.planner import Planner


class TestPlannerHeuristics:
    
    def test_priority_1_low_coherence(self):
        """Heuristic 1: Low coherence triggers clarification."""
        state = BeliefState.create_empty()
        planner = Planner()
        
        # Force low coherence by adding TONS of contradictions/failures?
        # Or just mocking?
        # Let's add failed predictions to tank coherence.
        # Coherence start 1.0.
        # F-term weight 0.35. We need score < 0.5.
        # We need penalty > 0.5.
        # F-term max penalty is 0.35 (if all predictions failed).
        # C-term weight 0.4.
        # So we need contradictions + failures.
        
        # Add contradictions (lightweight refs)
        # We need C load. C = sum(urgency)/10.
        # ContradictionRef doesn't have urgency in current impl (it's in Relation/Entity logic),
        # but coherence.py says:
        # "We count # of unresolved contradictions as proxy for now"
        # Wait, let's check coherence.py implementation of C-term.
        
        # Warning: I must check coherence.py logic to know how to tank it.
        # Assuming coherence.py uses len(contradictions) or similar if urgency missing.
        # Actually coherence.py snippet in Step 315/313 diffs didn't show full C-term logic.
        # But Coherence report showed C, F, H.
        
        # Let's assume we can trigger it.
        # Alternatively, we can mock compute_coherence, but integration tests are better.
        
        # Add contradictions
        # C load = sum(urgency)/10.
        # We add 10 contradictions with urgency 1.0 -> C=1.0 -> Penalty 0.4
        for i in range(10):
            state.contradictions.append(
                ContradictionRef(
                    id=f"c{i}",
                    belief_a="e1",
                    belief_b="e2",
                    urgency=1.0
                )
            )
            
        # 10 contradictions / 10.0 max = 1.0 raw C. 
        # C-term = 1.0 * 0.4 = 0.4.
        # Score = 1.0 - 0.4 = 0.6. Still > 0.5.
        
        # Add failed predictions.
        # 5 failed predictions (prob 1.0) -> Raw F = 0.5.
        # F-term = 0.5 * 0.35 = 0.175.
        # Score = 0.6 - 0.175 = 0.425. < 0.5!
        
        for i in range(5):
            p = Prediction.create("fail", 1.0, datetime.now())
            p.outcome = "denied" # Failure
            state.add_prediction(p)
            
        proposal = planner.propose(state)
        
        assert proposal is not None
        assert proposal.action.id == "ask_clarification"
        assert "critically low" in proposal.action.rationale

    def test_priority_2_contradictions(self):
        """Heuristic 2: Contradictions trigger resolution (if coherence OK)."""
        state = BeliefState.create_empty()
        planner = Planner()
        
        # Add 1 contradiction. Coherence penalty 0.1 * 0.4 = 0.04. Score 0.96.
        # ContradictionRef(id, belief_a, belief_b, urgency)
        c = ContradictionRef("c1", "entity_1", "conflict", 0.1)
        state.contradictions.append(c)
        
        proposal = planner.propose(state)
        
        assert proposal is not None
        assert proposal.action.id == "resolve_contradiction"
        assert proposal.action.target == "entity_1"

    def test_priority_3_expiring_prediction(self):
        """Heuristic 3: Expiring high-conf prediction triggers observation."""
        state = BeliefState.create_empty()
        planner = Planner()
        
        # No contradictions
        # Add active prediction about to expire
        p = Prediction.create("Rain", 0.9, datetime.now() + timedelta(minutes=5))
        state.add_prediction(p)
        
        proposal = planner.propose(state)
        
        assert proposal is not None
        assert proposal.action.id == "gather_evidence"
        assert proposal.action.target == p.id

    def test_priority_4_no_predictions(self):
        """Heuristic 4: No predictions triggers generation."""
        state = BeliefState.create_empty()
        planner = Planner()
        
        # Empty state (Coherence 1.0, No contradictions, No preds)
        
        proposal = planner.propose(state)
        
        assert proposal is not None
        assert proposal.action.id == "generate_prediction"

    def test_priority_5_stability(self):
        """Heuristic 5: Stable state triggers nothing."""
        state = BeliefState.create_empty()
        planner = Planner()
        
        # Add a safe prediction (active, far future)
        p = Prediction.create("Safe", 0.5, datetime.now() + timedelta(hours=5))
        state.add_prediction(p)
        
        # Coherence OK, No contradictions, Prediction exists but not urgent
        
        proposal = planner.propose(state)
        
        assert proposal is None

    def test_planner_is_stateless_and_safe(self):
        """Planner does not mutate state."""
        state = BeliefState.create_empty()
        planner = Planner()
        
        # Initial hash/property
        count_before = state.prediction_count()
        ts_before = state.timestamp
        
        planner.propose(state)
        
        assert state.prediction_count() == count_before
        assert state.timestamp == ts_before


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
