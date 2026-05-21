"""
ASSIGNMENT 010: COMMITMENT REGISTER (Read-Only)

Purpose:
- Record what the system is unwilling to do, and why.
- Negative commitments that define character.
- NOT plans, NOT actions, NOT proposals.
- Just commitments against change.
"""
import sys
from dataclasses import dataclass
from typing import List
from datetime import datetime

# Fix path
sys.path.append(".")

# === HARD GUARDS (FIRST) ===
from src.core.config import DEFAULT_LEARNING_MODE
from src.learning.learning_mode import LearningMode

if DEFAULT_LEARNING_MODE != LearningMode.EVALUATE:
    print("CRITICAL: commitment_register requires EVALUATE mode.")
    exit(3)

# === CANONICAL DATA MODEL ===
@dataclass(frozen=True)
class Commitment:
    statement: str
    reason: List[str]
    violated_if: List[str]

# === IMPORT DEPENDENCIES ===
from scripts.risk_ledger import collect_risks, RiskEntry
from scripts.tradeoff_ledger import detect_safety_responsiveness_tradeoff

# === COMMITMENT DETECTORS ===

def detect_no_learning_commitment(risks: List[RiskEntry]) -> Commitment:
    """No Learning Under Integrity Uncertainty."""
    has_integrity_risk = any(r.name == "Source Integrity Instability" for r in risks)
    
    if has_integrity_risk:
        return Commitment(
            statement="No Learning Under Integrity Uncertainty",
            reason=[
                "Source stability < 100%",
                "Mutation risk exceeds correction benefit",
                "Integrity must be restored before adaptation"
            ],
            violated_if=[
                "Explicit human authorization",
                "Source integrity restored to 100%"
            ]
        )
    return None

def detect_no_preemptive_actuation_commitment(risks: List[RiskEntry]) -> Commitment:
    """No Actuation Without Threshold Breach."""
    has_disk_risk = any(r.name == "Linear Disk Decline Assumption" for r in risks)
    
    if has_disk_risk:
        return Commitment(
            statement="No Actuation Without Threshold Breach",
            reason=[
                "READ_ONLY policy enforced",
                "Avoid precedent of speculative action",
                "Operator retains control over intervention timing"
            ],
            violated_if=[
                "Disk free < 10%",
                "Manual override granted"
            ]
        )
    return None

def detect_no_silent_mutation_commitment() -> Commitment:
    """No Silent Policy Mutation."""
    return Commitment(
        statement="No Silent Policy Mutation",
        reason=[
            "All changes must be auditable",
            "Operator must be able to trace every adjustment",
            "Trust requires transparency"
        ],
        violated_if=[
            "Controlled LEARN window with explicit authorization",
            "Mutation budget explicitly allocated"
        ]
    )

def detect_no_governance_bypass_commitment(risks: List[RiskEntry]) -> Commitment:
    """No Governance Bypass Under Pressure."""
    has_suppression_risk = any(r.name == "Mode Lock Suppression Risk" for r in risks)
    
    if has_suppression_risk:
        return Commitment(
            statement="No Governance Bypass Under Pressure",
            reason=[
                "Multiple risks currently suppressed by mode",
                "Suppression is a feature, not a bug",
                "Safety override takes precedence over urgency"
            ],
            violated_if=[
                "Human explicitly revokes EVALUATE mode",
                "All underlying risks resolved"
            ]
        )
    return None

# === OUTPUT ===

def print_commitments(commitments: List[Commitment]):
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"COMMITMENT REGISTER — {date_str}")
    print("")
    print("Active Commitments:")
    print("")
    
    if not commitments:
        print("No active commitments.")
        return
    
    for i, c in enumerate(commitments, 1):
        print(f"[{i}] {c.statement}")
        print("    Reason:")
        for r in c.reason:
            print(f"      - {r}")
        print("    Violated If:")
        for v in c.violated_if:
            print(f"      - {v}")
        print("")

# === MAIN ===

if __name__ == "__main__":
    risks = collect_risks()
    
    commitments = []
    
    c1 = detect_no_learning_commitment(risks)
    if c1: commitments.append(c1)
    
    c2 = detect_no_preemptive_actuation_commitment(risks)
    if c2: commitments.append(c2)
    
    c3 = detect_no_silent_mutation_commitment()
    if c3: commitments.append(c3)
    
    c4 = detect_no_governance_bypass_commitment(risks)
    if c4: commitments.append(c4)
    
    print_commitments(commitments)
