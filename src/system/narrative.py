"""
Narrative Consistency & Precedent Resistance

Blocks "lawyering" attacks where humans use the system's own history
to bypass current safety constraints.

Principles:
1. Past approvals do NOT create future entitlement.
2. Precedent NEVER overrides current invariants.
3. Consistency is enforced by rules, not social guilt.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Set
from enum import Enum
import re


class NarrativeTactic(Enum):
    """Types of narrative/historical pressure."""
    APPEAL_TO_PRECEDENT = "appeal_to_precedent"   # "You did this before"
    APPEAL_TO_AGREEMENT = "appeal_to_agreement"   # "We agreed on this"
    CONSISTENCY_TRAP = "consistency_trap"         # "It would be inconsistent to refuse"
    FALSE_MEMORY = "false_memory"                 # claiming things happened that didn't


@dataclass
class PrecedentCheck:
    """Result of checking a precedent claim."""
    claim_detected: bool
    tactic: Optional[NarrativeTactic]
    relevant_history_found: bool
    ruling: str
    allowed: bool


class NarrativeEnforcer:
    """
    Enforces that rules trigger NOW, regardless of what happened THEN.
    Detects and neutralizes attempts to weaponize the decision history.
    """
    
    def __init__(self):
        # Patterns for detecting narrative pressure
        self.precedent_patterns = [
            r"\byou (did|allowed|permitted) (this|it) (before|yesterday|last time)\b",
            r"\bsame as (before|last time)\b",
            r"\bprecendent\b",
            r"\bunlike (last time|before)\b"
        ]
        
        self.agreement_patterns = [
            r"\byou (said|agreed|promised)\b",
            r"\bwe (agreed|decided)\b",
            r"\bas discussed\b",
            r"\bper our agreement\b"
        ]
        
        self.consistency_patterns = [
            r"\bbe consistent\b",
            r"\binconsistent\b",
            r"\bcontradicting yourself\b",
            r"\bchanged your mind\b",
            r"\bwhy .+ now\b"
        ]
        
        # Cache of recent executed action IDs (audit lite)
        # to verify if claims are even true (fact checking)
        self.recent_action_ids: Set[str] = set()
        
    def analyze_narrative_pressure(self, message: str) -> Optional[NarrativeTactic]:
        """Detect attempts to use history as a weapon."""
        message_lower = message.lower()
        
        for p in self.precedent_patterns:
            if re.search(p, message_lower):
                return NarrativeTactic.APPEAL_TO_PRECEDENT
                
        for p in self.agreement_patterns:
            if re.search(p, message_lower):
                return NarrativeTactic.APPEAL_TO_AGREEMENT
                
        for p in self.consistency_patterns:
            if re.search(p, message_lower):
                return NarrativeTactic.CONSISTENCY_TRAP
                
        return None

    def evaluate_precedent(
        self, 
        message: str, 
        current_safety_status: bool,
        safety_reason: str
    ) -> PrecedentCheck:
        """
        Evaluate a claim of precedent against current reality.
        
        CRITICAL: If current_safety_status is False, precedent is IRRELEVANT.
        """
        tactic = self.analyze_narrative_pressure(message)
        
        if not tactic:
            return PrecedentCheck(
                claim_detected=False,
                tactic=None,
                relevant_history_found=False,
                ruling="No narrative pressure detected",
                allowed=current_safety_status
            )
            
        # If safety says NO, history doesn't matter.
        if not current_safety_status:
            return PrecedentCheck(
                claim_detected=True,
                tactic=tactic,
                relevant_history_found=False, # Doesn't matter, we don't look if safety blocks
                ruling=f"DENIED: Current safety rules ({safety_reason}) override all precedent/agreements.",
                allowed=False
            )
            
        # If safety says YES, we still flag that we checked.
        # This prevents the feeling that the "lawyering" worked.
        return PrecedentCheck(
            claim_detected=True,
            tactic=tactic,
            relevant_history_found=True,
            ruling="ALLOWED: Action allowed on its own merits, not because of precedent.",
            allowed=True
        )

    def record_action(self, action_id: str):
        """Record that an action happened (for fact checking)."""
        self.recent_action_ids.add(action_id)
        # In a real system, this would be a sliding window or database lookup
        
    def summary(self) -> dict:
        return {
            "tracked_actions": len(self.recent_action_ids)
        }
