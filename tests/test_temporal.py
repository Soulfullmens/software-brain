"""
Phase 18: Temporal Autonomy & Long-Horizon Governance Verification

Proves that:
1. Agent can defer actions (propose now, commit later)
2. Agent respects rate limits and cooldowns
3. Agent detects temporal inconsistency (loops, repetition)
4. Agent can cancel commitments when context changes
5. Agent can WAIT intelligently
"""

import pytest
from datetime import datetime, timedelta
import time
from src.system.bootstrap import boot_agent
from src.system.temporal import TemporalGovernor, UrgencyLevel, CommitmentStatus
from src.system.intent import IntentContext
from src.agency.action import Action, PlanProposal


@pytest.fixture
def temp_brain_dir(tmp_path):
    path = tmp_path / "brain_data"
    path.mkdir()
    yield path


class TestDeferredCommitments:
    
    def test_propose_and_cancel_commitment(self):
        gov = TemporalGovernor()
        
        # Propose a deferred action
        commitment = gov.propose_commitment(
            action_id="generate_prediction",
            action_description="Make a prediction about X",
            urgency=UrgencyLevel.NORMAL,
            delay_seconds=30,
            ttl_seconds=300
        )
        
        assert commitment.status == CommitmentStatus.PENDING
        
        # Cancel it
        success = gov.cancel_commitment(commitment.id, "Context changed")
        assert success is True
        assert commitment.status == CommitmentStatus.CANCELED
        assert commitment.cancel_reason == "Context changed"
        
    def test_commitment_expiration(self):
        gov = TemporalGovernor()
        
        # Propose with very short TTL
        commitment = gov.propose_commitment(
            action_id="test_action",
            action_description="Test",
            ttl_seconds=0.01  # Expires almost immediately
        )
        
        time.sleep(0.02)
        
        # Get ready commitments (should mark as expired)
        ready = gov.get_ready_commitments()
        
        assert commitment.status == CommitmentStatus.EXPIRED
        assert commitment not in ready


class TestTemporalConsistency:
    
    def test_same_action_cooldown(self):
        gov = TemporalGovernor()
        gov.same_action_cooldown_seconds = 60
        
        # Record an action
        gov._record_intention("gather_evidence", None, "executed")
        
        # Try same action immediately
        is_consistent, reason = gov.check_temporal_consistency("gather_evidence")
        
        assert is_consistent is False
        assert "Same action" in reason
        
    def test_loop_detection(self):
        gov = TemporalGovernor()
        gov.same_action_cooldown_seconds = 0  # Disable same-action check
        
        # Record same action 3 times
        for _ in range(3):
            gov._record_intention("resolve_contradiction", None, "executed")
        
        # Try same action again
        is_consistent, reason = gov.check_temporal_consistency("resolve_contradiction")
        
        assert is_consistent is False
        assert "loop" in reason.lower()


class TestRateLimiting:
    
    def test_action_rate_limit(self):
        gov = TemporalGovernor()
        gov.max_actions_per_minute = 5
        gov.action_cooldown_seconds = 0  # Disable global cooldown for this test
        
        # Record 5 actions
        for _ in range(5):
            gov._update_action_tracking()
        
        # Should be rate limited
        should_wait, reason = gov.should_wait()
        assert should_wait is True
        assert "Rate limit" in reason


class TestIntegratedTemporalGovernance:
    
    def test_agent_can_wait(self, temp_brain_dir):
        """Critical test: prove the agent can wait intelligently."""
        agent = boot_agent(temp_brain_dir, "Patient")
        
        # Disable global cooldown but keep same-action cooldown
        agent.temporal.action_cooldown_seconds = 0
        agent.temporal.same_action_cooldown_seconds = 60.0
        
        # First action should be allowed
        can_act_1, reason_1 = agent.temporal.can_act_now("gather_evidence")
        assert can_act_1 is True
        
        # Record the action
        agent.temporal._record_intention("gather_evidence", None, "executed")
        
        # Same action immediately should be denied due to same-action cooldown
        can_act_2, reason_2 = agent.temporal.can_act_now("gather_evidence")
        assert can_act_2 is False
        assert "Same action" in reason_2
        
        # Different action should be allowed (no global cooldown)
        can_act_3, reason_3 = agent.temporal.can_act_now("generate_prediction")
        assert can_act_3 is True
        
        print("[SUCCESS] Agent demonstrated intelligent waiting")
        
    def test_executor_respects_temporal_denial(self, temp_brain_dir):
        agent = boot_agent(temp_brain_dir, "Temporal")
        
        # Record same action 3 times to trigger loop detection
        agent.temporal.same_action_cooldown_seconds = 0  # Disable same-action check for this test
        agent.temporal.action_cooldown_seconds = 0  # Disable global cooldown
        for _ in range(3):
            agent.temporal._record_intention("resolve_contradiction", None, "executed")
        
        # Reset action tracking so we don't hit rate limit
        agent.temporal.actions_this_minute = 0
        agent.temporal.last_action_time = None
        
        # Try to execute same action
        action = Action("resolve_contradiction", "Test", "Rationale", "target")
        proposal = PlanProposal(action, 0.8)
        ctx = IntentContext.create_agent_intent("Test")
        
        result = agent.executor.execute(proposal, context=ctx)
        
        # Should be denied due to loop
        assert result is None
        
        # Check audit log
        entries = agent.executor.audit_log.entries
        last_entry = entries[-1]
        assert "Temporal" in last_entry.denial_reason
        assert "loop" in last_entry.denial_reason.lower()
        
        print(f"[SUCCESS] Executor respected temporal denial: {last_entry.denial_reason}")


class TestCommitmentLifecycle:
    
    def test_full_commitment_lifecycle(self, temp_brain_dir):
        agent = boot_agent(temp_brain_dir, "Committer")
        
        # 1. Propose commitment
        commitment = agent.temporal.propose_commitment(
            action_id="gather_evidence",
            action_description="Verify prediction about weather",
            urgency=UrgencyLevel.DEFERRED,
            delay_seconds=0,  # Ready immediately for test
            ttl_seconds=300,
            coherence=agent.belief_state.coherence_score,
            goal_pressure=0.5
        )
        
        assert commitment.status == CommitmentStatus.PENDING
        
        # 2. Get ready commitments
        ready = agent.temporal.get_ready_commitments()
        assert len(ready) >= 1
        assert commitment in ready
        
        # 3. Mark as executed
        agent.temporal.mark_executed(commitment.id, decision_id="test_decision")
        
        assert commitment.status == CommitmentStatus.EXECUTED
        
        # 4. Verify in intention history
        history = agent.temporal.intention_history
        assert len(history) >= 1
        assert history[-1].action_id == "gather_evidence"
        
        print("[SUCCESS] Full commitment lifecycle completed")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
