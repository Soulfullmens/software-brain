"""
Phase 11: Permission Engine Verification

Tests that the Executor enforces the PermissionPolicy.
"""

import pytest
from typing import Set, Optional
from src.embodiment.base import Embodiment
from src.agency.action import Action, PlanProposal
from src.perception.input_event import InputEvent
from src.system.executor import Executor
from src.system.permissions import PermissionPolicy, AuthorityLevel, create_default_policy
from src.system.intent import IntentContext

class MockBody(Embodiment):
    """A body with both safe and dangerous capabilities."""
    
    @property
    def embodiment_id(self) -> str:
        return "mock_body"
        
    @property
    def capabilities(self) -> Set[str]:
        return {"safe_action", "dangerous_action"}
        
    def can_execute(self, action: Action) -> bool:
        return action.id in self.capabilities
        
    def execute(self, action: Action) -> Optional[InputEvent]:
        return InputEvent("mock", "text", {"content": "executed"}, None)


class TestPermissionEngine:
    
    def test_default_policy_enforcement(self):
        """Verify default policy behavior."""
        # Default policy: Restricted Agent, Unlimited Owner
        # But default policy allows 'ask_clarification' etc.
        # Let's create a custom policy for clear testing.
        policy = PermissionPolicy()
        policy.allow(AuthorityLevel.AGENT, "safe_action")
        policy.allow(AuthorityLevel.OWNER, "*")
        
        body = MockBody()
        executor = Executor(body, policy)
        
        # 1. Agent -> Safe Action -> Allowed
        action_safe = Action("safe_action", "desc", "rat")
        proposal_safe = PlanProposal(action_safe, 1.0)
        
        ctx_agent = IntentContext(origin="agent", authority=AuthorityLevel.AGENT, reason="test")
        result = executor.execute(proposal_safe, context=ctx_agent)
        assert result is not None # Executed
        
        # 2. Agent -> Dangerous Action -> Denied (Security)
        action_danger = Action("dangerous_action", "desc", "rat")
        proposal_danger = PlanProposal(action_danger, 1.0)
        
        result = executor.execute(proposal_danger, context=ctx_agent)
        assert result is None # Denied
        
        # 3. Owner -> Dangerous Action -> Allowed (Wildcard)
        ctx_owner = IntentContext(origin="owner", authority=AuthorityLevel.OWNER, reason="test")
        result = executor.execute(proposal_danger, context=ctx_owner)
        assert result is not None # Executed

    def test_capability_check_after_permission(self):
        """Even if allowed, body must support it."""
        policy = PermissionPolicy()
        policy.allow(AuthorityLevel.AGENT, "impossible_action")
        
        body = MockBody() # Does NOT have "impossible_action"
        executor = Executor(body, policy)
        
        action = Action("impossible_action", "desc", "rat")
        proposal = PlanProposal(action, 1.0)
        
        ctx_agent = IntentContext(origin="agent", authority=AuthorityLevel.AGENT, reason="test")
        
        # Security pass, Capability fail
        result = executor.execute(proposal, context=ctx_agent)
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
