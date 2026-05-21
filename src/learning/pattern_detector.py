"""
Failure Pattern Detector

Analyzes the agent's history to find recurring failure modes.
This is structural introspection, not ML.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from collections import Counter, defaultdict


@dataclass
class FailurePattern:
    """
    A detected pattern of recurring failures.
    """
    id: str
    pattern_type: str  # "prediction_cluster", "contradiction_cycle", "goal_starvation", "heuristic_decay"
    description: str
    severity: float  # 0.0 - 1.0
    occurrences: int
    first_seen: datetime
    last_seen: datetime
    related_ids: List[str] = field(default_factory=list)  # Entity/Goal/Heuristic IDs involved
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.pattern_type,
            "description": self.description,
            "severity": self.severity,
            "occurrences": self.occurrences,
            "span": str(self.last_seen - self.first_seen)
        }


@dataclass
class HeuristicStats:
    """
    Tracks performance of a planning heuristic over time.
    """
    heuristic_id: str
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    last_used: Optional[datetime] = None
    first_used: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        if self.usage_count == 0:
            return 0.5  # Unknown, neutral
        return self.success_count / self.usage_count
    
    @property
    def confidence(self) -> float:
        """
        Confidence decays with:
        - Low success rate
        - Long time since use
        - Low sample size
        """
        base = self.success_rate
        
        # Sample size factor (more data = more confidence)
        sample_factor = min(self.usage_count / 10, 1.0)
        
        # Recency factor (decay if not used recently)
        recency_factor = 1.0
        if self.last_used:
            hours_since = (datetime.now() - self.last_used).total_seconds() / 3600
            recency_factor = max(1.0 - (hours_since / 168), 0.3)  # Decay over a week
        
        return base * sample_factor * recency_factor


class PatternDetector:
    """
    Analyzes agent history to detect recurring failure patterns.
    """
    
    def __init__(self):
        self.patterns: Dict[str, FailurePattern] = {}
        self.heuristic_stats: Dict[str, HeuristicStats] = {}
        
        # Tracking for detection
        self._recent_failures: List[Dict[str, Any]] = []
        self._contradiction_history: List[str] = []  # Entity IDs
        self._goal_starvation_markers: Dict[str, int] = defaultdict(int)
        
    def record_decision_outcome(
        self, 
        heuristic_id: str, 
        success: bool,
        decision_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record the outcome of a decision for pattern analysis."""
        
        # Update heuristic stats
        if heuristic_id not in self.heuristic_stats:
            self.heuristic_stats[heuristic_id] = HeuristicStats(heuristic_id=heuristic_id)
        
        stats = self.heuristic_stats[heuristic_id]
        stats.usage_count += 1
        stats.last_used = datetime.now()
        if stats.first_used is None:
            stats.first_used = datetime.now()
            
        if success:
            stats.success_count += 1
        else:
            stats.failure_count += 1
            self._recent_failures.append({
                "heuristic": heuristic_id,
                "decision_id": decision_id,
                "timestamp": datetime.now(),
                "context": context or {}
            })
            
    def record_contradiction(self, entity_id: str) -> None:
        """Record a contradiction involving an entity."""
        self._contradiction_history.append(entity_id)
        
        # Check for cycle (same entity keeps causing contradictions)
        recent = self._contradiction_history[-20:]
        counts = Counter(recent)
        
        for eid, count in counts.items():
            if count >= 3:
                self._create_or_update_pattern(
                    pattern_type="contradiction_cycle",
                    description=f"Entity '{eid}' repeatedly causes contradictions",
                    severity=min(count / 5, 1.0),
                    related_id=eid
                )
                
    def record_goal_starvation(self, goal_id: str, goal_desc: str) -> None:
        """Record when a goal is starving (no progress for too long)."""
        self._goal_starvation_markers[goal_id] += 1
        
        if self._goal_starvation_markers[goal_id] >= 3:
            self._create_or_update_pattern(
                pattern_type="goal_starvation",
                description=f"Goal '{goal_desc}' consistently starving",
                severity=min(self._goal_starvation_markers[goal_id] / 5, 1.0),
                related_id=goal_id
            )
            
    def _create_or_update_pattern(
        self, 
        pattern_type: str, 
        description: str, 
        severity: float,
        related_id: str
    ) -> FailurePattern:
        """Create or update a failure pattern."""
        import uuid
        
        # Look for existing pattern of same type with same related ID
        pattern_key = f"{pattern_type}:{related_id}"
        
        if pattern_key in self.patterns:
            pattern = self.patterns[pattern_key]
            pattern.occurrences += 1
            pattern.last_seen = datetime.now()
            pattern.severity = max(pattern.severity, severity)
        else:
            pattern = FailurePattern(
                id=str(uuid.uuid4()),
                pattern_type=pattern_type,
                description=description,
                severity=severity,
                occurrences=1,
                first_seen=datetime.now(),
                last_seen=datetime.now(),
                related_ids=[related_id]
            )
            self.patterns[pattern_key] = pattern
            
        return pattern
    
    def analyze_heuristic_health(self) -> List[Dict[str, Any]]:
        """Analyze which heuristics are aging poorly."""
        warnings = []
        
        for hid, stats in self.heuristic_stats.items():
            if stats.usage_count >= 5 and stats.success_rate < 0.4:
                warnings.append({
                    "heuristic": hid,
                    "warning": "low_success_rate",
                    "success_rate": stats.success_rate,
                    "confidence": stats.confidence
                })
            elif stats.confidence < 0.3:
                warnings.append({
                    "heuristic": hid,
                    "warning": "low_confidence",
                    "success_rate": stats.success_rate,
                    "confidence": stats.confidence
                })
                
        return warnings
    
    def get_active_patterns(self, min_severity: float = 0.3) -> List[FailurePattern]:
        """Get patterns above severity threshold."""
        return [p for p in self.patterns.values() if p.severity >= min_severity]
    
    def summary(self) -> dict:
        """Summary of detected patterns."""
        return {
            "total_patterns": len(self.patterns),
            "active_patterns": len(self.get_active_patterns()),
            "heuristics_tracked": len(self.heuristic_stats),
            "recent_failures": len(self._recent_failures)
        }
