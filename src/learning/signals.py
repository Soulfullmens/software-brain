"""
Learning Signals - Inputs to the Learning Engine

These are events that trigger learning.
They are immutably recorded facts about system performance.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional, Any

SignalType = Literal["prediction_failure", "contradiction", "surprise", "decay"]


@dataclass
class LearningSignal:
    """
    An input event for the learning engine.
    """
    type: SignalType
    magnitude: float         # 0.0 to 1.0 (Severity/Importance)
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Optional context (depends on signal type)
    source: Optional[str] = None       # e.g., "vision", "text_input"
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def prediction_failure(cls, prediction_probability: float, source: Optional[str] = None) -> 'LearningSignal':
        """
        Create a signal for a denied prediction.
        Magnitude = the probability we assigned to the failed prediction (high confidence failure = high signal).
        """
        return cls(
            type="prediction_failure",
            magnitude=prediction_probability,
            source=source
        )
        
    @classmethod
    def contradiction(cls, source_lost: str, urgency: float) -> 'LearningSignal':
        """
        Create a signal for a resolved contradiction where a specific source 'lost'.
        """
        return cls(
            type="contradiction",
            magnitude=urgency,
            source=source_lost
        )
