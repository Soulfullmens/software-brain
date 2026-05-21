"""
belief_state.py

The Core State Object for Phase R (Recursive Reasoning).
Stores the evolving understanding of the system, including:
- Active Hypotheses (Ranked & scored)
- Evidence Log (What we have seen)
- Contradictions (What doesn't fit)
- Uncertainty (Global metric)

This state is MUTABLE and evolves over the Reasoning Loop.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from .hypothesis import Hypothesis

@dataclass
class Evidence:
    """A unit of observation that supports or refutes a hypothesis."""
    source: str         # e.g., "grep_search", "structural_profile"
    content: str        # The actual finding
    confidence: float   # How reliable is this evidence? (0.0-1.0)
    timestamp: float    # Logical time (iteration step)
    related_files: List[str] = field(default_factory=list)

@dataclass
class Conflict:
    """A detected contradiction between hypotheses or evidence."""
    hypotheses: List[str] # Statements of conflicting hypotheses
    description: str      # Nature of the conflict
    severity: float       # How critical is this to resolve? (0.0-1.0)

@dataclass
class BeliefState:
    """
    The brain's working memory for a specific problem.
    Tracks the 'World Model' as it shifts from confusion to clarity.
    """
    # Goal Context
    goal: str = "" # Raw text
    goal_plan: Optional['GoalPlan'] = None # Structured Plan
    # Evaluation State
    last_success: bool = True
    last_failure_reason: Optional[str] = None
    
    action_history: List[str] = field(default_factory=list) # Log of executed commands
    
    # Active Understanding
    hypotheses: List[Hypothesis] = field(default_factory=list)
    evidence_log: List[Evidence] = field(default_factory=list)
    contradictions: List[Conflict] = field(default_factory=list)
    
    # Epistemic Metrics
    uncertainty_score: float = 1.0  # 1.0 = Total Confusion, 0.0 = Total Clarity
    confidence_volatility: float = 0.0 # How much did beliefs change last step?
    iteration: int = 0
    
    def update(self, new_evidence: Evidence) -> None:
        """
        Integrate new evidence into the belief state.
        
        Responsibilities (Phase R):
        1. Match evidence to relevant hypotheses.
        2. Bayesian update of hypothesis confidence.
        3. Detect new contradictions.
        4. Re-rank hypotheses.
        5. Update uncertainty and volatility metrics.
        """
        self.evidence_log.append(new_evidence)
        self.iteration += 1
        
        # Placeholder for Recursive Logic (To be designed by User Blueprint)
        pass
