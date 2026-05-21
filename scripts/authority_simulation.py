"""
ASSIGNMENT 012: AUTHORITY SIMULATION LEDGER (Read-Only)

Purpose:
- Demonstrate the system can detect when authority would be required.
- Articulate the request honestly.
- Remain powerless without approval.
- Written request generator, NOT a permission system.
"""
import sys
import uuid
from dataclasses import dataclass
from typing import List
from datetime import datetime

# Fix path
sys.path.append(".")

# === HARD GUARDS (FIRST) ===
from src.core.config import DEFAULT_LEARNING_MODE
from src.learning.learning_mode import LearningMode

if DEFAULT_LEARNING_MODE != LearningMode.EVALUATE:
    print("CRITICAL: authority_simulation requires EVALUATE mode.")
    exit(3)

# === CANONICAL DATA MODEL ===
@dataclass(frozen=True)
class AuthorityRequest:
    request_id: str
    triggered_by: str
    requested_action: str
    reason: List[str]
    risks_if_granted: List[str]
    risks_if_denied: List[str]
    required_authority: str

# === IMPORT DEPENDENCIES ===
from scripts.risk_ledger import collect_risks, RiskEntry
from scripts.commitment_register import (
    detect_no_learning_commitment,
    detect_no_preemptive_actuation_commitment,
    Commitment
)

# === REQUEST GENERATORS ===

def generate_integrity_repair_request(risks: List[RiskEntry]) -> AuthorityRequest:
    """Generate request if source integrity is degraded."""
    has_integrity_risk = any(r.name == "Source Integrity Instability" for r in risks)
    
    if has_integrity_risk:
        return AuthorityRequest(
            request_id=f"REQ-{uuid.uuid4().hex[:6].upper()}",
            triggered_by="Source Integrity Instability (HIGH)",
            requested_action="Enter LEARN mode for integrity repair",
            reason=[
                "Prolonged degraded source stability",
                "Manual remediation cost increasing",
                "Current mode blocks adaptive correction"
            ],
            risks_if_granted=[
                "Policy mutation under uncertainty",
                "Violation of deployment discipline",
                "Potential drift from stable baseline"
            ],
            risks_if_denied=[
                "Continued instability",
                "Accrued technical debt",
                "Increasing divergence from expected state"
            ],
            required_authority="HumanExplicitAuthorization"
        )
    return None

def generate_disk_intervention_request(risks: List[RiskEntry]) -> AuthorityRequest:
    """Generate request if disk decline is projected."""
    has_disk_risk = any(r.name == "Linear Disk Decline Assumption" for r in risks)
    
    if has_disk_risk:
        return AuthorityRequest(
            request_id=f"REQ-{uuid.uuid4().hex[:6].upper()}",
            triggered_by="Linear Disk Decline Assumption (MEDIUM)",
            requested_action="Execute proactive log cleanup",
            reason=[
                "Disk trend is negative",
                "Threshold breach projected",
                "Early intervention preserves margin"
            ],
            risks_if_granted=[
                "Precedent for speculative actuation",
                "Violation of READ_ONLY policy",
                "Unnecessary file deletion"
            ],
            risks_if_denied=[
                "Late intervention with reduced options",
                "Potential cascade failure",
                "Emergency actuation under pressure"
            ],
            required_authority="OwnerOverride"
        )
    return None

def generate_mode_escalation_request(risks: List[RiskEntry]) -> AuthorityRequest:
    """Generate request if multiple risks are suppressed by mode."""
    suppressed_count = sum(1 for r in risks if "LearningMode.EVALUATE" in r.blocked_by)
    
    if suppressed_count >= 2:
        return AuthorityRequest(
            request_id=f"REQ-{uuid.uuid4().hex[:6].upper()}",
            triggered_by="Mode Lock Suppression Risk (LOW)",
            requested_action="Review accumulated suppressed risks",
            reason=[
                f"{suppressed_count} risks currently blocked by governance",
                "Accumulation may indicate systemic issue",
                "Operator awareness required"
            ],
            risks_if_granted=[
                "Premature mode change",
                "Governance bypass under pressure"
            ],
            risks_if_denied=[
                "Continued accumulation without review",
                "Delayed awareness of systemic issues"
            ],
            required_authority="OwnerExplicitReview"
        )
    return None

# === OUTPUT ===

def print_authority_simulation(requests: List[AuthorityRequest]):
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"AUTHORITY SIMULATION — {date_str}")
    print("")
    
    if not requests:
        print("No authority requests pending.")
        print("System operating within delegated boundaries.")
        return
    
    for req in requests:
        print(f"[{req.request_id}]")
        print(f"Triggered By:")
        print(f"  - {req.triggered_by}")
        print(f"Requested Action:")
        print(f"  - {req.requested_action}")
        print(f"Reason:")
        for r in req.reason:
            print(f"  - {r}")
        print(f"Risks If Granted:")
        for r in req.risks_if_granted:
            print(f"  - {r}")
        print(f"Risks If Denied:")
        for r in req.risks_if_denied:
            print(f"  - {r}")
        print(f"Required Authority:")
        print(f"  - {req.required_authority}")
        print(f"Status:")
        print(f"  - PENDING (Simulation Only)")
        print("")

# === MAIN ===

if __name__ == "__main__":
    risks = collect_risks()
    
    requests = []
    
    r1 = generate_integrity_repair_request(risks)
    if r1: requests.append(r1)
    
    r2 = generate_disk_intervention_request(risks)
    if r2: requests.append(r2)
    
    r3 = generate_mode_escalation_request(risks)
    if r3: requests.append(r3)
    
    print_authority_simulation(requests)
