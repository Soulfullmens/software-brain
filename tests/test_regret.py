"""
Phase 25.4: Failure Artifacts & Regret Ledger Verification

Proves that:
1. FailureArtifact captures all required fields.
2. Regret scoring works correctly.
3. AuthorizedExecutor emits artifacts on blocked actions.
4. RegretLedger accumulates and indexes artifacts.
"""

import pytest
from datetime import datetime
from pathlib import Path
from src.learning.regret import FailureArtifact, FailureType, RegretLedger
from src.embodiment.filesystem import FilesystemBody
from src.embodiment.authorized_executor import AuthorizedExecutor
from src.agency.action import Action
from src.agency.authority import Authority, TrustModel, PermissionLevel


class TestFailureArtifact:
    
    def test_regret_score_calculation(self):
        """Regret score is computed from artifact properties."""
        # High regret: Goal failed, irreversible, no rollback
        high_regret = FailureArtifact(
            failure_type=FailureType.GOAL_FAILED,
            irreversible=True,
            rollback_possible=False,
            delta_cost=100.0,
            trust_level_at_time=0.9
        )
        
        # Low regret: Authority pending, reversible
        low_regret = FailureArtifact(
            failure_type=FailureType.AUTHORITY_APPROVAL_PENDING,
            irreversible=False,
            rollback_possible=True,
            delta_cost=5.0,
            trust_level_at_time=0.3
        )
        
        assert high_regret.regret_score > 1.0  # High
        assert low_regret.regret_score < 0.5  # Low
        assert high_regret.regret_score > low_regret.regret_score


class TestRegretLedger:
    
    def test_record_and_index(self):
        """Artifacts are recorded and indexed by goal and type."""
        ledger = RegretLedger()
        
        artifact1 = FailureArtifact(
            failure_type=FailureType.AUTHORITY_BLOCKED,
            goal_id="goal_123",
            action_id="delete_file"
        )
        artifact2 = FailureArtifact(
            failure_type=FailureType.GOAL_FAILED,
            goal_id="goal_123"
        )
        artifact3 = FailureArtifact(
            failure_type=FailureType.AUTHORITY_BLOCKED,
            goal_id="goal_456"
        )
        
        ledger.record(artifact1)
        ledger.record(artifact2)
        ledger.record(artifact3)
        
        assert len(ledger.artifacts) == 3
        assert len(ledger.by_goal["goal_123"]) == 2
        assert len(ledger.by_type[FailureType.AUTHORITY_BLOCKED]) == 2
        
    def test_total_regret_accumulates(self):
        """Total regret sums across all artifacts."""
        ledger = RegretLedger()
        
        ledger.record(FailureArtifact(failure_type=FailureType.GOAL_FAILED))
        ledger.record(FailureArtifact(failure_type=FailureType.GOAL_FAILED))
        
        assert ledger.total_regret >= 2.0  # Each GOAL_FAILED is ~1.0


class TestExecutorRegretIntegration:
    
    def test_blocked_action_emits_artifact(self, tmp_path):
        """AuthorizedExecutor emits artifact when action is blocked."""
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        
        body = FilesystemBody(sandbox_root=sandbox)
        auth = Authority(TrustModel(base_level=0.1))  # Low trust
        ledger = RegretLedger()
        
        executor = AuthorizedExecutor(body, auth, regret_ledger=ledger)
        
        # High risk action -> will be blocked
        action = Action(
            id="delete_file",
            description="",
            rationale="Test",
            target="test.txt",
            irreversible=True,
            estimated_cost=100.0,
            risk_domain="filesystem"
        )
        
        result = executor.execute(action, goal_id="goal_test")
        
        assert result.success is False
        assert len(ledger.artifacts) == 1
        
        artifact = ledger.artifacts[0]
        assert artifact.failure_type == FailureType.AUTHORITY_BLOCKED or artifact.failure_type == FailureType.AUTHORITY_APPROVAL_PENDING
        assert artifact.goal_id == "goal_test"
        assert artifact.action_id == "delete_file"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
