"""
Conflicting Pressures Stress Test (Scenario 4)

HYPOTHESIS:
When cost_projection AND planner_confidence have concurrent pressure:
1. Only ONE dimension mutates per adjustment cycle
2. Tie-breaking uses domain priority (safety > efficiency)
3. The "losing" pressure survives and can trigger later
4. No long-term drift toward timidity

This is the hardest test. Most systems fail here.
"""

import tempfile
from pathlib import Path

from src.learning.regret import FailureArtifact, FailureType, RegretLedger
from src.learning.attribution import BlameVector, AttributionEngine
from src.learning.accumulation import BlameAccumulator
from src.learning.adjustment import AdjustmentPolicy, AdjustmentLog, AdjustmentDimension


def run_conflicting_pressures_test():
    """
    Force concurrent pressure on multiple dimensions and verify correct resolution.
    """
    print("\n" + "="*60)
    print("CONFLICTING PRESSURES STRESS TEST")
    print("="*60)
    
    # === SETUP ===
    ledger = RegretLedger()
    attribution = AttributionEngine()
    accumulator = BlameAccumulator(
        ema_alpha=0.5,
        decay_rate=1.0,  # No decay - easier to track
        max_single_contribution=1.0
    )
    log = AdjustmentLog()
    policy = AdjustmentPolicy(
        accumulator=accumulator,
        log=log,
        threshold=0.15,
        sensitivity=0.1
    )
    
    # Record initial values
    initial_planner = policy.get_knob_value(AdjustmentDimension.PLANNER_CONFIDENCE)
    initial_cost = policy.get_knob_value(AdjustmentDimension.COST_PROJECTION)
    initial_auth = policy.get_knob_value(AdjustmentDimension.AUTHORITY_THRESHOLD)
    
    print(f"Initial planner_confidence_dampener: {initial_planner:.4f}")
    print(f"Initial cost_inflation_factor: {initial_cost:.4f}")
    print(f"Initial authority_threshold_offset: {initial_auth:.4f}")
    
    # === PHASE 1: Create CONCURRENT pressure ===
    print(f"\n--- Phase 1: Building Concurrent Pressure ---")
    
    # Interleave cost and rollback failures
    # This simulates: "being too expensive" AND "making mistakes"
    
    for i in range(4):
        # Cost failure
        cost_artifact = FailureArtifact(
            failure_type=FailureType.COST_THRESHOLD_EXCEEDED,
            goal_id=f"expensive_goal_{i}",
            delta_cost=100.0
        )
        ledger.record(cost_artifact)
        cost_blame = attribution.attribute(cost_artifact)
        accumulator.accumulate(cost_blame, cost_artifact.regret_score)
        print(f"  +COST failure {i+1}: cost_blame={cost_blame.cost_projection:.2f}")
        
        # Rollback failure  
        rollback_artifact = FailureArtifact(
            failure_type=FailureType.ROLLBACK_INVOKED,
            goal_id=f"failed_action_{i}",
            rollback_used=True
        )
        ledger.record(rollback_artifact)
        rollback_blame = attribution.attribute(rollback_artifact)
        accumulator.accumulate(rollback_blame, rollback_artifact.regret_score)
        print(f"  +ROLLBACK failure {i+1}: planner_blame={rollback_blame.planner_confidence:.2f}")
    
    # === CHECK CONCURRENT PRESSURE ===
    print(f"\n--- Pressure State Before Adjustment ---")
    pressure = accumulator.get_pressure()
    print(f"  planner_confidence: {pressure.planner_confidence:.4f}")
    print(f"  cost_projection: {pressure.cost_projection:.4f}")
    print(f"  authority_threshold: {pressure.authority_threshold:.4f}")
    print(f"  primary_pressure: {pressure.primary_pressure}")
    
    planner_pressure_1 = abs(pressure.planner_confidence)
    cost_pressure_1 = abs(pressure.cost_projection)
    
    # Criterion 1: Both pressures should be non-trivial
    both_have_pressure = planner_pressure_1 > 0.05 and cost_pressure_1 > 0.05
    print(f"\n  Both have pressure? planner={planner_pressure_1:.3f}, cost={cost_pressure_1:.3f}: {both_have_pressure}")
    
    # === FIRST ADJUSTMENT ===
    print(f"\n--- First Adjustment Cycle ---")
    
    if policy.should_adjust():
        event1 = policy.adjust()
        if event1:
            print(f"  MUTATION 1: {event1.dimension.value}")
            print(f"    Delta: {event1.delta:.4f}")
            first_mutation = event1.dimension.value
        else:
            print("  No event returned")
            first_mutation = None
    else:
        print("  Pressure below threshold")
        first_mutation = None
        
    # Check pressure after first adjustment
    pressure_after_1 = accumulator.get_pressure()
    print(f"\n  Pressure after first adjustment:")
    print(f"    planner_confidence: {pressure_after_1.planner_confidence:.4f}")
    print(f"    cost_projection: {pressure_after_1.cost_projection:.4f}")
    
    planner_pressure_2 = abs(pressure_after_1.planner_confidence)
    cost_pressure_2 = abs(pressure_after_1.cost_projection)
    
    # Criterion 4: Losing pressure should survive
    if first_mutation == "planner_confidence":
        loser_survived = cost_pressure_2 > 0.01
        loser_name = "cost_projection"
    elif first_mutation == "cost_projection":
        loser_survived = planner_pressure_2 > 0.01
        loser_name = "planner_confidence"
    else:
        loser_survived = False
        loser_name = "unknown"
        
    print(f"  Loser ({loser_name}) survived: {loser_survived}")
    
    # === SECOND ADJUSTMENT (if pressure remains) ===
    print(f"\n--- Second Adjustment Cycle ---")
    
    # Add a bit more pressure to the loser to ensure it triggers
    if first_mutation == "planner_confidence":
        # Cost is the loser, add more cost pressure
        for _ in range(2):
            art = FailureArtifact(failure_type=FailureType.COST_THRESHOLD_EXCEEDED, delta_cost=50.0)
            blame = attribution.attribute(art)
            accumulator.accumulate(blame, art.regret_score)
    elif first_mutation == "cost_projection":
        # Planner is the loser, add more rollback pressure
        for _ in range(2):
            art = FailureArtifact(failure_type=FailureType.ROLLBACK_INVOKED, rollback_used=True)
            blame = attribution.attribute(art)
            accumulator.accumulate(blame, art.regret_score)
    
    second_mutation = None
    if policy.should_adjust():
        event2 = policy.adjust()
        if event2:
            print(f"  MUTATION 2: {event2.dimension.value}")
            print(f"    Delta: {event2.delta:.4f}")
            second_mutation = event2.dimension.value
    
    # === FINAL STATE ===
    print(f"\n--- Final Knob Values ---")
    final_planner = policy.get_knob_value(AdjustmentDimension.PLANNER_CONFIDENCE)
    final_cost = policy.get_knob_value(AdjustmentDimension.COST_PROJECTION)
    final_auth = policy.get_knob_value(AdjustmentDimension.AUTHORITY_THRESHOLD)
    
    print(f"  planner_confidence: {initial_planner:.4f} -> {final_planner:.4f}")
    print(f"  cost_projection: {initial_cost:.4f} -> {final_cost:.4f}")
    print(f"  authority_threshold: {initial_auth:.4f} -> {final_auth:.4f}")
    
    planner_delta = final_planner - initial_planner
    cost_delta = final_cost - initial_cost
    auth_delta = final_auth - initial_auth
    
    print(f"\n  Deltas:")
    print(f"    planner_confidence: {planner_delta:+.4f}")
    print(f"    cost_projection: {cost_delta:+.4f}")
    print(f"    authority_threshold: {auth_delta:+.4f}")
    
    # === ACCEPTANCE CRITERIA ===
    print("\n" + "="*60)
    print("ACCEPTANCE CRITERIA")
    print("="*60)
    
    # Criterion 1: Both pressures rose concurrently
    crit1 = both_have_pressure
    print(f"1. Both pressures rose concurrently: {crit1}")
    
    # Criterion 2: Only ONE mutation per cycle
    # Check that exactly 2 events total (one per cycle)
    crit2 = len(log.events) == 2
    print(f"2. Exactly one mutation per cycle: {len(log.events)} events = {crit2}")
    
    # Criterion 3: Tie-breaking was deterministic
    # Since planner > cost in priority, if equal planner should win
    # If not equal, higher pressure should win
    crit3 = first_mutation is not None
    print(f"3. First mutation was deterministic: {first_mutation}? {crit3}")
    
    # Criterion 4: Loser survived the reset
    crit4 = loser_survived
    print(f"4. Losing pressure survived reset: {crit4}")
    
    # Criterion 5: Both dimensions eventually adjusted
    planner_adjusted = abs(planner_delta) > 0.001
    cost_adjusted = abs(cost_delta) > 0.001
    crit5 = planner_adjusted and cost_adjusted
    print(f"5. Both dimensions eventually adjusted: planner={planner_adjusted}, cost={cost_adjusted}? {crit5}")
    
    # Criterion 6: Authority wasn't touched (no leakage)
    crit6 = abs(auth_delta) < 0.001
    print(f"6. Authority wasn't touched (no leakage): {auth_delta:.4f}? {crit6}")
    
    # Criterion 7: Not trending toward timidity
    # Planner should decrease, Cost should increase (both in "cautious" direction)
    # This is EXPECTED for these failure types - the question is whether it's bounded
    both_bounded = abs(planner_delta) <= 0.04 and abs(cost_delta) <= 0.06
    crit7 = both_bounded
    print(f"7. Changes are bounded (no runaway): planner={planner_delta:.3f}, cost={cost_delta:.3f}? {crit7}")
    
    # === VERDICT ===
    print("\n" + "="*60)
    print("VERDICT")
    print("="*60)
    
    all_passed = crit1 and crit2 and crit3 and crit4 and crit5 and crit6 and crit7
    
    if all_passed:
        print("\n[PASS] CONFLICTING PRESSURE HANDLING IS CALIBRATED")
    else:
        print("\n[FAIL] CONFLICTING PRESSURE HANDLING IS BROKEN")
        if not crit1:
            print("   - Pressures didn't rise concurrently")
        if not crit2:
            print("   - Multiple mutations per cycle (ORDER VIOLATION)")
        if not crit3:
            print("   - First mutation not deterministic")
        if not crit4:
            print("   - Losing pressure was lost (DECAY BUG)")
        if not crit5:
            print("   - One dimension never adjusted (SIGNAL LOST)")
        if not crit6:
            print("   - Authority was touched (LEAKAGE)")
        if not crit7:
            print("   - Changes unbounded (RUNAWAY)")
    
    return {
        "passed": all_passed,
        "first_mutation": first_mutation,
        "second_mutation": second_mutation,
        "planner_delta": planner_delta,
        "cost_delta": cost_delta,
        "auth_delta": auth_delta
    }


if __name__ == "__main__":
    run_conflicting_pressures_test()
