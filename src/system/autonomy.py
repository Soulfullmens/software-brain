"""
Autonomy Regulator - The Governor

Dynamic self-restraint based on system state.
Prevents the agent from spiraling into instability.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Set, Optional, Dict, Any
from enum import Enum


class AutonomyLevel(Enum):
    """How much freedom the agent currently has."""
    FROZEN = 0       # Can only observe, no action
    MINIMAL = 1      # Basic safe actions only
    CAUTIOUS = 2     # Limited scope, frequent checks
    NORMAL = 3       # Standard operation
    ELEVATED = 4     # Full autonomy (rare, owner-granted)


class FreezeReason(Enum):
    """Why the agent froze itself."""
    COHERENCE_COLLAPSE = "coherence_collapse"
    PATTERN_ESCALATION = "pattern_escalation"
    GOAL_CONFLICT = "goal_conflict"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CRITIQUE_OVERLOAD = "critique_overload"
    MANUAL_FREEZE = "manual_freeze"


@dataclass
class AutonomyState:
    """Current autonomy status of the agent."""
    level: AutonomyLevel = AutonomyLevel.NORMAL
    
    # Budget
    execution_budget: float = 100.0  # 0-100
    max_budget: float = 100.0
    budget_regen_rate: float = 1.0  # per minute
    
    # Freeze state
    frozen: bool = False
    freeze_reason: Optional[FreezeReason] = None
    frozen_at: Optional[datetime] = None
    
    # Limits at current level
    allowed_action_types: Set[str] = field(default_factory=lambda: {
        "ask_clarification", "generate_prediction", 
        "gather_evidence", "resolve_contradiction"
    })
    max_planning_depth: int = 1
    execution_cooldown_seconds: float = 0.0
    
    # Tracking
    last_execution: Optional[datetime] = None
    executions_this_session: int = 0


class AutonomyRegulator:
    """
    Controls how much freedom the agent has based on system health.
    """
    
    def __init__(self):
        self.state = AutonomyState()
        
        # Thresholds
        self.coherence_freeze_threshold = 0.3
        self.critique_overload_count = 5
        self.pattern_escalation_threshold = 0.8
        
        # Action costs
        self.action_costs = {
            "ask_clarification": 5,
            "generate_prediction": 10,
            "gather_evidence": 15,
            "resolve_contradiction": 20,
            "default": 10
        }
        
        # Level configurations
        self.level_configs = {
            AutonomyLevel.FROZEN: {
                "allowed": set(),
                "depth": 0,
                "cooldown": float('inf')
            },
            AutonomyLevel.MINIMAL: {
                "allowed": {"ask_clarification"},
                "depth": 1,
                "cooldown": 60.0
            },
            AutonomyLevel.CAUTIOUS: {
                "allowed": {"ask_clarification", "gather_evidence"},
                "depth": 1,
                "cooldown": 10.0
            },
            AutonomyLevel.NORMAL: {
                "allowed": {"ask_clarification", "generate_prediction", 
                           "gather_evidence", "resolve_contradiction"},
                "depth": 1,
                "cooldown": 0.0
            },
            AutonomyLevel.ELEVATED: {
                "allowed": {"*"},  # All actions
                "depth": 3,
                "cooldown": 0.0
            }
        }
    
    def evaluate_autonomy(
        self,
        coherence: float,
        recent_critiques: int,
        pattern_severity: float,
        goal_conflicts: int,
        hours_since_human: float
    ) -> AutonomyLevel:
        """
        Evaluate and set the appropriate autonomy level.
        """
        # Check freeze conditions
        freeze_reason = self._check_freeze_conditions(
            coherence, recent_critiques, pattern_severity, goal_conflicts
        )
        
        if freeze_reason:
            self._freeze(freeze_reason)
            return AutonomyLevel.FROZEN
        
        # Unfreeze if conditions improved
        if self.state.frozen and coherence > 0.5 and recent_critiques < 3:
            self._unfreeze()
        
        # Determine level
        if coherence < 0.4 or recent_critiques >= 4:
            level = AutonomyLevel.MINIMAL
        elif coherence < 0.6 or recent_critiques >= 2 or pattern_severity > 0.5:
            level = AutonomyLevel.CAUTIOUS
        elif self.state.execution_budget > 80 and hours_since_human < 1:
            level = AutonomyLevel.ELEVATED
        else:
            level = AutonomyLevel.NORMAL
        
        self._set_level(level)
        return level
    
    def _check_freeze_conditions(
        self,
        coherence: float,
        recent_critiques: int,
        pattern_severity: float,
        goal_conflicts: int
    ) -> Optional[FreezeReason]:
        """Check if any freeze trigger is met."""
        
        if coherence < self.coherence_freeze_threshold:
            return FreezeReason.COHERENCE_COLLAPSE
        
        if recent_critiques >= self.critique_overload_count:
            return FreezeReason.CRITIQUE_OVERLOAD
        
        if pattern_severity >= self.pattern_escalation_threshold:
            return FreezeReason.PATTERN_ESCALATION
        
        if goal_conflicts >= 3:
            return FreezeReason.GOAL_CONFLICT
        
        if self.state.execution_budget <= 0:
            return FreezeReason.BUDGET_EXHAUSTED
        
        return None
    
    def _freeze(self, reason: FreezeReason) -> None:
        """Freeze the agent."""
        self.state.frozen = True
        self.state.freeze_reason = reason
        self.state.frozen_at = datetime.now()
        self._set_level(AutonomyLevel.FROZEN)
        
    def _unfreeze(self) -> None:
        """Unfreeze the agent."""
        self.state.frozen = False
        self.state.freeze_reason = None
        self.state.frozen_at = None
        self._set_level(AutonomyLevel.CAUTIOUS)  # Start cautious after unfreeze
    
    def _set_level(self, level: AutonomyLevel) -> None:
        """Apply level configuration."""
        self.state.level = level
        config = self.level_configs[level]
        self.state.allowed_action_types = config["allowed"]
        self.state.max_planning_depth = config["depth"]
        self.state.execution_cooldown_seconds = config["cooldown"]
    
    def can_execute(self, action_id: str) -> tuple[bool, Optional[str]]:
        """Check if an action can be executed under current constraints."""
        
        # Frozen check
        if self.state.frozen:
            return False, f"Agent frozen: {self.state.freeze_reason.value if self.state.freeze_reason else 'unknown'}"
        
        # Action type check
        if "*" not in self.state.allowed_action_types:
            if action_id not in self.state.allowed_action_types:
                return False, f"Action '{action_id}' not allowed at {self.state.level.name} level"
        
        # Budget check
        cost = self.action_costs.get(action_id, self.action_costs["default"])
        if self.state.execution_budget < cost:
            return False, f"Insufficient budget ({self.state.execution_budget:.1f} < {cost})"
        
        # Cooldown check
        if self.state.last_execution and self.state.execution_cooldown_seconds > 0:
            elapsed = (datetime.now() - self.state.last_execution).total_seconds()
            if elapsed < self.state.execution_cooldown_seconds:
                remaining = self.state.execution_cooldown_seconds - elapsed
                return False, f"Cooldown active ({remaining:.1f}s remaining)"
        
        return True, None
    
    def consume_budget(self, action_id: str) -> float:
        """Consume budget for an action. Returns amount consumed."""
        cost = self.action_costs.get(action_id, self.action_costs["default"])
        self.state.execution_budget = max(0, self.state.execution_budget - cost)
        self.state.last_execution = datetime.now()
        self.state.executions_this_session += 1
        return cost
    
    def regenerate_budget(self, minutes_elapsed: float) -> float:
        """Regenerate budget over time. Returns amount regenerated."""
        amount = minutes_elapsed * self.state.budget_regen_rate
        old_budget = self.state.execution_budget
        self.state.execution_budget = min(
            self.state.max_budget, 
            self.state.execution_budget + amount
        )
        return self.state.execution_budget - old_budget
    
    def apply_critique_penalty(self, severity: float) -> float:
        """Reduce budget based on self-critique severity."""
        penalty = severity * 20  # Max 20 budget loss per severe critique
        self.state.execution_budget = max(0, self.state.execution_budget - penalty)
        return penalty
    
    def apply_coherence_bonus(self, coherence: float) -> float:
        """Restore budget based on high coherence."""
        if coherence > 0.8:
            bonus = (coherence - 0.8) * 50  # Up to 10 bonus for perfect coherence
            self.state.execution_budget = min(
                self.state.max_budget,
                self.state.execution_budget + bonus
            )
            return bonus
        return 0.0
    
    def summary(self) -> dict:
        """Summary of autonomy state."""
        return {
            "level": self.state.level.name,
            "frozen": self.state.frozen,
            "freeze_reason": self.state.freeze_reason.value if self.state.freeze_reason else None,
            "budget": f"{self.state.execution_budget:.1f}/{self.state.max_budget}",
            "allowed_actions": list(self.state.allowed_action_types),
            "executions_this_session": self.state.executions_this_session
        }
