"""
Phase 24C: Owner Loop Verification

Proves that:
1. DecisionQueue can enqueue and poll requests.
2. Authority enqueues requests on REQUEST_APPROVAL.
3. Owner can respond and unlock the request.
4. Escalation creates non-blocking notifications.
5. Expiry works.
"""

import pytest
from datetime import datetime, timedelta
from src.agency.owner_loop import DecisionQueue, OwnerRequest, RequestStatus
from src.agency.authority import Authority, TrustModel, DecisionType, PermissionLevel


class TestDecisionQueue:
    
    def test_enqueue_and_poll(self):
        """Basic FIFO operation."""
        queue = DecisionQueue()
        
        request = queue.enqueue(
            decision_type=DecisionType.COMMIT_GOAL,
            context={"goal_id": "abc"},
            risk_score=0.5,
            rationale="Need approval to commit"
        )
        
        assert queue.get_pending_count() == 1
        assert queue.poll(request.id) == RequestStatus.PENDING
        
    def test_respond_approve(self):
        """Owner approves."""
        queue = DecisionQueue()
        
        request = queue.enqueue(
            decision_type=DecisionType.COMMIT_GOAL,
            context={"goal_id": "abc"},
            risk_score=0.5,
            rationale="Commit request"
        )
        
        # Owner approves
        queue.respond(request.id, approved=True)
        
        assert queue.get_pending_count() == 0
        assert queue.poll(request.id) == RequestStatus.APPROVED
        
    def test_respond_deny(self):
        """Owner denies."""
        queue = DecisionQueue()
        
        request = queue.enqueue(
            decision_type=DecisionType.COMMIT_GOAL,
            context={"goal_id": "abc"},
            risk_score=0.5,
            rationale="Commit request"
        )
        
        # Owner denies
        queue.respond(request.id, approved=False)
        
        assert queue.poll(request.id) == RequestStatus.DENIED
        
    def test_expiry(self):
        """Stale requests expire."""
        queue = DecisionQueue(default_expiry_minutes=0) # Immediate expiry for test
        
        request = queue.enqueue(
            decision_type=DecisionType.COMMIT_GOAL,
            context={"goal_id": "abc"},
            risk_score=0.5,
            rationale="This will expire",
            expiry_minutes=0 # Immediate
        )
        
        # Force expiry
        request.expires_at = datetime.now() - timedelta(seconds=1)
        
        # Poll should detect expiry
        status = queue.poll(request.id)
        
        assert status == RequestStatus.EXPIRED
        assert queue.get_pending_count() == 0


class TestAuthorityWithQueue:
    
    def test_approval_enqueues(self):
        """REQUEST_APPROVAL should enqueue a request."""
        queue = DecisionQueue()
        auth = Authority(TrustModel(base_level=0.1), decision_queue=queue) # Low trust
        
        # High risk -> Approval needed
        level = auth.check_permission(DecisionType.COMMIT_GOAL, "goal_x", risk_score=0.9)
        
        assert level == PermissionLevel.REQUEST_APPROVAL
        assert queue.get_pending_count() == 1
        
        # Verify request details
        oldest = queue.get_oldest_pending()
        assert oldest.decision_type == DecisionType.COMMIT_GOAL
        assert oldest.blocking is True
        
    def test_escalation_enqueues_non_blocking(self):
        """Escalation should enqueue a non-blocking notification."""
        queue = DecisionQueue()
        auth = Authority(decision_queue=queue)
        
        auth.escalate("Test Catastrophe", {"detail": "something broke"})
        
        assert queue.get_pending_count() == 1
        
        oldest = queue.get_oldest_pending()
        assert oldest.decision_type == DecisionType.ESCALATE_FAILURE
        assert oldest.blocking is False # Non-blocking


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
