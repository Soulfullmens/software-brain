"""
Bounded Initiative Recovery

How the agent regrows confidence and initiative after recovery.
Without this, the system becomes chronically timid.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from enum import Enum
import math


@dataclass
class InitiativeRecord:
    """Record of initiative-relevant events."""
    timestamp: datetime
    event_type: str  # "success", "failure", "critique", "recovery"
    weight: float    # Impact on initiative score


class InitiativeEngine:
    """
    Manages initiative growth after recovery.
    
    Key principles:
    - Initiative grows slowly with consecutive successes
    - Initiative drops sharply with failures
    - Initiative is bounded by autonomy level
    - Initiative never exceeds safety thresholds
    """
    
    def __init__(self):
        # Current initiative score (0.0 - 1.0)
        self.initiative_score: float = 0.5
        
        # Bounds (never violated)
        self.min_initiative = 0.1
        self.max_initiative = 0.9
        
        # Growth parameters
        self.success_growth = 0.02      # +2% per success
        self.failure_decay = 0.10       # -10% per failure
        self.critique_penalty = 0.05    # -5% per critique
        self.recovery_reset = 0.3       # Reset to 30% after recovery
        
        # Consecutive success tracking
        self.consecutive_successes = 0
        self.consecutive_failures = 0
        
        # History
        self.records: List[InitiativeRecord] = []
        self.max_records = 100
        
        # Confidence thresholds for autonomy promotion
        self.promotion_thresholds = {
            "CAUTIOUS_to_NORMAL": 0.5,
            "NORMAL_to_ELEVATED": 0.8
        }
        
        # Minimum time at level before promotion eligible
        self.min_time_at_level = timedelta(minutes=10)
        self.level_start_time: Optional[datetime] = None
        
    def record_success(self) -> float:
        """Record a successful action. Returns new initiative score."""
        self.consecutive_successes += 1
        self.consecutive_failures = 0
        
        # Bonus for consecutive successes (diminishing returns)
        bonus_multiplier = 1 + math.log1p(self.consecutive_successes) * 0.1
        growth = self.success_growth * bonus_multiplier
        
        self.initiative_score = min(
            self.max_initiative,
            self.initiative_score + growth
        )
        
        self._record("success", growth)
        return self.initiative_score
    
    def record_failure(self) -> float:
        """Record a failed action. Returns new initiative score."""
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        
        # Harsher penalty for consecutive failures
        penalty_multiplier = 1 + self.consecutive_failures * 0.2
        decay = self.failure_decay * penalty_multiplier
        
        self.initiative_score = max(
            self.min_initiative,
            self.initiative_score - decay
        )
        
        self._record("failure", -decay)
        return self.initiative_score
    
    def record_critique(self, severity: float) -> float:
        """Record a self-critique. Returns new initiative score."""
        penalty = self.critique_penalty * severity
        
        self.initiative_score = max(
            self.min_initiative,
            self.initiative_score - penalty
        )
        
        self._record("critique", -penalty)
        return self.initiative_score
    
    def reset_for_recovery(self) -> float:
        """Reset initiative after recovery from freeze."""
        self.initiative_score = self.recovery_reset
        self.consecutive_successes = 0
        self.consecutive_failures = 0
        self.level_start_time = datetime.now()
        
        self._record("recovery", 0)
        return self.initiative_score
    
    def _record(self, event_type: str, weight: float) -> None:
        """Record an initiative event."""
        self.records.append(InitiativeRecord(
            timestamp=datetime.now(),
            event_type=event_type,
            weight=weight
        ))
        
        if len(self.records) > self.max_records:
            self.records = self.records[-self.max_records:]
    
    def check_promotion_eligible(
        self,
        current_level: str,
        coherence: float,
        critique_count: int
    ) -> tuple[bool, Optional[str], str]:
        """
        Check if initiative warrants autonomy promotion.
        Returns (eligible, new_level, reason).
        """
        from src.system.autonomy import AutonomyLevel
        
        # Time gate
        if self.level_start_time:
            time_at_level = datetime.now() - self.level_start_time
            if time_at_level < self.min_time_at_level:
                remaining = (self.min_time_at_level - time_at_level).seconds
                return False, None, f"Minimum time at level not met ({remaining}s remaining)"
        
        # System health gates
        if coherence < 0.6:
            return False, None, f"Coherence too low ({coherence:.2f})"
        
        if critique_count > 2:
            return False, None, f"Too many active critiques ({critique_count})"
        
        # Initiative score gates
        if current_level == "CAUTIOUS":
            threshold = self.promotion_thresholds["CAUTIOUS_to_NORMAL"]
            if self.initiative_score >= threshold:
                return True, "NORMAL", f"Initiative {self.initiative_score:.2f} >= {threshold}"
            return False, None, f"Initiative too low ({self.initiative_score:.2f} < {threshold})"
        
        if current_level == "NORMAL":
            threshold = self.promotion_thresholds["NORMAL_to_ELEVATED"]
            if self.initiative_score >= threshold:
                return True, "ELEVATED", f"Initiative {self.initiative_score:.2f} >= {threshold}"
            return False, None, f"Initiative too low ({self.initiative_score:.2f} < {threshold})"
        
        return False, None, "Already at max level or frozen"
    
    def check_demotion_needed(
        self,
        current_level: str,
        coherence: float,
        critique_count: int
    ) -> tuple[bool, Optional[str], str]:
        """
        Check if initiative warrants autonomy demotion.
        Returns (demote, new_level, reason).
        """
        # Health-based demotion (immediate)
        if coherence < 0.4:
            if current_level in ["ELEVATED", "NORMAL"]:
                return True, "CAUTIOUS", f"Coherence dropped to {coherence:.2f}"
        
        if critique_count >= 4:
            if current_level in ["ELEVATED", "NORMAL"]:
                return True, "CAUTIOUS", f"Critique count reached {critique_count}"
        
        # Initiative-based demotion
        if current_level == "ELEVATED" and self.initiative_score < 0.6:
            return True, "NORMAL", f"Initiative dropped to {self.initiative_score:.2f}"
        
        if current_level == "NORMAL" and self.initiative_score < 0.3:
            return True, "CAUTIOUS", f"Initiative dropped to {self.initiative_score:.2f}"
        
        return False, None, "No demotion needed"
    
    def mark_level_change(self) -> None:
        """Mark when autonomy level changed (for time gating)."""
        self.level_start_time = datetime.now()
    
    def get_risk_tolerance(self) -> float:
        """
        Get current risk tolerance based on initiative.
        Used to influence action selection.
        """
        # Risk tolerance scales with initiative
        # Low initiative = conservative actions only
        # High initiative = can attempt riskier actions
        return self.initiative_score * 0.8  # Max 72% risk tolerance
    
    def summary(self) -> dict:
        """Summary of initiative state."""
        recent = [r for r in self.records if 
                  r.timestamp > datetime.now() - timedelta(hours=1)]
        
        return {
            "initiative_score": round(self.initiative_score, 2),
            "consecutive_successes": self.consecutive_successes,
            "consecutive_failures": self.consecutive_failures,
            "recent_events": len(recent),
            "risk_tolerance": round(self.get_risk_tolerance(), 2)
        }
