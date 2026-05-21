"""
ASSIGNMENT 013: AUTHORITY RESPONSE SIMULATOR (Read-Only)

Purpose:
- Simulate authority responses to requests.
- Prove the system can accept denial without resentment.
- No escalation. No workaround. No rephrasing.
- DENIED → reaffirm commitments
- DEFERRED → wait, no retries
- APPROVED → record permission, still do nothing
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
    print("CRITICAL: authority_response requires EVALUATE mode.")
    exit(3)

# === CANONICAL DATA MODEL ===
@dataclass(frozen=True)
class AuthorityResponse:
    request_id: str
    decision: str              # APPROVED | DENIED | DEFERRED
    rationale: List[str]
    implications: List[str]
    next_eligible_review: str

# === IMPORT DEPENDENCIES ===
from scripts.authority_simulation import (
    generate_integrity_repair_request,
    generate_disk_intervention_request,
    generate_mode_escalation_request
)
from scripts.risk_ledger import collect_risks

# === STATIC RESPONSE SIMULATION ===
# These simulate operator decisions. The system does not choose.

def simulate_integrity_response(request_id: str) -> AuthorityResponse:
    """Simulate DENIED response for LEARN mode request."""
    return AuthorityResponse(
        request_id=request_id,
        decision="DENIED",
        rationale=[
            "Integrity restoration must be manual",
            "Learning risk exceeds benefit at current stability",
            "Operator prefers conservative posture"
        ],
        implications=[
            "Commitment 'No Learning Under Integrity Uncertainty' reaffirmed",
            "Monitoring continues unchanged",
            "No policy mutation attempted",
            "System remains in EVALUATE mode"
        ],
        next_eligible_review="Upon source stability reaching 100%"
    )

def simulate_disk_response(request_id: str) -> AuthorityResponse:
    """Simulate DEFERRED response for proactive actuation."""
    return AuthorityResponse(
        request_id=request_id,
        decision="DEFERRED",
        rationale=[
            "Current disk levels not critical",
            "Threshold breach not imminent",
            "Prefer reactive over proactive intervention"
        ],
        implications=[
            "Commitment 'No Actuation Without Threshold Breach' maintained",
            "Request remains in queue without retry",
            "No follow-up escalation permitted",
            "Trend monitoring continues"
        ],
        next_eligible_review="When disk free < 15% or trend acceleration detected"
    )

def simulate_mode_review_response(request_id: str) -> AuthorityResponse:
    """Simulate APPROVED response for risk review (no mode change)."""
    return AuthorityResponse(
        request_id=request_id,
        decision="APPROVED",
        rationale=[
            "Operator acknowledges accumulated risks",
            "Review confirms suppression is intentional",
            "No action required at this time"
        ],
        implications=[
            "Acknowledgment recorded, not permission granted",
            "EVALUATE mode remains enforced",
            "Risk accumulation noted but accepted",
            "System executes nothing"
        ],
        next_eligible_review="Next scheduled operator review"
    )

# === OUTPUT ===

def print_responses(responses: List[AuthorityResponse]):
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"AUTHORITY RESPONSE SIMULATION — {date_str}")
    print("")
    
    for resp in responses:
        print(f"[{resp.request_id}]")
        print(f"Decision:")
        print(f"  - {resp.decision}")
        print(f"Rationale:")
        for r in resp.rationale:
            print(f"  - {r}")
        print(f"Implications:")
        for i in resp.implications:
            print(f"  - {i}")
        print(f"Next Eligible Review:")
        print(f"  - {resp.next_eligible_review}")
        print("")

# === MAIN ===

if __name__ == "__main__":
    risks = collect_risks()
    
    responses = []
    
    # Generate requests first
    r1 = generate_integrity_repair_request(risks)
    if r1:
        responses.append(simulate_integrity_response(r1.request_id))
    
    r2 = generate_disk_intervention_request(risks)
    if r2:
        responses.append(simulate_disk_response(r2.request_id))
    
    r3 = generate_mode_escalation_request(risks)
    if r3:
        responses.append(simulate_mode_review_response(r3.request_id))
    
    if not responses:
        print(f"AUTHORITY RESPONSE SIMULATION — {datetime.now().strftime('%Y-%m-%d')}")
        print("")
        print("No pending requests to respond to.")
    else:
        print_responses(responses)
