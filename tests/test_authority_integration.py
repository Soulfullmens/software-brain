"""
Phase 24B: Authority Integration Verification

Proves that:
1. GoalTradeoffEngine obeys Authority. (The Court has Police)
2. Commit is blocked if PermissionLevel is REQUEST_APPROVAL.
3. Commit succeeds if PermissionLevel is AUTONOMOUS.
4. Catastrophic abort triggers Escalation.
"""

import pytest
from datetime import datetime
from src.system.bootstrap import boot_agent
from src.agency.goal_pressure import GoalStatus, GoalTradeoffEngine
from src.agency.authority import Authority, TrustModel, PermissionLevel, DecisionType

@pytest.fixture
def temp_brain_dir(tmp_path):
    path = tmp_path / "brain_data"
    path.mkdir()
    yield path

class TestAuthorityIntegration:
    
    def test_autonomous_commit(self, temp_brain_dir):
        """
        Scenario: Low Risk Goal + High Trust Agent -> Commit Allowed.
        """
        # Boot simple agent (Goals only)
        # We manually inject Authority for precise control
        auth = Authority(TrustModel(base_level=1.0)) # Max Trust
        goals = GoalTradeoffEngine(authority=auth)
        
        goal = goals.add_goal("Low Risk", expected_value=0.5, risk=0.1, cost=10.0)
        
        # Action: Commit
        success = goals.commit_goal(goal.id)
        
        assert success is True
        assert goal.status == GoalStatus.COMMITTED
        
    def test_blocked_commit(self, temp_brain_dir):
        """
        Scenario: High Risk Goal + Low Trust Agent -> Commit Blocked.
        """
        auth = Authority(TrustModel(base_level=0.1)) # Minimal Trust
        goals = GoalTradeoffEngine(authority=auth)
        
        # High Cost + High Risk = High Risk Score
        goal = goals.add_goal("Dangerous Move", expected_value=1.0, risk=0.9, cost=200.0)
        
        # Action: Commit
        success = goals.commit_goal(goal.id)
        
        assert success is False
        assert goal.status == GoalStatus.ACTIVE # Not committed
        # We can't easily check 'pending' or logs without mocking, but the result is correct.
        
    def test_catastrophic_escalation(self, temp_brain_dir):
        """
        Scenario: Goal Fails Catastrophically -> Escalation Triggered.
        """
        # Mock Authority to capture escalation
        class MockAuthority(Authority):
            def __init__(self):
                super().__init__()
                self.escalated = False
                
            def escalate(self, reason: str, context: dict) -> None:
                self.escalated = True
                self.last_reason = reason
        
        auth = MockAuthority()
        goals = GoalTradeoffEngine(authority=auth)
        
        goal = goals.add_goal("To Fail", expected_value=1.0)
        goals.commit_goal(goal.id) # Should succeed (default trust)
        
        # Trigger Catastrophe
        goal.cost_estimate = 600.0
        
        status = goals.evaluate_lifecycle(goal, budget_available=1000.0)
        
        assert status == GoalStatus.FAILED
        assert auth.escalated is True
        assert "Catastrophic Cost" in auth.last_reason

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
