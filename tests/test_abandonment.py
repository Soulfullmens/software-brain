"""
Phase 22C: Goal Abandonment & Strategy Verification

Proves that the agent can:
1. Abandon stuck goals (Sunk Cost Avoidance).
2. Defer expensive goals until budget recovers.
3. Automatically reactivate deferred goals.
"""

import pytest
from datetime import datetime, timedelta
from src.system.bootstrap import boot_agent
from src.agency.goal_pressure import GoalStatus

@pytest.fixture
def temp_brain_dir(tmp_path):
    path = tmp_path / "brain_data"
    path.mkdir()
    yield path

class TestStrategicAbandonment:
    
    def test_abandonment_rising_cost(self, temp_brain_dir):
        """
        Scenario:
        Goal A: Started well, but cost spiraled to 60.0 and Value is low (0.3).
        Result: ABANDONED.
        """
        agent = boot_agent(temp_brain_dir, "Realist")
        
        goal_a = agent.goals.add_goal("Spiral", expected_value=0.3, cost=10.0)
        
        # Simulate cost spiral
        goal_a.cost_estimate = 60.0
        
        # Evaluate
        chosen = agent.goals.prioritize(budget_available=100.0)
        
        assert goal_a.status == GoalStatus.ABANDONED
        assert "Cost rising" in goal_a.abandon_reason
        # If it's abandoned, it won't be chosen
        assert chosen is None or chosen.id != goal_a.id

    def test_abandonment_stagnation(self, temp_brain_dir):
        """
        Scenario:
        Goal B: High cost (30.0), hasn't progressed in 25 hours.
        Result: ABANDONED.
        """
        agent = boot_agent(temp_brain_dir, "Cleaner")
        
        goal_b = agent.goals.add_goal("Stuck", expected_value=0.5, cost=30.0)
        
        # Mark progress long ago
        goal_b.progress_count = 1
        goal_b.last_progress = datetime.now() - timedelta(hours=25)
        
        # Evaluate
        chosen = agent.goals.prioritize(budget_available=100.0)
        
        assert goal_b.status == GoalStatus.ABANDONED
        assert "Stagnation" in goal_b.abandon_reason

    def test_deferral_resource_scarcity(self, temp_brain_dir):
        """
        Scenario:
        Goal C: High Value (0.9), but Cost (80.0) > Budget * 1.5 (Budget=40).
        Result: DEFERRED (not Abandoned).
        """
        agent = boot_agent(temp_brain_dir, "Strategist")
        
        goal_c = agent.goals.add_goal("Moonshot", expected_value=0.9, cost=80.0)
        
        # Low budget
        chosen = agent.goals.prioritize(budget_available=40.0)
        
        assert goal_c.status == GoalStatus.DEFERRED
        assert "insufficient budget" in goal_c.abandon_reason
        assert chosen is None # Or picks another goal

    def test_reactivation_of_deferred(self, temp_brain_dir):
        """
        Scenario:
        Goal C: Was DEFERRED.
        Budget recovers to 100.
        Result: ACTIVE.
        """
        agent = boot_agent(temp_brain_dir, "Recoverer")
        
        goal_c = agent.goals.add_goal("Moonshot", expected_value=0.9, cost=80.0)
        goal_c.status = GoalStatus.DEFERRED
        
        # High budget
        chosen = agent.goals.prioritize(budget_available=100.0)
        
        assert goal_c.status == GoalStatus.ACTIVE
        assert chosen.id == goal_c.id

    def test_sunk_cost_avoidance(self, temp_brain_dir):
        """
        Scenario:
        Goal D: Huge sunk cost (progress=100), but remaining value low.
        Cost Estimate remains high.
        Result: ABANDONED (progress doesn't save it).
        """
        agent = boot_agent(temp_brain_dir, "Economist")
        
        goal_d = agent.goals.add_goal("Old Legacy", expected_value=0.2, cost=60.0)
        goal_d.progress_count = 100 # Huge sunk cost
        
        chosen = agent.goals.prioritize(budget_available=100.0)
        
        assert goal_d.status == GoalStatus.ABANDONED
        assert "Cost rising" in goal_d.abandon_reason

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
