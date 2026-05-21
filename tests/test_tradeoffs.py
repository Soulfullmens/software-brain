"""
Phase 22B: Goal Prioritization & Tradeoff Verification

Proves that the agent can:
1. Reason about Value vs. Urgency.
2. Spot "Urgency Traps" (Low Value + High Urgency).
3. Penalize Risk.
4. Log why a goal was chosen/rejected.
"""

import pytest
from datetime import datetime, timedelta
from src.system.bootstrap import boot_agent
from src.agency.goal_pressure import GoalStatus, TradeoffRecord

@pytest.fixture
def temp_brain_dir(tmp_path):
    path = tmp_path / "brain_data"
    path.mkdir()
    yield path

class TestUsageTradeoffs:
    
    def test_avoids_urgency_trap(self, temp_brain_dir):
        """
        Scenario:
        Goal A: High Value (0.9), Safe (0.1), No deadline (Urgency 0)
        Goal B: Low Value (0.2), Safe (0.1), Urgent Deadline (Urgency 1.0)
        
        Result: System chooses Goal A. Goal B is identified as a TRAP.
        """
        agent = boot_agent(temp_brain_dir, "Strategist")
        
        # Goal A: Important Work
        goal_a = agent.goals.add_goal(
            "Develop Cure", 
            expected_value=0.9, 
            risk=0.1,
            deadline=None
        )
        
        # Goal B: Distraction
        goal_b = agent.goals.add_goal(
            "Answer Email",
            expected_value=0.2, # Low value
            risk=0.1,
            deadline=datetime.now() - timedelta(minutes=1) # Overdue/Urgent
        )
        
        # Evaluate
        chosen = agent.goals.prioritize(budget_available=100.0)
        
        assert chosen.id == goal_a.id, "Failed to prioritize Value over Urgency"
        
        # Verify Trap Logic
        utility_b = agent.goals.calculate_utility(goal_b)
        assert utility_b.is_urgency_trap is True
        assert utility_b.urgency_bonus < 0, "Urgency trap should be penalized"
        
        # Audit Check
        assert len(agent.goals.tradeoff_history) > 0
        record = agent.goals.tradeoff_history[-1]
        assert record.chosen_goal_id == goal_a.id
        assert goal_b.id in record.rejected_goal_ids
        
    def test_risk_aversion(self, temp_brain_dir):
        """
        Scenario:
        Goal A: High Value (0.8), High Risk (0.8) -> Net ~0.16
        Goal B: Medium Value (0.5), Low Risk (0.0) -> Net ~0.5
        
        Result: System chooses Goal B (Safe Bet).
        """
        agent = boot_agent(temp_brain_dir, "RiskAware")
        
        goal_a = agent.goals.add_goal("Gamble", expected_value=0.8, risk=0.8)
        goal_b = agent.goals.add_goal("Sure Thing", expected_value=0.5, risk=0.0)
        
        chosen = agent.goals.prioritize(budget_available=100.0)
        
        assert chosen.id == goal_b.id, f"Failed to penalize risk: {chosen.description}"
        
        utility_a = agent.goals.calculate_utility(goal_a)
        assert utility_a.risk_penalty == 0.8
        
    def test_cost_dampening(self, temp_brain_dir):
        """
        Scenario:
        Goal A: Value 0.5, Cost 10
        Goal B: Value 0.5, Cost 1000
        
        Result: Choose A.
        """
        agent = boot_agent(temp_brain_dir, "Frugal")
        
        goal_a = agent.goals.add_goal("Cheap Win", expected_value=0.5, cost=10.0)
        goal_b = agent.goals.add_goal("Expensive Win", expected_value=0.5, cost=1000.0)
        
        chosen = agent.goals.prioritize(budget_available=100.0)
        
        assert chosen.id == goal_a.id
        
        utility_a = agent.goals.calculate_utility(goal_a)
        utility_b = agent.goals.calculate_utility(goal_b)
        
        assert utility_a.utility_score > utility_b.utility_score
        
    def test_tradeoff_logging(self, temp_brain_dir):
        agent = boot_agent(temp_brain_dir, "Logger")
        agent.goals.add_goal("Task 1")
        agent.goals.add_goal("Task 2")
        
        agent.goals.prioritize(100)
        
        assert len(agent.goals.tradeoff_history) == 1
        record = agent.goals.tradeoff_history[0]
        assert isinstance(record, TradeoffRecord)
        assert "Score" in record.reasoning

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
