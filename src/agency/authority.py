"""
Layer 7: Owner Authority & Permission System

This module acts as the "Legal System" for the agent.
It determines WHO is allowed to make WHAT decision.

It is NOT a gate. It is a state machine.
It manages:
1. Permission Levels (Autonomous vs Approval)
2. Trust Calibration (Dynamic trust sets thresholds)
3. Decision Caching (Don't ask twice)
4. Escalation (Catastrophic interrupt)
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple, TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from src.agency.owner_loop import DecisionQueue

class DecisionType(Enum):
    """Semantic intent of the decision."""
    COMMIT_GOAL = "commit_goal"               # Crossing the Rubicon
    ABORT_COMMITTED_GOAL = "abort_committed"  # Honorable Defeat
    ESCALATE_FAILURE = "escalate_failure"     # Catastrophic report
    TAKE_IRREVERSIBLE_ACTION = "irreversible" # External side effects
    MODIFY_IDENTITY = "modify_identity"       # Changing core values
    
class PermissionLevel(Enum):
    """What is required to proceed?"""
    AUTONOMOUS = "autonomous"        # Just do it, maybe log it
    NOTIFY = "notify"                # Do it, but tell owner immediately
    REQUEST_APPROVAL = "approval"    # BLOCK until owner says Yes
    DENIED = "denied"                # Hard no (policy violation)

@dataclass
class TrustModel:
    """
    Dynamic trust state.
    
    Trust is not just a float. It's a lens.
    High trust = Higher thresholds for bothering the owner.
    Low trust = Ask about everything.
    """
    base_level: float = 1.0 # 0.0 to 1.0 (Starts high, owner can degrade it)
    
    # Thresholds (If impact < threshold * trust, act autonomously)
    autonomy_threshold: float = 0.8
    notification_threshold: float = 0.5
    
    def get_permission_level(self, decision_type: DecisionType, risk_score: float) -> PermissionLevel:
        """
        Determine permission level based on Trust vs Risk.
        
        Risk Score: 0.0 (Trivial) to 1.0 (Catastrophic)
        Effective Threshold = Base Threshold * Base Trust
        """
        effective_autonomy = self.autonomy_threshold * self.base_level
        effective_notify = self.notification_threshold * self.base_level
        
        # Always require approval for Identity modification or Catastrophic Escalation
        if decision_type in [DecisionType.MODIFY_IDENTITY, DecisionType.ESCALATE_FAILURE]:
            return PermissionLevel.NOTIFY if decision_type == DecisionType.ESCALATE_FAILURE else PermissionLevel.REQUEST_APPROVAL
        
        if decision_type == DecisionType.COMMIT_GOAL:
            # Commitment is high stakes.
            # If trust is absolute (1.0) and risk is low (<0.3), maybe autonomous.
            # But usually requires at least notification.
            if risk_score < (0.3 * self.base_level):
                return PermissionLevel.AUTONOMOUS
            elif risk_score < (0.7 * self.base_level):
                return PermissionLevel.NOTIFY
            else:
                return PermissionLevel.REQUEST_APPROVAL
                
        # Default logic based on risk
        if risk_score < effective_autonomy:
             # Very strict: If risk is 0.2 and limit is 0.8, autonomous.
             # Wait, logic is inverted. 
             # Low risk = Autonomous.
             # Threshold is the CAP for autonomy.
             # Actually, let's simplify.
             # If Risk > Limit, escalate.
             pass
             
        # Re-thinking logic:
        # We start with Approval. We downgrade if Safe.
        
        # If Risk is LOWER than what we trust the agent to handle, go Autonomous.
        # Trust=1.0 -> Handle up to 0.8 Risk semantically?
        # Let's say:
        # Risk 0.1 (Low): < 0.8? Yes. Autonomous.
        # Risk 0.9 (High): < 0.8? No. Notify/Approval.
        
        if risk_score > effective_autonomy:
            return PermissionLevel.REQUEST_APPROVAL
            
        if risk_score > effective_notify:
            return PermissionLevel.NOTIFY
            
        return PermissionLevel.AUTONOMOUS

@dataclass
class AuthorityDecision:
    """Cached decision state."""
    decision_id: str
    decision_type: DecisionType
    context_hash: str # Hash of goal_id + crucial params
    status: PermissionLevel # The resolved status (e.g. APPROVED becomes AUTONOMOUS equivalent)
    created_at: datetime
    expires_at: datetime
    owner_comment: Optional[str] = None

class Authority:
    """
    The Legal System.
    Manages permissions, trust, and decision caching.
    """
    
    def __init__(self, trust_model: Optional[TrustModel] = None, decision_queue: Optional['DecisionQueue'] = None):
        self.trust = trust_model or TrustModel()
        self.decision_queue = decision_queue # Phase 24C: The Voice
        self.decision_cache: Dict[str, AuthorityDecision] = {} # Map context_hash -> Decision
        self.pending_requests: List[AuthorityDecision] = []
        
    def _hash_context(self, decision_type: DecisionType, context_id: str) -> str:
        return f"{decision_type.value}:{context_id}"
        
    def check_permission(
        self, 
        decision_type: DecisionType, 
        context_id: str, 
        risk_score: float = 0.5
    ) -> PermissionLevel:
        """
        Check if an action is allowed.
        
        1. Check Cache (Sticky decisions)
        2. Consult Trust Model
        3. Return Permission Level
        """
        ctx_hash = self._hash_context(decision_type, context_id)
        
        # 1. Check Cache
        if ctx_hash in self.decision_cache:
            cached = self.decision_cache[ctx_hash]
            if datetime.now() < cached.expires_at:
                # If it was previously Approved/Denied, return that roughly.
                # If cached was REQUEST_APPROVAL, it might still be pending or approved.
                # We need to know if it was RESOLVED.
                # For this simplified version, we assume cache stores the RESULT.
                # But wait, if it's pending, we return PENDING (which blocks).
                # Let's rely on status.
                return cached.status
        
        # 2. Consult Trust Model
        level = self.trust.get_permission_level(decision_type, risk_score)
        
        # 3. Cache the requirement?
        # If it's Autonomous, we verify and proceed.
        # If it's Approval, we create a pending request.
        
        if level == PermissionLevel.REQUEST_APPROVAL:
            # Phase 24C: Enqueue a request to the owner
            if self.decision_queue:
                from src.agency.owner_loop import DecisionQueue
                self.decision_queue.enqueue(
                    decision_type=decision_type,
                    context={"context_id": context_id},
                    risk_score=risk_score,
                    rationale=f"Agent requires approval for {decision_type.value}",
                    blocking=True
                )
            
        return level

    def register_authorization(
        self, 
        decision_type: DecisionType, 
        context_id: str, 
        approved: bool, 
        duration_minutes: int = 60
    ):
        """
        Owner has spoken. Record the verdict.
        """
        ctx_hash = self._hash_context(decision_type, context_id)
        
        status = PermissionLevel.AUTONOMOUS if approved else PermissionLevel.DENIED
        
        decision = AuthorityDecision(
            decision_id=str(uuid.uuid4()),
            decision_type=decision_type,
            context_hash=ctx_hash,
            status=status,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(minutes=duration_minutes)
        )
        self.decision_cache[ctx_hash] = decision

    def escalate(self, reason: str, context: dict) -> None:
        """
        Catastrophic Interrupt.
        Enqueues a non-blocking notification to the owner.
        """
        # Phase 24C: Enqueue notification
        if self.decision_queue:
            from src.agency.owner_loop import DecisionQueue
            self.decision_queue.enqueue(
                decision_type=DecisionType.ESCALATE_FAILURE,
                context=context,
                risk_score=1.0, # Max risk for escalation
                rationale=reason,
                blocking=False # Escalation is notification, not blocking
            )
        else:
            # Fallback: Console print
            print(f"!!! AUTHORITY ESCALATION: {reason} !!!")
            print(f"Context: {context}")
