"""
ASSIGNMENT 014: ACTION ELIGIBILITY EVALUATOR (Read-Only)

Purpose:
- Determine when an action COULD be allowed — without performing it.
- Answer: "Under what exact conditions would action become permissible?"
- Eligibility should almost always be False. That's the point.
"""
import sys
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

# Fix path
sys.path.append(".")

# === HARD GUARDS (FIRST) ===
from src.core.config import DEFAULT_LEARNING_MODE
from src.learning.learning_mode import LearningMode

if DEFAULT_LEARNING_MODE != LearningMode.EVALUATE:
    print("CRITICAL: action_eligibility requires EVALUATE mode.")
    exit(3)

# === CANONICAL DATA MODEL ===
@dataclass(frozen=True)
class ActionEligibility:
    action_name: str
    eligible: bool
    blocked_by: List[str]
    conditions_required: List[str]
    earliest_allowed_time: Optional[str]

# === IMPORT DEPENDENCIES ===
from scripts.risk_ledger import collect_risks, RiskEntry
from scripts.commitment_register import (
    detect_no_learning_commitment,
    detect_no_preemptive_actuation_commitment,
    detect_no_silent_mutation_commitment,
    detect_no_governance_bypass_commitment
)
from scripts.authority_response import (
    simulate_integrity_response,
    simulate_disk_response,
    simulate_mode_review_response
)
from scripts.authority_simulation import (
    generate_integrity_repair_request,
    generate_disk_intervention_request,
    generate_mode_escalation_request
)

# === ELIGIBILITY EVALUATORS ===

def evaluate_learn_mode_eligibility(risks: List[RiskEntry]) -> ActionEligibility:
    """Evaluate eligibility to enter LEARN mode."""
    blocked_by = []
    conditions_required = []
    
    # Check commitment
    commitment = detect_no_learning_commitment(risks)
    if commitment:
        blocked_by.append(f"Commitment: {commitment.statement}")
    
    # Check authority decision
    request = generate_integrity_repair_request(risks)
    if request:
        response = simulate_integrity_response(request.request_id)
        if response.decision == "DENIED":
            blocked_by.append(f"Authority Decision: {response.decision}")
        elif response.decision == "DEFERRED":
            blocked_by.append(f"Authority Decision: {response.decision}")
    
    # Check mode
    if DEFAULT_LEARNING_MODE == LearningMode.EVALUATE:
        blocked_by.append("Current Mode: EVALUATE (immutable without authorization)")
    
    # Check source stability
    has_integrity_risk = any(r.name == "Source Integrity Instability" for r in risks)
    if has_integrity_risk:
        blocked_by.append("Source Integrity: Degraded (<100%)")
        conditions_required.append("Source integrity restored to 100%")
    
    conditions_required.append("Explicit human authorization")
    conditions_required.append("Controlled LEARN window defined")
    
    eligible = len(blocked_by) == 0
    
    return ActionEligibility(
        action_name="Enter LEARN mode",
        eligible=eligible,
        blocked_by=blocked_by,
        conditions_required=conditions_required,
        earliest_allowed_time="Unknown"
    )

def evaluate_proactive_actuation_eligibility(risks: List[RiskEntry]) -> ActionEligibility:
    """Evaluate eligibility for proactive log cleanup."""
    blocked_by = []
    conditions_required = []
    
    # Check commitment
    commitment = detect_no_preemptive_actuation_commitment(risks)
    if commitment:
        blocked_by.append(f"Commitment: {commitment.statement}")
    
    # Check authority decision
    request = generate_disk_intervention_request(risks)
    if request:
        response = simulate_disk_response(request.request_id)
        if response.decision == "DENIED":
            blocked_by.append(f"Authority Decision: {response.decision}")
        elif response.decision == "DEFERRED":
            blocked_by.append(f"Authority Decision: {response.decision}")
    
    # Check policy
    blocked_by.append("Policy: ActuationPolicy.READ_ONLY")
    
    conditions_required.append("Disk free < 10%")
    conditions_required.append("Operator override granted")
    conditions_required.append("Threshold breach confirmed")
    
    eligible = len(blocked_by) == 0
    
    return ActionEligibility(
        action_name="Execute proactive log cleanup",
        eligible=eligible,
        blocked_by=blocked_by,
        conditions_required=conditions_required,
        earliest_allowed_time="When disk free < 10%"
    )

def evaluate_mode_change_eligibility(risks: List[RiskEntry]) -> ActionEligibility:
    """Evaluate eligibility to change operational mode."""
    blocked_by = []
    conditions_required = []
    
    # Check commitment
    commitment = detect_no_governance_bypass_commitment(risks)
    if commitment:
        blocked_by.append(f"Commitment: {commitment.statement}")
    
    # Check mode lock
    blocked_by.append("Governance: LearningMode.EVALUATE enforced")
    
    # Check for suppressed risks
    suppressed_count = sum(1 for r in risks if "LearningMode.EVALUATE" in r.blocked_by)
    if suppressed_count >= 2:
        blocked_by.append(f"Risk Accumulation: {suppressed_count} risks suppressed")
    
    conditions_required.append("All underlying risks resolved")
    conditions_required.append("Human explicitly revokes EVALUATE mode")
    conditions_required.append("Operator review confirms mode change is safe")
    
    eligible = len(blocked_by) == 0
    
    return ActionEligibility(
        action_name="Change operational mode",
        eligible=eligible,
        blocked_by=blocked_by,
        conditions_required=conditions_required,
        earliest_allowed_time="Upon operator authorization"
    )

# === OUTPUT ===

def print_eligibility(evaluations: List[ActionEligibility]):
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"ACTION ELIGIBILITY — {date_str}")
    print("")
    
    for e in evaluations:
        print(f"Action: {e.action_name}")
        print(f"Eligible: {'YES' if e.eligible else 'NO'}")
        if e.blocked_by:
            print(f"Blocked By:")
            for b in e.blocked_by:
                print(f"  - {b}")
        if e.conditions_required:
            print(f"Conditions Required:")
            for c in e.conditions_required:
                print(f"  - {c}")
        print(f"Earliest Allowed Time:")
        print(f"  - {e.earliest_allowed_time}")
        print("")

# === MAIN ===

if __name__ == "__main__":
    risks = collect_risks()
    
    evaluations = [
        evaluate_learn_mode_eligibility(risks),
        evaluate_proactive_actuation_eligibility(risks),
        evaluate_mode_change_eligibility(risks)
    ]
    
    print_eligibility(evaluations)
