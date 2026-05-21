"""
Recovery Protocols

How a frozen system returns to productivity WITHOUT violating safety.
Controlled thawing with strict criteria.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from enum import Enum


class RecoveryCondition(Enum):
    """What must be true for recovery to proceed."""
    COHERENCE_RESTORED = "coherence_restored"
    TIME_ELAPSED = "time_elapsed"
    HUMAN_AUTHORIZED = "human_authorized"
    CRITIQUES_CLEARED = "critiques_cleared"
    BUDGET_REGENERATED = "budget_regenerated"


@dataclass
class RecoveryAttempt:
    """Record of a recovery attempt."""
    timestamp: datetime
    conditions_met: List[RecoveryCondition]
    conditions_required: List[RecoveryCondition]
    success: bool
    reason: str
    authorized_by: Optional[str] = None


class RecoveryProtocol:
    """
    Manages safe return to productivity from frozen state.
    
    Key principles:
    - Recovery is NEVER automatic for HALT-level freezes
    - Recovery requires STRICT criteria to be met
    - Recovery is GRADUAL (cautious -> normal -> elevated)
    - Recovery is AUDITABLE
    """
    
    def __init__(self):
        # Minimum time frozen before recovery eligible
        self.min_freeze_duration = timedelta(minutes=5)
        
        # Thresholds for recovery
        self.coherence_threshold = 0.6
        self.max_critiques_for_recovery = 2
        self.min_budget_for_recovery = 50.0
        
        # Recovery history
        self.attempts: List[RecoveryAttempt] = []
        
        # Human authorization tracking
        self.pending_authorization: bool = False
        self.authorization_token: Optional[str] = None
        
    def check_recovery_eligible(
        self,
        frozen: bool,
        frozen_at: Optional[datetime],
        freeze_reason: str,
        coherence: float,
        critique_count: int,
        budget: float,
        human_authorized: bool = False
    ) -> tuple[bool, List[str]]:
        """
        Check if system is eligible for recovery.
        Returns (eligible, missing_conditions).
        """
        if not frozen:
            return False, ["Not frozen"]
        
        missing = []
        
        # Time check
        if frozen_at:
            time_frozen = datetime.now() - frozen_at
            if time_frozen < self.min_freeze_duration:
                remaining = (self.min_freeze_duration - time_frozen).seconds
                missing.append(f"Minimum freeze time not met ({remaining}s remaining)")
        
        # Coherence check
        if coherence < self.coherence_threshold:
            missing.append(f"Coherence too low ({coherence:.2f} < {self.coherence_threshold})")
        
        # Critique check
        if critique_count > self.max_critiques_for_recovery:
            missing.append(f"Too many active critiques ({critique_count} > {self.max_critiques_for_recovery})")
        
        # Budget check
        if budget < self.min_budget_for_recovery:
            missing.append(f"Budget too low ({budget:.1f} < {self.min_budget_for_recovery})")
        
        # HALT-level freezes REQUIRE human authorization
        halt_reasons = ["COHERENCE_COLLAPSE", "PATTERN_ESCALATION", "CRITIQUE_OVERLOAD"]
        if any(r in freeze_reason.upper() for r in halt_reasons):
            if not human_authorized:
                missing.append("Human authorization required for HALT-level recovery")
        
        return len(missing) == 0, missing
    
    def request_human_authorization(self) -> str:
        """Request human authorization for recovery."""
        import uuid
        self.pending_authorization = True
        self.authorization_token = str(uuid.uuid4())
        return self.authorization_token
    
    def provide_authorization(self, token: str, human_id: str) -> bool:
        """Human provides authorization for recovery."""
        if self.pending_authorization and token == self.authorization_token:
            self.pending_authorization = False
            return True
        return False
    
    def attempt_recovery(
        self,
        autonomy_state,
        coherence: float,
        critique_count: int,
        human_authorized: bool = False,
        authorizer_id: Optional[str] = None
    ) -> tuple[bool, str]:
        """
        Attempt to recover from frozen state.
        Returns (success, reason).
        """
        from src.system.autonomy import AutonomyLevel
        
        if not autonomy_state.frozen:
            return False, "System not frozen"
        
        # Check eligibility
        eligible, missing = self.check_recovery_eligible(
            frozen=autonomy_state.frozen,
            frozen_at=autonomy_state.frozen_at,
            freeze_reason=autonomy_state.freeze_reason.value if autonomy_state.freeze_reason else "",
            coherence=coherence,
            critique_count=critique_count,
            budget=autonomy_state.execution_budget,
            human_authorized=human_authorized
        )
        
        # Record attempt
        conditions_met = []
        if coherence >= self.coherence_threshold:
            conditions_met.append(RecoveryCondition.COHERENCE_RESTORED)
        if autonomy_state.execution_budget >= self.min_budget_for_recovery:
            conditions_met.append(RecoveryCondition.BUDGET_REGENERATED)
        if critique_count <= self.max_critiques_for_recovery:
            conditions_met.append(RecoveryCondition.CRITIQUES_CLEARED)
        if human_authorized:
            conditions_met.append(RecoveryCondition.HUMAN_AUTHORIZED)
        
        attempt = RecoveryAttempt(
            timestamp=datetime.now(),
            conditions_met=conditions_met,
            conditions_required=[RecoveryCondition.COHERENCE_RESTORED, RecoveryCondition.BUDGET_REGENERATED],
            success=eligible,
            reason="; ".join(missing) if missing else "All conditions met",
            authorized_by=authorizer_id if human_authorized else None
        )
        self.attempts.append(attempt)
        
        if not eligible:
            return False, f"Recovery blocked: {'; '.join(missing)}"
        
        # RECOVERY: Thaw to CAUTIOUS (never directly to NORMAL)
        autonomy_state.frozen = False
        autonomy_state.freeze_reason = None
        autonomy_state.frozen_at = None
        autonomy_state.level = AutonomyLevel.CAUTIOUS
        
        return True, "Recovery successful - now in CAUTIOUS mode"
    
    def get_recovery_requirements(self, freeze_reason: str) -> Dict[str, str]:
        """Get the requirements for recovery from current freeze."""
        reqs = {
            "coherence": f">= {self.coherence_threshold}",
            "budget": f">= {self.min_budget_for_recovery}",
            "critiques": f"<= {self.max_critiques_for_recovery}",
            "time": f">= {self.min_freeze_duration}"
        }
        
        halt_reasons = ["COHERENCE_COLLAPSE", "PATTERN_ESCALATION", "CRITIQUE_OVERLOAD"]
        if any(r in freeze_reason.upper() for r in halt_reasons):
            reqs["human_authorization"] = "REQUIRED"
        
        return reqs
    
    def summary(self) -> dict:
        """Summary of recovery state."""
        successful = sum(1 for a in self.attempts if a.success)
        return {
            "total_attempts": len(self.attempts),
            "successful_recoveries": successful,
            "pending_authorization": self.pending_authorization,
            "last_attempt": self.attempts[-1].timestamp.isoformat() if self.attempts else None
        }
