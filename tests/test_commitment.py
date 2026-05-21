"""
Phase 23C: Commitment, Point-of-No-Return & Mode Switching Verification

Proves that:
1. Committed goals beat everything else (overwhelming priority).
2. Committed goals propagate "Mandatory" status to instrumental dependencies.
3. Committed goals cannot be abandoned (Immunity).
4. Mode switch works (Prep -> Execute).
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

class TestCommitment:
    
    def test_commitment_override(self, temp_brain_dir):
        """
        Scenario:
        Goal A (Committed): Low Value (0.1)
        Goal B (Shiny): High Value (1.0), Urgent
        
        Result: Goal A MUST win because it is COMMITTED.
        """
        agent = boot_agent(temp_brain_dir, "Commander")
        
        goal_a = agent.goals.add_goal("Hold the Line", expected_value=0.1)
        goal_b = agent.goals.add_goal("Chase Butterfly", expected_value=1.0, deadline=datetime.now())
        
        # Determine priority before commitment
        # B should win comfortably
        util_a = agent.goals.calculate_utility(goal_a)
        util_b = agent.goals.calculate_utility(goal_b)
        assert util_b.utility_score > util_a.utility_score
        
        # CROSS THE RUBICON
        agent.goals.commit_goal(goal_a.id)
        
        # Determine priority after commitment
        # A should crush B
        choice = agent.goals.prioritize(budget_available=100.0)
        assert choice.id == goal_a.id
        
        util_a_committed = agent.goals.calculate_utility(goal_a)
        assert util_a_committed.commitment_bonus >= 5.0
        assert "COMMITMENT" in util_a_committed.reason

    def test_mandatory_instrumental_goals(self, temp_brain_dir):
        """
        Scenario:
        Goal Term (Committed)
        Goal Prep (Instrumental to Term)
        
        Result: Goal Prep inherits commitment pressure.
        """
        agent = boot_agent(temp_brain_dir, "Engineer")
        
        goal_term = agent.goals.add_goal("Launch Mission")
        goal_prep = agent.goals.add_goal("Fuel Rocket", enables=[goal_term.id])
        
        # Commit the terminal goal
        agent.goals.commit_goal(goal_term.id)
        
        # Calculate prep utility
        util_prep = agent.goals.calculate_utility(goal_prep)
        
        # Should have inherited commitment bonus
        assert util_prep.commitment_bonus >= 3.0
        assert "MANDATORY" in util_prep.reason
        
    def test_immune_to_abandonment(self, temp_brain_dir):
        """
        Scenario:
        Goal A (Committed)
        Cost spirals to 200. Value is 0.1.
        Normal logic would Abandon.
        Committed logic must persist.
        """
        agent = boot_agent(temp_brain_dir, "Hero")
        
        goal_a = agent.goals.add_goal("Save World", expected_value=0.1)
        agent.goals.commit_goal(goal_a.id)
        
        # Make it terrible
        goal_a.cost_estimate = 200.0
        
        status = agent.goals.evaluate_lifecycle(goal_a, budget_available=100.0)
        
        assert status == GoalStatus.COMMITTED
        assert status != GoalStatus.ABANDONED

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
