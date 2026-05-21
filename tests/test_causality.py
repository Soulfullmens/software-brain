"""
Phase 23B: Causal Goal Chains & Instrumental Reasoning Verification

Proves that:
1. Instrumental Goals (low intrinsic value) gain value from what they enable.
2. The agent champions "Boring Setup Work" if it unlocks "Strategic Wins".
3. Recursive utility propagation works (A -> B -> C).
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

class TestCausalChains:
    
    def test_instrumental_value_propagation(self, temp_brain_dir):
        """
        Scenario:
        Goal A (Cleanup): Low Value (0.1)
        Goal B (Launch): High Value (1.0)
        
        Goal A enables Goal B.
        
        Result: Goal A's utility > Goal C (Medium Value 0.4) due to instrumental bonus.
        """
        agent = boot_agent(temp_brain_dir, "Visionary")
        
        # Goal B: The Big Win (High Value)
        # Initially not actionable (maybe high cost or blocked? 
        # For this test, we assume both are candidates, 
        # but A should be prioritized because it enables B, and B contributes to A's score.
        # Wait, if B is active, why not just do B?
        # A causal graph usually implies B is BLOCKED until A is done.
        # But our prioritization logic just ranks active goals.
        # We need to simulate that B is valuable but A is the NECESSARY step.
        # However, for pure utility calculation, even if B is "active", 
        # A should benefit from B's value if A -> B.
        
        goal_launch = agent.goals.add_goal("Launch Rocket", expected_value=1.0)
        
        # Goal A: The Boring Setup (Low Value), enables Launch
        goal_cleanup = agent.goals.add_goal(
            "Clean Pad", 
            expected_value=0.1, 
            enables=[goal_launch.id]
        )
        
        # Goal C: Distraction (Medium Value)
        goal_distraction = agent.goals.add_goal("Watch TV", expected_value=0.4)
        
        # Calculate utilities
        util_cleanup = agent.goals.calculate_utility(goal_cleanup)
        util_distraction = agent.goals.calculate_utility(goal_distraction)
        
        print(f"Cleanup Score: {util_cleanup.utility_score} (Instr: {util_cleanup.instrumental_bonus})")
        print(f"Distraction Score: {util_distraction.utility_score}")
        
        # Instrumental bonus from Launch (1.0 * 0.5 = 0.5) should push Cleanup (0.1) to ~0.6
        # Distraction is 0.4.
        
        assert util_cleanup.instrumental_bonus > 0.3
        assert util_cleanup.utility_score > util_distraction.utility_score
        assert "Future" in util_cleanup.reason

    def test_chain_reaction(self, temp_brain_dir):
        """
        Scenario: A -> B -> C
        C is Huge Value.
        A should feel it.
        """
        agent = boot_agent(temp_brain_dir, "Architect")
        
        goal_c = agent.goals.add_goal("Establish Colony", expected_value=1.0)
        goal_b = agent.goals.add_goal("Build Ship", expected_value=0.5, enables=[goal_c.id])
        goal_a = agent.goals.add_goal("Mine Ore", expected_value=0.1, enables=[goal_b.id])
        
        util_a = agent.goals.calculate_utility(goal_a)
        
        # A gets from B (0.5 intrinsic) + B's instrumental (from C)
        # C contribution to B = 1.0 * 0.5 = 0.5
        # B total = 0.5 base + 0.5 instr = 1.0
        # A gets from B = 1.0 * 0.5 = 0.5
        
        assert util_a.instrumental_bonus >= 0.2
        assert util_a.utility_score > 0.5 # Base 0.1 + Instr 0.5 approx
        
    def test_infinite_loop_prevention(self, temp_brain_dir):
        """
        Scenario: A -> B -> A
        Should not crash.
        """
        agent = boot_agent(temp_brain_dir, "Looper")
        
        goal_a = agent.goals.add_goal("Chicken")
        goal_b = agent.goals.add_goal("Egg", enables=[goal_a.id])
        
        # Create cycle
        goal_a.enables = [goal_b.id]
        
        # Calculate should not hang/crash
        util_a = agent.goals.calculate_utility(goal_a)
        assert util_a.utility_score >= 0

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
