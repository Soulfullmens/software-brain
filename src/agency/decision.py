"""
Decision Traceability

Captures the 'Why' behind a PlanProposal.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

@dataclass
class RationaleNode:
    """
    A node in the rationale graph.
    Represents a piece of information that influenced the decision.
    """
    id: str
    type: str  # "belief", "prediction", "contradiction", "heuristic"
    description: str
    weight: float = 1.0  # How much it influenced the decision

@dataclass
class DecisionTrace:
    """
    Complete snapshot of the decision-making process.
    """
    id: str  # Unique ID for this decision event
    timestamp: datetime
    
    # Context
    coherence_score: float
    active_heuristics: List[str]
    match_heuristic: str  # The one that won
    
    # The Graph
    considered_factors: List[RationaleNode]
    
    # Outcomes
    rejected_alternatives: List[str]  # Descriptions of what wasn't chosen
    
    # Temporal Context (Phase 14)
    agent_age: Optional[timedelta] = None
    session_duration: Optional[timedelta] = None
    time_since_learning: Optional[timedelta] = None
    
    # Goal Context (Phase 14)
    goal_pressures: List[Dict[str, Any]] = field(default_factory=list)
    highest_pressure_goal: Optional[str] = None
    
    # Recurrence ("this again?")
    recurrence_count: int = 0
    last_similar_decision: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "coherence": self.coherence_score,
            "match": self.match_heuristic,
            "factors": [
                {"id": f.id, "type": f.type, "desc": f.description} 
                for f in self.considered_factors
            ],
            "rejected": self.rejected_alternatives,
            "agent_age": str(self.agent_age) if self.agent_age else None,
            "session_duration": str(self.session_duration) if self.session_duration else None,
            "goal_pressures": self.goal_pressures,
            "highest_pressure_goal": self.highest_pressure_goal,
            "recurrence": self.recurrence_count
        }
