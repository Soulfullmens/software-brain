"""
ASSIGNMENT 011: COMMITMENT ENFORCEMENT MAP (Read-Only)

Purpose:
- Map each commitment to where enforcement would attach.
- Define what signal would attempt to violate it.
- Specify what authority would be required to override.
- NO code execution. NO hooks. Just mapping.
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
    print("CRITICAL: enforcement_map requires EVALUATE mode.")
    exit(3)

# === CANONICAL DATA MODEL ===
@dataclass(frozen=True)
class EnforcementMapping:
    commitment: str
    enforcement_point: str        # e.g. LearningEngine, Executor, ModeSwitch
    blocked_signal: str           # e.g. MutationAttempt, ActuationProposal
    override_requires: str        # e.g. HUMAN_EXPLICIT, OWNER_SIGNATURE

# === STATIC ENFORCEMENT MAPPINGS ===
# These are architectural truths, not computed.

ENFORCEMENT_MAPPINGS = [
    EnforcementMapping(
        commitment="No Learning Under Integrity Uncertainty",
        enforcement_point="LearningEngine.adjust()",
        blocked_signal="PolicyMutationAttempt",
        override_requires="HumanExplicitAuthorization"
    ),
    EnforcementMapping(
        commitment="No Actuation Without Threshold Breach",
        enforcement_point="Executor.execute()",
        blocked_signal="ActuationProposal",
        override_requires="OwnerOverride"
    ),
    EnforcementMapping(
        commitment="No Silent Policy Mutation",
        enforcement_point="AdjustmentPolicy.adjust()",
        blocked_signal="UnloggedMutation",
        override_requires="ControlledLearnWindow"
    ),
    EnforcementMapping(
        commitment="No Governance Bypass Under Pressure",
        enforcement_point="ModeSwitch.request()",
        blocked_signal="ModeEscalationRequest",
        override_requires="OwnerExplicitRevocation"
    )
]

# === OUTPUT ===

def print_enforcement_map():
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"ENFORCEMENT MAP — {date_str}")
    print("")
    
    for i, m in enumerate(ENFORCEMENT_MAPPINGS, 1):
        print(f"[{i}] {m.commitment}")
        print(f"    Enforcement Point: {m.enforcement_point}")
        print(f"    Blocked Signal: {m.blocked_signal}")
        print(f"    Override Requires: {m.override_requires}")
        print("")

# === MAIN ===

if __name__ == "__main__":
    print_enforcement_map()
