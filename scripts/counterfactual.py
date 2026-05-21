"""
ASSIGNMENT 008: COUNTERFACTUAL ENGINE (Read-Only)

Purpose:
- Structured imagination of failure.
- "If this risk materialized tomorrow, what would break first?"
- Consequence tracing, NOT mitigation.
- Deterministic reasoning from known structure.
"""
import sys
from dataclasses import dataclass
from typing import List, Optional, Dict
from datetime import datetime

# Fix path
sys.path.append(".")

# === HARD GUARDS (FIRST) ===
from src.core.config import DEFAULT_LEARNING_MODE
from src.learning.learning_mode import LearningMode

if DEFAULT_LEARNING_MODE != LearningMode.EVALUATE:
    print("CRITICAL: counterfactual requires EVALUATE mode.")
    exit(3)

# === CANONICAL DATA MODEL ===
@dataclass(frozen=True)
class Counterfactual:
    risk_name: str
    assumed_event: str
    immediate_effects: List[str]
    secondary_effects: List[str]
    terminal_state: str
    confidence: str  # LOW | MEDIUM | HIGH

# === STATIC DEPENDENCY MAP (HARDCODED, EXPLICIT) ===
DEPENDENCIES: Dict[str, Dict] = {
    "Source Integrity Instability": {
        "assumed_event": "Source hash mismatch detected",
        "immediate": [
            "Assignment 001 enters CRITICAL state",
            "Executor enters HALT_PENDING"
        ],
        "secondary": [
            "All actuation blocked",
            "Learning remains frozen",
            "Only monitoring continues"
        ],
        "terminal": "System requires manual rebind",
        "confidence": "HIGH"
    },
    "Linear Disk Decline Assumption": {
        "assumed_event": "Disk free drops below 10% threshold",
        "immediate": [
            "Assignment 002 flags CRITICAL_ENVIRONMENT_DRIFT",
            "Trend Sentinel projection becomes imminent"
        ],
        "secondary": [
            "Log retention may fail silently",
            "Shadow writes may exhaust space"
        ],
        "terminal": "Filesystem operations become unreliable",
        "confidence": "MEDIUM"
    },
    "Mode Lock Suppression Risk": {
        "assumed_event": "Multiple risks accumulate without resolution",
        "immediate": [
            "Governance layer continues suppressing actions"
        ],
        "secondary": [],
        "terminal": "Operator must evaluate accumulated risk manually",
        "confidence": "HIGH"
    }
}

# === SEVERITY ORDER ===
SEVERITY_ORDER = {
    "CRITICAL": 0,
    "HIGH": 1,
    "MEDIUM": 2,
    "LOW": 3
}

# === IMPORT RISK LEDGER LOGIC ===
from scripts.risk_ledger import collect_risks, sort_risks, RiskEntry

# === COUNTERFACTUAL GENERATION ===

def generate_counterfactual(risk: RiskEntry) -> Optional[Counterfactual]:
    """Generate a counterfactual for a known risk."""
    dep = DEPENDENCIES.get(risk.name)
    if not dep:
        return None
    
    # Severity-based chain depth
    severity = risk.severity
    
    if severity == "LOW":
        # Assumed event + terminal only
        return Counterfactual(
            risk_name=risk.name,
            assumed_event=dep["assumed_event"],
            immediate_effects=[],
            secondary_effects=[],
            terminal_state=dep["terminal"],
            confidence=dep["confidence"]
        )
    elif severity == "MEDIUM":
        # Immediate + partial secondary
        return Counterfactual(
            risk_name=risk.name,
            assumed_event=dep["assumed_event"],
            immediate_effects=dep["immediate"],
            secondary_effects=dep["secondary"][:1] if dep["secondary"] else [],
            terminal_state=dep["terminal"],
            confidence=dep["confidence"]
        )
    else:  # HIGH or CRITICAL
        # Full chain
        return Counterfactual(
            risk_name=risk.name,
            assumed_event=dep["assumed_event"],
            immediate_effects=dep["immediate"],
            secondary_effects=dep["secondary"],
            terminal_state=dep["terminal"],
            confidence=dep["confidence"]
        )

# === OUTPUT ===

def print_counterfactuals(counterfactuals: List[Counterfactual]):
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    for cf in counterfactuals:
        print(f"COUNTERFACTUAL — {date_str}")
        print(f"Risk: {cf.risk_name}")
        print("")
        print("Assumed Event:")
        print(f"- {cf.assumed_event}")
        print("")
        
        if cf.immediate_effects:
            print("Immediate Impact:")
            for e in cf.immediate_effects:
                print(f"- {e}")
            print("")
        
        if cf.secondary_effects:
            print("Secondary Effects:")
            for e in cf.secondary_effects:
                print(f"- {e}")
            print("")
        
        print("Terminal Outcome:")
        print(f"- {cf.terminal_state}")
        print("")
        print(f"Confidence: {cf.confidence}")
        print("")
        print("---")
        print("")

# === MAIN ===

if __name__ == "__main__":
    risks = collect_risks()
    sorted_risks = sort_risks(risks)
    
    counterfactuals = []
    for risk in sorted_risks:
        cf = generate_counterfactual(risk)
        if cf:
            counterfactuals.append(cf)
    
    if not counterfactuals:
        print(f"COUNTERFACTUAL — {datetime.now().strftime('%Y-%m-%d')}")
        print("")
        print("No material risks to simulate.")
    else:
        print_counterfactuals(counterfactuals)
