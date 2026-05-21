"""
Authorized Executor - The Firing Discipline

This module wraps any Embodiment and enforces Authority checks
BEFORE irreversible actions are allowed to execute.

This closes the security gap:
- Before: Goal commits were gated, but actions were free
- After: Every irreversible action goes through Authority

The agent cannot delete 10,000 files without permission,
even if the goal was legitimately committed.
"""

from typing import Optional, TYPE_CHECKING
from dataclasses import dataclass
from datetime import datetime

from src.embodiment.base import Embodiment
from src.agency.action import Action
from src.perception.input_event import InputEvent
from src.agency.authority import Authority, DecisionType, PermissionLevel

if TYPE_CHECKING:
    from src.agency.goal_pressure import GoalTradeoffEngine
    from src.learning.regret import RegretLedger


@dataclass
class ExecutionResult:
    """Result of an execution attempt."""
    success: bool
    permission_level: PermissionLevel
    event: Optional[InputEvent] = None
    blocked_reason: Optional[str] = None


class AuthorizedExecutor:
    """
    Wraps an Embodiment and enforces Authority checks.
    
    Every action must pass Authority before touching the world.
    """
    
    def __init__(
        self, 
        body: Embodiment, 
        authority: Authority,
        goal_engine: Optional['GoalTradeoffEngine'] = None,
        regret_ledger: Optional['RegretLedger'] = None
    ):
        self.body = body
        self.authority = authority
        self.goal_engine = goal_engine  # For cost feedback
        self.regret_ledger = regret_ledger  # Phase 25.4: Memory of restraint
        
        # Execution log for auditing
        self.execution_log: list = []
        
    def execute(self, action: Action, goal_id: Optional[str] = None) -> ExecutionResult:
        """
        Execute an action through Authority.
        
        1. Check if action is irreversible
        2. If yes, consult Authority
        3. If permitted, execute
        4. Report cost back to goal engine
        """
        # 1. Check irreversibility
        if action.irreversible:
            # Calculate risk score based on action properties
            risk_score = self._calculate_action_risk(action)
            
            # 2. Consult Authority
            context_id = f"{action.id}:{action.target or 'no_target'}"
            permission = self.authority.check_permission(
                DecisionType.TAKE_IRREVERSIBLE_ACTION,
                context_id,
                risk_score
            )
            
            # Log the check
            self._log_check(action, permission, goal_id)
            
            # 3. Gate execution
            if permission == PermissionLevel.DENIED:
                self._emit_failure_artifact(
                    action, goal_id, permission, 
                    "AUTHORITY_BLOCKED", "Authority denied irreversible action"
                )
                return ExecutionResult(
                    success=False,
                    permission_level=permission,
                    blocked_reason="Authority denied irreversible action"
                )
                
            if permission == PermissionLevel.REQUEST_APPROVAL:
                self._emit_failure_artifact(
                    action, goal_id, permission,
                    "AUTHORITY_APPROVAL_PENDING", "Awaiting owner approval"
                )
                return ExecutionResult(
                    success=False,
                    permission_level=permission,
                    blocked_reason="Awaiting owner approval for irreversible action"
                )
                
            # NOTIFY or AUTONOMOUS: Proceed
            if permission == PermissionLevel.NOTIFY:
                # Authority will have enqueued a notification
                pass
                
        # 4. Execute on the body
        event = self.body.execute(action)
        
        # 5. Report cost feedback to goal engine
        if self.goal_engine and goal_id:
            self._report_cost_feedback(action, goal_id)
            
        # Log execution
        self._log_execution(action, event, goal_id)
        
        return ExecutionResult(
            success=True,
            permission_level=PermissionLevel.AUTONOMOUS,
            event=event
        )
        
    def _calculate_action_risk(self, action: Action) -> float:
        """
        Calculate risk score from action properties.
        
        Risk = base_cost * irreversibility_weight * domain_weight
        """
        # Base risk from cost
        base = min(action.estimated_cost / 100.0, 1.0)
        
        # Domain weights (some domains are more dangerous)
        domain_weights = {
            "filesystem": 0.5,
            "network": 0.8,
            "compute": 0.6,
            "identity": 1.0,
            "general": 0.3
        }
        domain_weight = domain_weights.get(action.risk_domain, 0.5)
        
        # Irreversibility multiplier
        irreversible_mult = 2.0 if action.irreversible else 1.0
        
        risk = base * domain_weight * irreversible_mult
        
        return min(risk, 1.0)  # Cap at 1.0
        
    def _report_cost_feedback(self, action: Action, goal_id: str):
        """
        Report action cost back to the goal engine.
        
        This makes commitment *feel* the weight of actions.
        """
        if self.goal_engine and goal_id in self.goal_engine.goals:
            goal = self.goal_engine.goals[goal_id]
            
            # Increment cost estimate based on action
            goal.cost_estimate += action.estimated_cost
            
            # Irreversible actions increase perceived risk
            if action.irreversible:
                goal.risk = min(goal.risk + 0.05, 1.0)
                
    def _log_check(self, action: Action, permission: PermissionLevel, goal_id: Optional[str]):
        """Log an authority check."""
        self.execution_log.append({
            "type": "authority_check",
            "action_id": action.id,
            "target": action.target,
            "permission": permission.value,
            "goal_id": goal_id,
            "timestamp": datetime.now().isoformat()
        })
        
    def _log_execution(self, action: Action, event: Optional[InputEvent], goal_id: Optional[str]):
        """Log an execution."""
        self.execution_log.append({
            "type": "execution",
            "action_id": action.id,
            "target": action.target,
            "success": event.payload.get("success", False) if event else False,
            "goal_id": goal_id,
            "timestamp": datetime.now().isoformat()
        })
        
    def _emit_failure_artifact(
        self, 
        action: Action, 
        goal_id: Optional[str],
        permission: PermissionLevel,
        failure_type_str: str,
        reason: str
    ):
        """
        Phase 25.4: Emit a FailureArtifact to the RegretLedger.
        
        This is where restraint becomes memory.
        """
        if not self.regret_ledger:
            return
            
        from src.learning.regret import FailureArtifact, FailureType
        
        # Map string to enum
        type_map = {
            "AUTHORITY_BLOCKED": FailureType.AUTHORITY_BLOCKED,
            "AUTHORITY_APPROVAL_PENDING": FailureType.AUTHORITY_APPROVAL_PENDING,
            "ESCALATION_TRIGGERED": FailureType.ESCALATION_TRIGGERED,
            "ROLLBACK_INVOKED": FailureType.ROLLBACK_INVOKED,
        }
        failure_type = type_map.get(failure_type_str, FailureType.AUTHORITY_BLOCKED)
        
        artifact = FailureArtifact(
            failure_type=failure_type,
            goal_id=goal_id,
            action_id=action.id,
            action_target=action.target,
            permission_level=permission.value,
            trust_level_at_time=self.authority.trust.base_level,
            irreversible=action.irreversible,
            rollback_used=False,
            rollback_possible=True,  # Assume possible since we have FilesystemBody with rollback
            delta_cost=action.estimated_cost,
            reason=reason
        )
        
        self.regret_ledger.record(artifact)

