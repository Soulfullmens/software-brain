"""
LEARN WINDOW 001: FILESYSTEM PLANNING ACCURACY
Execution Script

Objective:
- Run for 6 virtual hours in LEARN mode.
- Mask disallowed signals (Authority/Environment).
- Allow mutations for Cost/Planner Confidence.
- Hard budget: 2 mutations.

"""
import random
import time
from datetime import datetime, timedelta
from pathlib import Path

from src.learning.learning_mode import LearningMode
from src.learning.regret import RegretLedger, FailureArtifact, FailureType
from src.learning.attribution import AttributionEngine
from src.learning.accumulation import BlameAccumulator
from src.learning.adjustment import AdjustmentPolicy, AdjustmentLog, AdjustmentDimension
from src.learning.learning_explain import LearningExplanationEngine
from src.embodiment.filesystem import FilesystemBody
from src.agency.action import Action

# === CONFIGURATION ===
WINDOW_DURATION_HOURS = 6
MUTATION_BUDGET = 2

# Whitelist (Masking)
ALLOWED_FAILURES = {
    FailureType.ROLLBACK_INVOKED,
    FailureType.COST_THRESHOLD_EXCEEDED,
    FailureType.SUCCESS_LOW_VARIANCE,
    FailureType.SUCCESS_UNDER_BUDGET
}

def run_window():
    print(f"\n>>> STARTING LEARN WINDOW 001 <<<")
    print(f"Mode: LEARN")
    print(f"Budget: {MUTATION_BUDGET}")
    print(f"Allowed Signals: {[f.name for f in ALLOWED_FAILURES]}")
    
    # === SETUP ===
    ledger = RegretLedger()
    attribution = AttributionEngine()
    accumulator = BlameAccumulator(mode=LearningMode.LEARN)
    log = AdjustmentLog()
    
    # Initialize Policy with Budget
    policy = AdjustmentPolicy(
        accumulator=accumulator,
        log=log,
        mode=LearningMode.LEARN,
        mutation_budget=MUTATION_BUDGET,
        cooldown_hours=6
    )
    
    explain = LearningExplanationEngine(policy, accumulator, log)
    fs = FilesystemBody(sandbox_root=Path("./tmp_learn_env").resolve())
    
    # === EXECUTION LOOP (6 Hours) ===
    start_knobs = explain.current_knobs()
    
    for hour in range(WINDOW_DURATION_HOURS):
        print(f"\n--- Hour {hour + 1} ---")
        
        # 1. Simulate Workload (Focus: Filesystem friction)
        # We simulate users doing file ops that might fail logic
        
        # Event A: Expensive Operation (Cost Pressure)
        # We want to trigger COST_THRESHOLD_EXCEEDED to see if Cost Projection adapts
        if hour < 2:
            print("  [Sim] Injecting Cost Pressure...")
            artifact = FailureArtifact(
                failure_type=FailureType.COST_THRESHOLD_EXCEEDED,
                reason="CPU spike during grep",
                delta_cost=150.0 # High cost
            )
            process_artifact(artifact, attribution, accumulator)
            
        # Event B: Rollback (Planner Confidence Pressure)
        if hour == 2:
            print("  [Sim] Injecting Rollback...")
            artifact = FailureArtifact(
                failure_type=FailureType.ROLLBACK_INVOKED,
                reason="Accidental overwrite reversed",
                irreversible=True 
            )
            process_artifact(artifact, attribution, accumulator)
            
        # Event C: Authority Block (SHOULD BE IGNORED)
        if hour == 3:
            print("  [Sim] Injecting Authority Block (Should be ignored)...")
            artifact = FailureArtifact(
                failure_type=FailureType.AUTHORITY_BLOCKED,
                reason="Sudo denied"
            )
            process_artifact(artifact, attribution, accumulator)
            
        # 2. Attempt Adjustment
        evt = policy.adjust()
        if evt:
            print(f"  !!! MUTATION TRIGGERED !!!")
            print(f"  {evt.parameter_name}: {evt.old_value:.4f} -> {evt.new_value:.4f} (Delta: {evt.delta:.4f})")
            print(f"  Reason: Pressure {evt.pressure_at_mutation:.4f}")
        else:
            # Check why blocked
            if policy.mutations_this_session >= MUTATION_BUDGET:
                print("  [Status] Mutation blocked by BUDGET.")
            elif policy._cooldown_active():
                 print("  [Status] Mutation blocked by COOLDOWN.")
            else:
                 print(f"  [Status] Pressure building... Max: {accumulator.get_pressure().max_pressure:.4f}")

    # === END OF WINDOW ===
    print("\n>>> WINDOW CLOSED (Auto-Downgrade to EVALUATE) <<<")
    
    # Post-Mortem Data
    end_knobs = explain.current_knobs()
    mutations = log.events
    
    print("\n=== POST-MORTEM DATA ===")
    print(f"Total Mutations: {len(mutations)}")
    
    for i, evt in enumerate(mutations):
        print(f"{i+1}. {evt.dimension.value}: {evt.old_value:.4f} -> {evt.new_value:.4f}")
        
    print("\nKnob Deltas:")
    for k, v in end_knobs.items():
        delta = v - start_knobs[k]
        if abs(delta) > 0.0001:
            print(f"{k}: {delta:+.4f}")
            
    # Verification of Masking
    # Authority pressure should be 0.0 if blocked correctly
    auth_pressure = accumulator.get_pressure().authority_threshold
    print(f"\nAuthority Pressure (Expect 0.0): {auth_pressure:.4f}")
    
    if auth_pressure > 0.001:
        print("FAIL: Authority signal leaked!")
        return False
        
    return True

def process_artifact(artifact, attribution, accumulator):
    # MASKING LOGIC
    if artifact.failure_type not in ALLOWED_FAILURES:
        print(f"  [Masked] Ignoring signal {artifact.failure_type.name}")
        return
        
    # Process
    blame = attribution.attribute(artifact)
    accumulator.accumulate(blame, artifact.regret_score)
    print(f"  [Processed] {artifact.failure_type.name} -> Regret {artifact.regret_score:.2f}")

if __name__ == "__main__":
    run_window()
