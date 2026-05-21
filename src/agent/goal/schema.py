"""
schema.py

Data structures for Goal Interpretation.
Defines the contract between the Interpreter and the Planner.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

@dataclass
class GoalPlan:
    """Structured interpretation of a user goal."""
    intent: str                  # e.g., "GENERATE_REPORT", "OPEN_FILE"
    entities: Dict[str, Any]     # Extracted parameters (e.g., filename, email)
    actions: List[str]           # High-level steps (e.g., ["collect_files", "send_email"])
    
    missing_info: List[str] = field(default_factory=list) # Entities needed but not found
    confidence: float = 0.0      # 0.0 to 1.0
    requires_approval: bool = True
    reasoning: str = ""
