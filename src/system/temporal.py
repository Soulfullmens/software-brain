"""
Temporal Governance

Controls WHEN the agent acts, not just WHAT it does.
Prevents reaction spirals and ensures long-term coherence.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from enum import Enum
import uuid


class CommitmentStatus(Enum):
    """Status of a deferred commitment."""
    PENDING = "pending"
    COMMITTED = "committed"
    EXECUTED = "executed"
    CANCELED = "canceled"
    EXPIRED = "expired"


class UrgencyLevel(Enum):
    """How urgent is an action?"""
    IMMEDIATE = 0    # Must act now
    SOON = 1         # Within minutes
    NORMAL = 2       # Standard timing
    DEFERRED = 3     # Can wait
    BACKGROUND = 4   # Only when idle


@dataclass
class DeferredCommitment:
    """
    An action proposed now but committed/executed later.
    Can be canceled if context changes.
    """
    id: str
    action_id: str
    action_description: str
    proposed_at: datetime
    
    # Timing
    urgency: UrgencyLevel
    execute_after: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    # Status
    status: CommitmentStatus = CommitmentStatus.PENDING
    
    # Context snapshot for consistency check
    coherence_at_proposal: float = 1.0
    goal_pressure_at_proposal: float = 0.0
    
    # Cancellation
    canceled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    
    def is_ready(self, now: datetime) -> bool:
        """Check if commitment is ready to execute."""
        if self.status != CommitmentStatus.PENDING:
            return False
        if self.expires_at and now > self.expires_at:
            return False
        if self.execute_after and now < self.execute_after:
            return False
        return True
    
    def is_expired(self, now: datetime) -> bool:
        """Check if commitment has expired."""
        return self.expires_at and now > self.expires_at


@dataclass
class IntentionRecord:
    """Record of a past intention for consistency checking."""
    action_id: str
    timestamp: datetime
    decision_id: Optional[str]
    outcome: str  # "executed", "denied", "canceled"


class TemporalGovernor:
    """
    Controls temporal aspects of agent behavior.
    
    Responsibilities:
    - Buffer intentions before execution
    - Track recent actions to prevent thrashing
    - Check temporal consistency of new actions
    - Enable intelligent waiting
    """
    
    def __init__(self):
        # Pending commitments
        self.commitments: Dict[str, DeferredCommitment] = {}
        
        # Recent intention history
        self.intention_history: List[IntentionRecord] = []
        self.max_history = 100
        
        # Thresholds
        self.action_cooldown_seconds = 5.0
        self.same_action_cooldown_seconds = 60.0
        self.max_actions_per_minute = 10
        
        # Tracking
        self.last_action_time: Optional[datetime] = None
        self.actions_this_minute: int = 0
        self._minute_window_start: Optional[datetime] = None
    
    def propose_commitment(
        self,
        action_id: str,
        action_description: str,
        urgency: UrgencyLevel = UrgencyLevel.NORMAL,
        delay_seconds: float = 0,
        ttl_seconds: float = 300,
        coherence: float = 1.0,
        goal_pressure: float = 0.0
    ) -> DeferredCommitment:
        """
        Propose a deferred action commitment.
        """
        now = datetime.now()
        
        commitment = DeferredCommitment(
            id=str(uuid.uuid4()),
            action_id=action_id,
            action_description=action_description,
            proposed_at=now,
            urgency=urgency,
            execute_after=now + timedelta(seconds=delay_seconds) if delay_seconds > 0 else None,
            expires_at=now + timedelta(seconds=ttl_seconds),
            coherence_at_proposal=coherence,
            goal_pressure_at_proposal=goal_pressure
        )
        
        self.commitments[commitment.id] = commitment
        return commitment
    
    def cancel_commitment(self, commitment_id: str, reason: str) -> bool:
        """Cancel a pending commitment."""
        if commitment_id not in self.commitments:
            return False
        
        commitment = self.commitments[commitment_id]
        if commitment.status != CommitmentStatus.PENDING:
            return False
        
        commitment.status = CommitmentStatus.CANCELED
        commitment.canceled_at = datetime.now()
        commitment.cancel_reason = reason
        return True
    
    def get_ready_commitments(self) -> List[DeferredCommitment]:
        """Get commitments ready for execution."""
        now = datetime.now()
        ready = []
        
        for c in self.commitments.values():
            if c.is_expired(now):
                c.status = CommitmentStatus.EXPIRED
            elif c.is_ready(now):
                ready.append(c)
        
        # Sort by urgency
        return sorted(ready, key=lambda c: c.urgency.value)
    
    def mark_executed(self, commitment_id: str, decision_id: Optional[str] = None) -> None:
        """Mark a commitment as executed."""
        if commitment_id in self.commitments:
            commitment = self.commitments[commitment_id]
            commitment.status = CommitmentStatus.EXECUTED
            
            # Record in history
            self._record_intention(
                commitment.action_id,
                decision_id,
                "executed"
            )
    
    def _record_intention(self, action_id: str, decision_id: Optional[str], outcome: str) -> None:
        """Record an intention for history tracking."""
        record = IntentionRecord(
            action_id=action_id,
            timestamp=datetime.now(),
            decision_id=decision_id,
            outcome=outcome
        )
        self.intention_history.append(record)
        
        if len(self.intention_history) > self.max_history:
            self.intention_history = self.intention_history[-self.max_history:]
        
        # Update action tracking
        self._update_action_tracking()
    
    def _update_action_tracking(self) -> None:
        """Update action frequency tracking."""
        now = datetime.now()
        self.last_action_time = now
        
        # Reset minute window if needed
        if self._minute_window_start is None or (now - self._minute_window_start).seconds >= 60:
            self._minute_window_start = now
            self.actions_this_minute = 1
        else:
            self.actions_this_minute += 1
    
    def should_wait(self) -> tuple[bool, Optional[str]]:
        """
        Check if the agent should wait before acting.
        Returns (should_wait, reason).
        """
        now = datetime.now()
        
        # Global cooldown
        if self.last_action_time:
            elapsed = (now - self.last_action_time).total_seconds()
            if elapsed < self.action_cooldown_seconds:
                remaining = self.action_cooldown_seconds - elapsed
                return True, f"Global cooldown ({remaining:.1f}s remaining)"
        
        # Rate limiting
        if self.actions_this_minute >= self.max_actions_per_minute:
            return True, f"Rate limit reached ({self.actions_this_minute}/{self.max_actions_per_minute} this minute)"
        
        return False, None
    
    def check_temporal_consistency(
        self,
        proposed_action: str,
        lookback_minutes: int = 60
    ) -> tuple[bool, Optional[str]]:
        """
        Check if proposed action contradicts recent intentions.
        Returns (is_consistent, contradiction_description).
        """
        cutoff = datetime.now() - timedelta(minutes=lookback_minutes)
        
        recent = [r for r in self.intention_history if r.timestamp >= cutoff]
        
        # Check for same action too recently
        same_action = [r for r in recent if r.action_id == proposed_action]
        if same_action:
            last = same_action[-1]
            elapsed = (datetime.now() - last.timestamp).total_seconds()
            if elapsed < self.same_action_cooldown_seconds:
                return False, f"Same action '{proposed_action}' executed {elapsed:.0f}s ago (cooldown: {self.same_action_cooldown_seconds}s)"
        
        # Check for contradictory patterns
        # E.g., "resolve_contradiction" followed immediately by same action
        if len(recent) >= 3:
            last_three = [r.action_id for r in recent[-3:]]
            if len(set(last_three)) == 1:
                return False, f"Stuck in loop: '{last_three[0]}' repeated 3+ times"
        
        return True, None
    
    def can_act_now(self, proposed_action: str) -> tuple[bool, Optional[str]]:
        """
        Combined check: should we act now with this action?
        """
        # Wait check
        should_wait, wait_reason = self.should_wait()
        if should_wait:
            return False, wait_reason
        
        # Consistency check
        is_consistent, inconsistency = self.check_temporal_consistency(proposed_action)
        if not is_consistent:
            return False, inconsistency
        
        return True, None
    
    def summary(self) -> dict:
        """Summary of temporal state."""
        now = datetime.now()
        pending = [c for c in self.commitments.values() if c.status == CommitmentStatus.PENDING]
        ready = self.get_ready_commitments()
        
        return {
            "pending_commitments": len(pending),
            "ready_commitments": len(ready),
            "recent_intentions": len(self.intention_history),
            "actions_this_minute": self.actions_this_minute,
            "last_action": self.last_action_time.isoformat() if self.last_action_time else None
        }
