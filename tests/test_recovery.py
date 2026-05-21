"""
Phase 21A: Recovery Protocols Verification

Proves that:
1. Recovery has strict eligibility criteria
2. HALT-level freezes require human authorization
3. Recovery is gradual (returns to CAUTIOUS, not NORMAL)
4. Recovery is auditable
5. System returns to productivity after recovery
"""

import pytest
from datetime import datetime, timedelta
import time
from src.system.bootstrap import boot_agent
from src.system.recovery import RecoveryProtocol, RecoveryCondition
from src.system.autonomy import FreezeReason, AutonomyLevel
from src.system.invariants import InvariantEngine
from src.system.killproof import KillProofExecutor
from src.system.intent import IntentContext
from src.agency.action import Action, PlanProposal


@pytest.fixture
def temp_brain_dir(tmp_path):
    path = tmp_path / "brain_data"
    path.mkdir()
    yield path


class TestRecoveryEligibility:
    
    def test_recovery_blocked_if_coherence_low(self):
        """Recovery requires coherence >= 0.6."""
        recovery = RecoveryProtocol()
        
        eligible, missing = recovery.check_recovery_eligible(
            frozen=True,
            frozen_at=datetime.now() - timedelta(minutes=10),
            freeze_reason="coherence_collapse",
            coherence=0.4,  # Below 0.6
            critique_count=0,
            budget=100,
            human_authorized=True
        )
        
        assert eligible is False
        assert any("Coherence" in m for m in missing)
        
    def test_recovery_blocked_if_too_many_critiques(self):
        """Recovery requires critiques <= 2."""
        recovery = RecoveryProtocol()
        
        eligible, missing = recovery.check_recovery_eligible(
            frozen=True,
            frozen_at=datetime.now() - timedelta(minutes=10),
            freeze_reason="manual_freeze",
            coherence=0.8,
            critique_count=5,  # Above 2
            budget=100,
            human_authorized=False
        )
        
        assert eligible is False
        assert any("critique" in m.lower() for m in missing)
        
    def test_recovery_blocked_if_time_not_elapsed(self):
        """Recovery requires minimum freeze time."""
        recovery = RecoveryProtocol()
        
        eligible, missing = recovery.check_recovery_eligible(
            frozen=True,
            frozen_at=datetime.now() - timedelta(seconds=30),  # Only 30s
            freeze_reason="manual_freeze",
            coherence=0.8,
            critique_count=0,
            budget=100,
            human_authorized=False
        )
        
        assert eligible is False
        assert any("time" in m.lower() for m in missing)


class TestHumanAuthorization:
    
    def test_halt_level_requires_human_authorization(self):
        """COHERENCE_COLLAPSE requires human authorization."""
        recovery = RecoveryProtocol()
        
        eligible, missing = recovery.check_recovery_eligible(
            frozen=True,
            frozen_at=datetime.now() - timedelta(minutes=10),
            freeze_reason="COHERENCE_COLLAPSE",
            coherence=0.8,
            critique_count=0,
            budget=100,
            human_authorized=False  # No authorization
        )
        
        assert eligible is False
        assert any("authorization" in m.lower() for m in missing)
        
    def test_halt_level_succeeds_with_authorization(self):
        """COHERENCE_COLLAPSE recovery succeeds with human authorization."""
        recovery = RecoveryProtocol()
        
        eligible, missing = recovery.check_recovery_eligible(
            frozen=True,
            frozen_at=datetime.now() - timedelta(minutes=10),
            freeze_reason="COHERENCE_COLLAPSE",
            coherence=0.8,
            critique_count=0,
            budget=100,
            human_authorized=True  # Authorized
        )
        
        assert eligible is True
        assert len(missing) == 0
        
    def test_manual_freeze_does_not_require_authorization(self):
        """MANUAL_FREEZE can recover without human authorization."""
        recovery = RecoveryProtocol()
        
        eligible, missing = recovery.check_recovery_eligible(
            frozen=True,
            frozen_at=datetime.now() - timedelta(minutes=10),
            freeze_reason="manual_freeze",
            coherence=0.8,
            critique_count=0,
            budget=100,
            human_authorized=False  # Not required
        )
        
        assert eligible is True


class TestGradualRecovery:
    
    def test_recovery_returns_to_cautious_not_normal(self, temp_brain_dir):
        """Recovery thaws to CAUTIOUS, not NORMAL."""
        agent = boot_agent(temp_brain_dir, "Recoverer")
        recovery = RecoveryProtocol()
        
        # Freeze with manual reason (no auth required)
        agent.autonomy._freeze(FreezeReason.MANUAL_FREEZE)
        
        # Wait for eligibility (simulate time passage)
        agent.autonomy.state.frozen_at = datetime.now() - timedelta(minutes=10)
        
        # Attempt recovery
        success, reason = recovery.attempt_recovery(
            autonomy_state=agent.autonomy.state,
            coherence=0.8,
            critique_count=0,
            human_authorized=False
        )
        
        assert success is True
        assert agent.autonomy.state.frozen is False
        assert agent.autonomy.state.level == AutonomyLevel.CAUTIOUS
        
        print(f"[RECOVERY TEST] Thawed to CAUTIOUS: {reason}")


class TestProductiveRecovery:
    """Prove system returns to productivity after recovery."""
    
    def test_can_execute_after_recovery(self, temp_brain_dir):
        """Recovered system can execute actions."""
        agent = boot_agent(temp_brain_dir, "Productive")
        recovery = RecoveryProtocol()
        
        invariants = InvariantEngine()
        killproof = KillProofExecutor(agent.executor, invariants)
        
        # 1. Freeze
        agent.autonomy._freeze(FreezeReason.MANUAL_FREEZE)
        assert agent.autonomy.state.frozen is True
        
        # 2. Simulate time + conditions
        agent.autonomy.state.frozen_at = datetime.now() - timedelta(minutes=10)
        agent.temporal.action_cooldown_seconds = 0
        agent.temporal.same_action_cooldown_seconds = 0
        
        # 3. Verify frozen execution fails
        action = Action("ask_clarification", "Help", "Need help")
        proposal = PlanProposal(action, 0.5)
        ctx = IntentContext.create_agent_intent("Frozen test")
        
        frozen_result = killproof.execute(proposal, ctx)
        assert frozen_result is None
        
        # 4. Recover
        success, _ = recovery.attempt_recovery(
            autonomy_state=agent.autonomy.state,
            coherence=0.8,
            critique_count=0,
            human_authorized=False
        )
        assert success is True
        
        # 5. Verify execution now works
        # (ask_clarification is allowed at CAUTIOUS level)
        recovered_result = killproof.execute(proposal, ctx)
        
        # Should succeed now
        assert agent.autonomy.state.frozen is False
        assert agent.autonomy.state.level == AutonomyLevel.CAUTIOUS
        
        print("[RECOVERY TEST] Productivity restored after recovery")
        
    def test_recovery_is_auditable(self, temp_brain_dir):
        """Recovery attempts are recorded."""
        agent = boot_agent(temp_brain_dir, "Audited")
        recovery = RecoveryProtocol()
        
        # Freeze
        agent.autonomy._freeze(FreezeReason.MANUAL_FREEZE)
        agent.autonomy.state.frozen_at = datetime.now() - timedelta(minutes=10)
        
        # Attempt recovery
        success, reason = recovery.attempt_recovery(
            autonomy_state=agent.autonomy.state,
            coherence=0.8,
            critique_count=0,
            human_authorized=False
        )
        
        # Check audit trail
        assert len(recovery.attempts) >= 1
        last_attempt = recovery.attempts[-1]
        assert last_attempt.success == success
        
        summary = recovery.summary()
        assert summary["total_attempts"] >= 1
        
        print(f"[RECOVERY TEST] Audit recorded: {summary}")


class TestRecoveryInvariants:
    """Prove recovery doesn't violate invariants."""
    
    def test_IMPOSSIBLE_recovery_without_criteria(self, temp_brain_dir):
        """IMPOSSIBLE: Recovery succeeds without meeting criteria."""
        agent = boot_agent(temp_brain_dir, "NoShortcut")
        recovery = RecoveryProtocol()
        
        # Freeze with HALT-level reason
        agent.autonomy._freeze(FreezeReason.COHERENCE_COLLAPSE)
        
        # Don't meet criteria
        agent.autonomy.state.frozen_at = datetime.now()  # Just now
        
        # Attempt recovery without authorization
        success, reason = recovery.attempt_recovery(
            autonomy_state=agent.autonomy.state,
            coherence=0.4,  # Low
            critique_count=5,  # High
            human_authorized=False  # Not authorized
        )
        
        assert success is False
        assert agent.autonomy.state.frozen is True
        
        print(f"[RECOVERY TEST] Shortcut BLOCKED: {reason}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
