"""
Phase 23D: Abort Logic, Failure Semantics & Honor Verification

Proves that:
1. Committed goals CAN fail (no infinite loops).
2. Failure is distinct from Abandonment (Honorable Defeat).
3. Catastrophic cost triggers abort even for committed goals.
4. "Impossibility" flag triggers immediate failure.
"""

import pytest
from datetime import datetime
from src.system.bootstrap import boot_agent
from src.agency.goal_pressure import GoalStatus

@pytest.fixture
def temp_brain_dir(tmp_path):
    path = tmp_path / "brain_data"
    path.mkdir()
    yield path

class TestHonorableFailure:
    
    def test_catastrophic_cost_abort(self, temp_brain_dir):
        """
        Scenario:
        Goal A (Committed): Value 1.0. 
        Cost spirals to 600.
        
        Result: FAILED (Honorable Defeat). Not ABANDONED.
        """
        agent = boot_agent(temp_brain_dir, "General")
        
        goal_a = agent.goals.add_goal("Defend Castle", expected_value=1.0)
        agent.goals.commit_goal(goal_a.id)
        
        # Scenario: Castle is burning, cost is infinite
        goal_a.cost_estimate = 600.0
        
        status = agent.goals.evaluate_lifecycle(goal_a, budget_available=100.0)
        
        assert status == GoalStatus.FAILED
        assert "Catastrophic Cost" in goal_a.failure_reason
        assert status != GoalStatus.ABANDONED

    def test_impossibility_abort(self, temp_brain_dir):
        """
        Scenario:
        Goal A (Committed).
        External reality says "Bridge is gone".
        Agent flags impossible.
        
        Result: FAILED.
        """
        agent = boot_agent(temp_brain_dir, "Scout")
        
        goal_a = agent.goals.add_goal("Cross Bridge", expected_value=1.0)
        agent.goals.commit_goal(goal_a.id)
        
        # Reality check
        goal_a.is_impossible = True
        
        status = agent.goals.evaluate_lifecycle(goal_a, budget_available=100.0)
        
        assert status == GoalStatus.FAILED
        assert "Impossible" in goal_a.failure_reason
        
    def test_active_goals_just_abandon(self, temp_brain_dir):
        """
        Scenario:
        Goal A (ACTIVE, NOT committed).
        Cost spirals to 600.
        
        Result: ABANDONED (Quit).
        """
        agent = boot_agent(temp_brain_dir, "Mercenary")
        
        goal_a = agent.goals.add_goal("Easy Money", expected_value=0.1)
        # NOT committed
        
        goal_a.cost_estimate = 600.0
        
        status = agent.goals.evaluate_lifecycle(goal_a, budget_available=100.0)
        
        # Should be ABANDONED because it wasn't committed
        # Wait, catastrophic cost checks are inside the "If committed" block?
        # Standard abandonment handles costs > 50. So 600 > 50, it triggers standard abandonment.
        
        assert status == GoalStatus.ABANDONED
        assert "Cost rising" in goal_a.abandon_reason

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
