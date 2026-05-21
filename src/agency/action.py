"""
Action Definitions

Dumb, declarative action carriers.
No execution logic.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Any
# Avoid circular import by using forward reference or TYPE_CHECKING if needed
# But DecisionTrace is in .decision, which has no deps on action.
from .decision import DecisionTrace
from src.cognition.prediction import Prediction


@dataclass
class Action:
    """
    A proposed action.
    
    Phase 25.1: Actions now declare their risk profile.
    This enables Authority to gate individual actions, not just goals.
    """
    id: str  # Unique ID (e.g., "write_file" or "delete_file")
    description: str
    rationale: str
    target: Optional[str] = None  # Affected entity/prediction ID
    
    # Risk Profile (Phase 25.1)
    irreversible: bool = False  # Can this action be undone?
    estimated_cost: float = 1.0  # Resource cost (arbitrary units)
    risk_domain: str = "general"  # Domain: "filesystem", "network", "compute", "identity"


@dataclass
class PlanProposal:
    """
    A single-step plan proposal.
    Wraps an action with expectations.
    """
    action: Action
    confidence: float
    expected_effects: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    
    # Why did we propose this?
    trace: Optional[DecisionTrace] = None
