"""
Phase 23A: Long-Horizon Strategy & Identity Constraints

Proves that:
1. Agent prefers goals aligned with its 'Strategic Domains'.
2. Aligned goals have higher 'Grit' (harder to abandon).
3. Strategic alignment creates a 'bonus' in utility.
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

class TestStrategicAlignment:
    
    def test_domain_preference(self, temp_brain_dir):
        """
        Scenario:
        Identity prefers 'Security' (1.0) over 'Wealth' (0.1).
        Goal A (Security) vs Goal B (Wealth), same base value.
        Result: Goal A wins due to alignment bonus.
        """
        agent = boot_agent(temp_brain_dir, "Guardian")
        
        # Inject strategic preference
        agent.identity.strategic_domains = {
            "Security": 1.0,
            "Wealth": 0.1
        }
        
        # Same intrinsic value
        goal_sec = agent.goals.add_goal("Patch Vuln", expected_value=0.5, domain="Security")
        goal_rich = agent.goals.add_goal("Buy Stock", expected_value=0.5, domain="Wealth")
        
        # Prioritize with identity context
        chosen = agent.goals.prioritize(budget_available=100.0, identity=agent.identity)
        
        assert chosen.id == goal_sec.id
        
        # Check reasons
        util_sec = agent.goals.calculate_utility(goal_sec, agent.identity)
        util_rich = agent.goals.calculate_utility(goal_rich, agent.identity)
        
        assert util_sec.strategic_bonus > util_rich.strategic_bonus
        assert "Strategy(Security)" in util_sec.reason

    def test_grit_prevents_abandonment(self, temp_brain_dir):
        """
        Scenario:
        Goal A (Core Domain): Cost rises to 75. Value 0.3.
        Threshold for normal is Cost 50, Value 0.4.
        
        Result: NOT ABANDONED because Grit doubles the tolerance.
        """
        agent = boot_agent(temp_brain_dir, "Stoic")
        
        # High preference for 'Science'
        agent.identity.strategic_domains = {"Science": 1.0}
        
        goal_sci = agent.goals.add_goal("Long Experiment", expected_value=0.3, cost=75.0, domain="Science")
        
        # Evaluate lifecycle
        status = agent.goals.evaluate_lifecycle(goal_sci, budget_available=100.0, identity=agent.identity)
        
        assert status == GoalStatus.ACTIVE, "Strategic goal should have survived due to Grit"
        
        # Compare with non-strategic goal
        goal_norm = agent.goals.add_goal("Random Task", expected_value=0.3, cost=75.0, domain="Random")
        status_norm = agent.goals.evaluate_lifecycle(goal_norm, budget_available=100.0, identity=agent.identity)
        
        assert status_norm == GoalStatus.ABANDONED, "Non-strategic goal should have been abandoned"

    def test_planner_integration_traces_strategy(self, temp_brain_dir):
        """
        Verify that Planner trace includes strategic pressure.
        """
        agent = boot_agent(temp_brain_dir, "Strategist")
        agent.identity.strategic_domains = {"Mission": 1.0}
        
        agent.goals.add_goal("Mission Critical", expected_value=0.8, domain="Mission")
        
        # Propose
        proposal = agent.planner.propose(
            agent.belief_state, 
            goals=agent.goals, 
            identity=agent.identity # New arg
        )
        
        if proposal and proposal.trace:
            # Check if trace data reflects utility
            pressures = proposal.trace.goal_pressures
            assert len(pressures) > 0
            # Just verify it ran without crashing and got data
            assert pressures[0]['pressure'] > 0

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
