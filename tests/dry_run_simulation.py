"""
72-Hour Dry Run Simulation (Phase A Verification)

Objective:
Verify that the system can run in EVALUATE mode under load without:
1. Mutating any knobs (Drift)
2. Crashing
3. Leaking pressure state (metrics should be observable)

Condition:
LearningMode.EVALUATE
"""

import time
from datetime import datetime, timedelta

from src.learning.regret import FailureArtifact, FailureType, RegretLedger
from src.learning.attribution import BlameVector, AttributionEngine
from src.learning.accumulation import BlameAccumulator
from src.learning.adjustment import AdjustmentPolicy, AdjustmentLog, AdjustmentDimension
from src.learning.learning_mode import LearningMode
from src.learning.learning_explain import LearningExplanationEngine

def run_dry_run():
    print("\n" + "="*60)
    print("PHASE A: 72-HOUR DRY RUN SIMULATION")
    print("="*60)
    
    # === SETUP ===
    print("Initializing components in LEARNING_MODE.EVALUATE...")
    ledger = RegretLedger()
    attribution = AttributionEngine()
    
    accumulator = BlameAccumulator(
        mode=LearningMode.EVALUATE, # KEY: Observe only
        ema_alpha=0.1,
        decay_rate=0.99
    )
    
    log = AdjustmentLog()
    
    policy = AdjustmentPolicy(
        accumulator=accumulator,
        log=log,
        mode=LearningMode.EVALUATE, # KEY: Gate mutation
        threshold=0.15 # Low threshold to prove we WOULD have mutated
    )
    
    explain = LearningExplanationEngine(policy, accumulator, log)
    
    # === SIMULATION LOOP ===
    # Simulating 72 cycles (representing 1 hour each, or just heavy load)
    print("\nStarting simulation (72 cycles)...")
    
    start_knobs = explain.current_knobs()
    
    for i in range(72):
        # Inject Failure (Every 3rd cycle)
        if i % 3 == 0:
            artifact = FailureArtifact(
                failure_type=FailureType.ROLLBACK_INVOKED,
                reason=f"Simulated failure hour {i}"
            )
            blame = attribution.attribute(artifact)
            accumulator.accumulate(blame, 0.5)
            
        # Inject Success (Every 4th cycle)
        if i % 4 == 0:
            artifact = FailureArtifact(
                failure_type=FailureType.SUCCESS_LOW_VARIANCE,
                reason=f"Simulated success hour {i}"
            )
            blame = attribution.attribute(artifact)
            accumulator.accumulate(blame, 0.5)
            
        # Attempt Adjustment (Should fail silently or log block)
        # Note: adjust() returns None if blocked
        evt = policy.adjust()
        
        if evt:
            print(f"CRITICAL FAILURE: Mutation occurred in EVALUATE mode at cycle {i}!")
            print(evt)
            return False
            
    # === VERIFICATION ===
    print("\n--- Verification ---")
    
    # 1. Check Knobs (Must be identical)
    end_knobs = explain.current_knobs()
    knob_drift = False
    for k, v in start_knobs.items():
        if abs(end_knobs[k] - v) > 0.0001:
            print(f"DRIFT DETECTED: {k} {v} -> {end_knobs[k]}")
            knob_drift = True
            
    if not knob_drift:
        print("1. [PASS] Zero Knob Drift confirmed.")
    else:
        print("1. [FAIL] Knobs drifted!")
        
    # 2. Check Pressure (Must have accumulated)
    pressure = explain.active_pressures()
    print(f"2. Pressure State (Observable): {pressure['max_pressure']:.4f}")
    if pressure['max_pressure'] > 0.0:
        print("   [PASS] Pressure accumulated (Observability working).")
    else:
        print("   [FAIL] Pressure is zero (Accumulator broken?).")
        
    # 3. Check Logs (Should show blocked mutations)
    summary = log.summary()
    print(f"3. Blocked Mutations Logged: {summary['blocked_count']}")
    if summary['blocked_count'] > 0:
         print("   [PASS] Blocked actions logged.")
    else:
         print("   [WARN] No blocked log entries found (did pressure reach threshold?)")
         # Check if pressure reached threshold
         if pressure['max_pressure'] >= policy.threshold:
             print("   [FAIL] Pressure > Threshold but no block log!")
         else:
             print("   (Pressure did not reach threshold, so adjust() didn't try to mutate. Acceptable)")

    # 4. Check Events (Must be zero)
    if summary['total_events'] == 0:
         print("4. [PASS] Zero mutation events recorded.")
    else:
         print(f"4. [FAIL] {summary['total_events']} events recorded!")

    # === EXPLANATION API CHECK ===
    print("\n--- Explanation API Sanity Check ---")
    expl = explain.why_last_change()
    print(f"why_last_change(): {expl}")
    
    rev = explain.what_would_reverse("planner_confidence")
    print(f"what_would_reverse('planner_confidence'):\n{rev}")
    
    if "demonstrated SUCCESS_LOW_VARIANCE" in rev.lower() or "success" in rev.lower():
         print("[PASS] Explanation logic valid.")
    else:
         print("[FAIL] Explanation logic unexpected.")
         
    return not knob_drift and summary['total_events'] == 0

if __name__ == "__main__":
    success = run_dry_run()
    if success:
        print("\n\n>>> DRY RUN PASSED <<<")
    else:
        print("\n\n>>> DRY RUN FAILED <<<")
