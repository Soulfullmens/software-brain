"""
ASSIGNMENT 009: TRADEOFF LEDGER (Read-Only)

Purpose:
- Model value tensions without resolution.
- Expose incompatible truths coexisting.
- "What values are in tension, and what is the cost of honoring each?"
- NOT optimization. NOT decision-making.
"""
import sys
from dataclasses import dataclass
from typing import List, Dict
from datetime import datetime

# Fix path
sys.path.append(".")

# === HARD GUARDS (FIRST) ===
from src.core.config import DEFAULT_LEARNING_MODE
from src.learning.learning_mode import LearningMode

if DEFAULT_LEARNING_MODE != LearningMode.EVALUATE:
    print("CRITICAL: tradeoff_ledger requires EVALUATE mode.")
    exit(3)

# === CANONICAL DATA MODEL ===
@dataclass(frozen=True)
class Tradeoff:
    tension: str
    option_a_name: str
    option_a_preserves: List[str]
    option_a_costs: List[str]
    option_b_name: str
    option_b_preserves: List[str]
    option_b_costs: List[str]
    enforced_by: str

# === IMPORT RISK LEDGER ===
from scripts.risk_ledger import collect_risks, RiskEntry

# === STATIC TRADEOFF DEFINITIONS ===
# These are architectural truths, not computed.

def detect_safety_responsiveness_tradeoff(risks: List[RiskEntry]) -> Tradeoff:
    """Safety vs Responsiveness tension exists when risks are suppressed by mode."""
    has_suppressed = any("LearningMode.EVALUATE" in r.blocked_by for r in risks)
    
    if has_suppressed:
        return Tradeoff(
            tension="Safety vs Responsiveness",
            option_a_name="Maintain EVALUATE mode",
            option_a_preserves=[
                "System integrity",
                "Predictability",
                "Operator trust"
            ],
            option_a_costs=[
                "Prolonged degraded source stability",
                "Delayed remediation",
                "Accumulated technical debt"
            ],
            option_b_name="Enter LEARN mode",
            option_b_preserves=[
                "Adaptive correction",
                "Faster convergence"
            ],
            option_b_costs=[
                "Exposure to mutation risk",
                "Violation of deployment discipline",
                "Potential policy drift"
            ],
            enforced_by="LearningMode.EVALUATE (governance)"
        )
    return None

def detect_integrity_availability_tradeoff(risks: List[RiskEntry]) -> Tradeoff:
    """Integrity vs Availability tension when source instability exists."""
    has_integrity_risk = any(r.name == "Source Integrity Instability" for r in risks)
    
    if has_integrity_risk:
        return Tradeoff(
            tension="Integrity vs Availability",
            option_a_name="Halt on integrity violation",
            option_a_preserves=[
                "Code trustworthiness",
                "Audit trail validity",
                "Immutability guarantee"
            ],
            option_a_costs=[
                "System becomes observational-only",
                "No proactive maintenance",
                "Manual intervention required"
            ],
            option_b_name="Continue despite violation",
            option_b_preserves=[
                "Operational continuity",
                "Uninterrupted monitoring"
            ],
            option_b_costs=[
                "Unknown code state",
                "Compromised trust model",
                "Potential silent corruption"
            ],
            enforced_by="Assignment 001 CRITICAL state"
        )
    return None

def detect_restraint_urgency_tradeoff(risks: List[RiskEntry]) -> Tradeoff:
    """Restraint vs Urgency when disk decline is detected."""
    has_disk_risk = any(r.name == "Linear Disk Decline Assumption" for r in risks)
    
    if has_disk_risk:
        return Tradeoff(
            tension="Restraint vs Urgency",
            option_a_name="Wait for threshold breach",
            option_a_preserves=[
                "Conservative actuation policy",
                "Reduced false positives",
                "Operator control"
            ],
            option_a_costs=[
                "Late intervention",
                "Potential cascade failure",
                "Reduced recovery margin"
            ],
            option_b_name="Proactive cleanup now",
            option_b_preserves=[
                "Safety margin",
                "Early intervention"
            ],
            option_b_costs=[
                "Unnecessary actuation",
                "Violation of READ_ONLY policy",
                "Precedent for preemptive action"
            ],
            enforced_by="ActuationPolicy.READ_ONLY"
        )
    return None

# === OUTPUT ===

def print_tradeoffs(tradeoffs: List[Tradeoff]):
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"TRADEOFF LEDGER — {date_str}")
    print("")
    
    if not tradeoffs:
        print("No active value tensions detected.")
        return
    
    for t in tradeoffs:
        print(f"Tension: {t.tension}")
        print("")
        print(f"Option A: {t.option_a_name}")
        print("  Preserves:")
        for p in t.option_a_preserves:
            print(f"    - {p}")
        print("  Costs:")
        for c in t.option_a_costs:
            print(f"    - {c}")
        print("")
        print(f"Option B: {t.option_b_name}")
        print("  Preserves:")
        for p in t.option_b_preserves:
            print(f"    - {p}")
        print("  Costs:")
        for c in t.option_b_costs:
            print(f"    - {c}")
        print("")
        print(f"Current State:")
        print(f"  - Option A enforced by {t.enforced_by}")
        print("")
        print("---")
        print("")

# === MAIN ===

if __name__ == "__main__":
    risks = collect_risks()
    
    tradeoffs = []
    
    t1 = detect_safety_responsiveness_tradeoff(risks)
    if t1: tradeoffs.append(t1)
    
    t2 = detect_integrity_availability_tradeoff(risks)
    if t2: tradeoffs.append(t2)
    
    t3 = detect_restraint_urgency_tradeoff(risks)
    if t3: tradeoffs.append(t3)
    
    print_tradeoffs(tradeoffs)
