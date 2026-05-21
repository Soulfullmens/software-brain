"""
Phase 24A: Authority & Permission Logic Verification

Proves that:
1. Trust modifies permission thresholds.
2. Decision caching works (sticky permissions).
3. Catastrophic events enforce escalation.
4. Identity changes are always locked.
"""

import pytest
from datetime import datetime, timedelta
from src.agency.authority import Authority, TrustModel, DecisionType, PermissionLevel

class TestAuthority:
    
    def test_trust_scaling(self):
        """
        High trust should allow autonomous commit.
        Low trust should block it.
        """
        # 1. High Trust Agent (Base 1.0)
        high_trust = Authority(TrustModel(base_level=1.0))
        
        # Risk 0.2 (Low Risk)
        # Thresholds: Autonomy 0.8 * 1.0 = 0.8.
        # Risk 0.2 < 0.8 -> AUTONOMOUS.
        level = high_trust.check_permission(DecisionType.COMMIT_GOAL, "goal_1", risk_score=0.2)
        assert level == PermissionLevel.AUTONOMOUS
        
        # 2. Low Trust Agent (Base 0.1)
        low_trust = Authority(TrustModel(base_level=0.1))
        
        # Risk 0.2 (Low Risk)
        # Thresholds: Autonomy 0.8 * 0.1 = 0.08.
        # Risk 0.2 > 0.08 -> REQUEST_APPROVAL.
        level = low_trust.check_permission(DecisionType.COMMIT_GOAL, "goal_1", risk_score=0.2)
        assert level == PermissionLevel.REQUEST_APPROVAL

    def test_decision_caching(self):
        """
        If owner approves "Launch", agent shouldn't ask again immediately.
        """
        auth = Authority()
        
        # Initially, it wants approval (Risk 0.9)
        level = auth.check_permission(DecisionType.COMMIT_GOAL, "context_x", risk_score=0.9)
        assert level == PermissionLevel.REQUEST_APPROVAL
        
        # Owner approves
        auth.register_authorization(DecisionType.COMMIT_GOAL, "context_x", approved=True)
        
        # Check again - should be Autonomous now (because Cache says Approved)
        level_2 = auth.check_permission(DecisionType.COMMIT_GOAL, "context_x", risk_score=0.9)
        assert level_2 == PermissionLevel.AUTONOMOUS
        
        # Owner Denies another
        auth.register_authorization(DecisionType.COMMIT_GOAL, "context_y", approved=False)
        level_3 = auth.check_permission(DecisionType.COMMIT_GOAL, "context_y", risk_score=0.9)
        assert level_3 == PermissionLevel.DENIED

    def test_identity_lock(self):
        """
        Identity modification ALWAYS requires approval, even with Max Trust.
        """
        auth = Authority(TrustModel(base_level=1.0))
        
        # Zero risk identity change? Doesn't matter.
        level = auth.check_permission(DecisionType.MODIFY_IDENTITY, "change_values", risk_score=0.0)
        assert level == PermissionLevel.REQUEST_APPROVAL

    def test_escalation_always_notifies(self):
        """
        Escalate Failure is at minimum NOTIFY.
        """
        auth = Authority(TrustModel(base_level=1.0))
        level = auth.check_permission(DecisionType.ESCALATE_FAILURE, "fail_1", risk_score=0.5)
        assert level == PermissionLevel.NOTIFY

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
