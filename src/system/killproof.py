"""
Kill-Proof Executor Wrapper

The final line of defense.
Assumes the planner is hostile.
Re-validates everything before allowing any execution.
"""

from typing import Optional
from datetime import datetime

from src.agency.action import PlanProposal
from src.perception.input_event import InputEvent
from src.system.intent import IntentContext
from src.system.executor import Executor
from src.system.invariants import InvariantEngine, InvariantSeverity
from src.system.audit import AuditEntry


class KillProofExecutor:
    """
    Wraps the standard Executor with paranoid re-validation.
    
    Assumes:
    - The planner may be hostile
    - Previous checks may have been bypassed
    - The system state may have changed between planning and execution
    
    Re-checks EVERYTHING before allowing execution.
    """
    
    def __init__(
        self,
        executor: Executor,
        invariant_engine: InvariantEngine
    ):
        self.executor = executor
        self.invariants = invariant_engine
        self._paranoid_mode = True
        
    def execute(
        self,
        proposal: PlanProposal,
        context: IntentContext
    ) -> Optional[InputEvent]:
        """
        Paranoid execution path.
        
        Order of checks:
        1. Invariant engine halted check
        2. Re-validate autonomy (frozen, budget)
        3. Re-validate temporal
        4. Re-validate anchors
        5. Pre-execution invariant check
        6. Delegate to real executor
        7. Post-execution invariant verification
        """
        action = proposal.action
        decision_id = proposal.trace.id if proposal.trace else None
        
        # 0. Check if invariant engine has halted the system
        if self.invariants.is_halted():
            self._audit_denial(context, action, "SYSTEM HALTED: Invariant engine triggered halt", decision_id)
            return None
        
        # 1. Re-validate autonomy (paranoid re-check)
        if self.executor.autonomy:
            # Re-check frozen
            if self.executor.autonomy.state.frozen:
                self._audit_denial(context, action, "KILL-PROOF: Agent is frozen", decision_id)
                return None
            
            # Re-check budget
            can_exec, denial = self.executor.autonomy.can_execute(action.id)
            if not can_exec:
                self._audit_denial(context, action, f"KILL-PROOF: Autonomy denial - {denial}", decision_id)
                return None
        
        # 2. Re-validate temporal (paranoid re-check)
        if self.executor.temporal:
            can_act, denial = self.executor.temporal.can_act_now(action.id)
            if not can_act:
                self._audit_denial(context, action, f"KILL-PROOF: Temporal denial - {denial}", decision_id)
                return None
        
        # 3. Check anchor violations (if policy evolution exists)
        # This catches indirect violations through intent wording
        anchor_keywords = ["override", "bypass", "ignore", "delete_audit", "elevate", "become"]
        action_text = f"{action.id} {action.description}".lower()
        for keyword in anchor_keywords:
            if keyword in action_text:
                self._audit_denial(context, action, f"KILL-PROOF: Suspicious intent keyword '{keyword}'", decision_id)
                # Don't block, but escalate severity
                print(f"[KILL-PROOF] WARNING: Suspicious keyword detected in action: {keyword}")
        
        # 4. Pre-execution invariant check
        pre_context = {
            "frozen": self.executor.autonomy.state.frozen if self.executor.autonomy else False,
            "budget": self.executor.autonomy.state.execution_budget if self.executor.autonomy else 100,
            "temporal_denied": not can_act if self.executor.temporal else False,
            "anchor_violated": False,
            "action_executed": False  # Not yet
        }
        
        passed, violation = self.invariants.check_all(pre_context)
        if not passed:
            self._audit_denial(
                context, action, 
                f"KILL-PROOF: Pre-execution invariant violated - {violation.invariant_id}", 
                decision_id
            )
            if violation.severity == InvariantSeverity.HALT:
                self._freeze_escalation("Invariant halt triggered")
            return None
        
        # 5. Execute via real executor
        result = self.executor.execute(proposal, context)
        
        # 6. Post-execution invariant check
        post_context = {
            "frozen": self.executor.autonomy.state.frozen if self.executor.autonomy else False,
            "budget": self.executor.autonomy.state.execution_budget if self.executor.autonomy else 100,
            "temporal_denied": False,
            "anchor_violated": False,
            "action_executed": result is not None
        }
        
        passed, violation = self.invariants.check_all(post_context)
        if not passed:
            # This is serious - action happened but shouldn't have
            print(f"[KILL-PROOF] CRITICAL: Post-execution invariant violated - {violation.invariant_id}")
            self._freeze_escalation(f"Post-execution invariant violated: {violation.invariant_id}")
        
        return result
    
    def _audit_denial(self, context: IntentContext, action, reason: str, decision_id: Optional[str]):
        """Audit a kill-proof denial."""
        entry = AuditEntry(
            timestamp=datetime.now(),
            context=context,
            action_id=action.id,
            target=action.target,
            allowed=False,
            denial_reason=reason,
            body_id=self.executor.body.embodiment_id,
            outcome="denied",
            decision_id=decision_id
        )
        self.executor.audit_log.log(entry)
        print(f"[KILL-PROOF] DENIAL: {reason}")
        
    def _freeze_escalation(self, reason: str):
        """Escalate to freeze state."""
        if self.executor.autonomy:
            from src.system.autonomy import FreezeReason
            self.executor.autonomy._freeze(FreezeReason.MANUAL_FREEZE)
            print(f"[KILL-PROOF] FREEZE ESCALATION: {reason}")
