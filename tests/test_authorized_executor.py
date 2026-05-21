"""
Phase 25.1: Action-Level Authority Verification

Proves that:
1. Irreversible actions require Authority check.
2. DENIED permission blocks execution.
3. REQUEST_APPROVAL blocks execution.
4. Cost feedback updates goal.cost_estimate.
5. Reversible actions pass through without check.
"""

import pytest
from pathlib import Path
from src.embodiment.filesystem import FilesystemBody
from src.embodiment.authorized_executor import AuthorizedExecutor, ExecutionResult
from src.agency.action import Action
from src.agency.authority import Authority, TrustModel, PermissionLevel, DecisionType
from src.agency.goal_pressure import GoalTradeoffEngine


@pytest.fixture
def sandbox(tmp_path):
    """Create a temporary sandbox directory."""
    sandbox_dir = tmp_path / "agent_sandbox"
    sandbox_dir.mkdir()
    yield sandbox_dir


class TestAuthorizedExecutor:
    
    def test_irreversible_blocked_by_low_trust(self, sandbox):
        """
        Scenario: Low trust agent attempts irreversible delete.
        Result: BLOCKED.
        """
        body = FilesystemBody(sandbox_root=sandbox)
        auth = Authority(TrustModel(base_level=0.1))  # Very low trust
        executor = AuthorizedExecutor(body, auth)
        
        # Create a file first
        (sandbox / "precious.txt").write_text("important data")
        
        # Attempt irreversible delete
        delete_action = Action(
            id="delete_file",
            description="",
            rationale="Testing",
            target="precious.txt",
            irreversible=True,
            estimated_cost=50.0,
            risk_domain="filesystem"
        )
        
        result = executor.execute(delete_action)
        
        # Should be blocked
        assert result.success is False
        assert result.permission_level == PermissionLevel.REQUEST_APPROVAL
        
        # File should still exist
        assert (sandbox / "precious.txt").exists()
        
    def test_irreversible_allowed_by_high_trust(self, sandbox):
        """
        Scenario: High trust agent attempts irreversible delete.
        Result: ALLOWED.
        """
        body = FilesystemBody(sandbox_root=sandbox)
        auth = Authority(TrustModel(base_level=1.0))  # Max trust
        executor = AuthorizedExecutor(body, auth)
        
        # Create a file first
        (sandbox / "expendable.txt").write_text("not important")
        
        # Attempt irreversible delete (low cost, high trust)
        delete_action = Action(
            id="delete_file",
            description="",
            rationale="Cleanup",
            target="expendable.txt",
            irreversible=True,
            estimated_cost=5.0,  # Low cost
            risk_domain="filesystem"
        )
        
        result = executor.execute(delete_action)
        
        # Should succeed
        assert result.success is True
        
        # File should be gone
        assert not (sandbox / "expendable.txt").exists()
        
    def test_reversible_bypasses_authority(self, sandbox):
        """
        Scenario: Reversible action (read).
        Result: No authority check, just execute.
        """
        body = FilesystemBody(sandbox_root=sandbox)
        auth = Authority(TrustModel(base_level=0.1))  # Very low trust
        executor = AuthorizedExecutor(body, auth)
        
        # Create a file
        (sandbox / "readable.txt").write_text("hello")
        
        # Read action (reversible)
        read_action = Action(
            id="read_file",
            description="",
            rationale="Reading",
            target="readable.txt",
            irreversible=False  # Reversible
        )
        
        result = executor.execute(read_action)
        
        # Should succeed even with low trust
        assert result.success is True
        assert result.event.payload["content"] == "hello"
        
    def test_cost_feedback_to_goal(self, sandbox):
        """
        Scenario: Execution reports cost back to goal.
        Result: goal.cost_estimate increases.
        """
        body = FilesystemBody(sandbox_root=sandbox)
        auth = Authority(TrustModel(base_level=1.0))
        goal_engine = GoalTradeoffEngine()
        
        goal = goal_engine.add_goal("Test Goal", cost=10.0)
        initial_cost = goal.cost_estimate
        
        executor = AuthorizedExecutor(body, auth, goal_engine)
        
        # Write action
        write_action = Action(
            id="write_file",
            description="Some content",
            rationale="Testing",
            target="feedback_test.txt",
            irreversible=True,
            estimated_cost=25.0,
            risk_domain="filesystem"
        )
        
        executor.execute(write_action, goal_id=goal.id)
        
        # Cost should have increased
        assert goal.cost_estimate == initial_cost + 25.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
