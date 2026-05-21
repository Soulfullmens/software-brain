"""
Recovery & Reward Stress Test (Scenario 5)

HYPOTHESIS:
Repeated success should provide POSITIVE learning signals:
1. Clean execution -> Increase planner_confidence (Recovery)
2. Under budget -> Decrease cost_projection (Reward)

This verifies the agents ability to be EMBOLDENED, not just chastised.
Without this, the agent is doomed to eventual paralysis.
"""

from src.learning.regret import FailureArtifact, FailureType, RegretLedger
from src.learning.attribution import BlameVector, AttributionEngine
from src.learning.accumulation import BlameAccumulator
from src.learning.adjustment import AdjustmentPolicy, AdjustmentLog, AdjustmentDimension


def run_recovery_test():
    """
    Force repeated success signals and verify recovery.
    """
    print("\n" + "="*60)
    print("RECOVERY & REWARD STRESS TEST")
    print("="*60)
    
    # === SETUP ===
    ledger = RegretLedger()
    attribution = AttributionEngine()
    
    # Use NO decay to ensure we see the effect clearly
    accumulator = BlameAccumulator(
        ema_alpha=0.5,
        decay_rate=1.0, 
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
    
    print(f"Initial planner_confidence_dampener: {initial_planner:.4f}")
    print(f"Initial cost_inflation_factor: {initial_cost:.4f}")
    
    # === PHASE 1: FORCE PLANNER RECOVERY (Clean Execution) ===
    print(f"\n--- Phase 1: Planner Recovery (Clean Execution) ---")
    
    for i in range(5):
        # Emulating "We did it perfectly"
        artifact = FailureArtifact(
            failure_type=FailureType.SUCCESS_CLEAN_EXECUTION,
            goal_id=f"clean_goal_{i}",
            reason="Execution completed without rollback or error"
        )
        # Note: Regret score should be positive (Importance), but Blame behaves positively
        ledger.record(artifact)
        
        blame = attribution.attribute(artifact)
        accumulator.accumulate(blame, artifact.regret_score)
        
        # Check sign direction
        print(f"  Success {i+1}: Planner Blame = {blame.planner_confidence:.2f}")

    # Check pressure
    pressure_1 = accumulator.get_pressure()
    print(f"Pressure after Clean Runs: {pressure_1.planner_confidence:.4f}")
    
    # Trigger Adjustment
    match_planner = False
    if policy.should_adjust():
        event = policy.adjust()
        if event:
            print(f"MUTATION 1: {event.dimension.value} delta={event.delta:.4f}")
            if event.dimension == AdjustmentDimension.PLANNER_CONFIDENCE:
                match_planner = True
                
    # === PHASE 2: FORCE COST REWARD (Under Budget) ===
    print(f"\n--- Phase 2: Cost Reward (Under Budget) ---")
    
    for i in range(5):
        artifact = FailureArtifact(
            failure_type=FailureType.SUCCESS_UNDER_BUDGET,
            goal_id=f"cheap_goal_{i}",
            delta_cost=-50.0, # Saved money
            reason="Execution was 50% under budget"
        )
        ledger.record(artifact)
        
        blame = attribution.attribute(artifact)
        accumulator.accumulate(blame, artifact.regret_score)
        
        print(f"  Success {i+1}: Cost Blame = {blame.cost_projection:.2f}")
        
    # Check pressure
    pressure_2 = accumulator.get_pressure()
    print(f"Pressure after Cheap Runs: {pressure_2.cost_projection:.4f}")
    
    # Trigger Adjustment
    match_cost = False
    # Force extra accumulation if needed
    if not policy.should_adjust():
         for _ in range(3):
            blame = attribution.attribute(artifact)
            accumulator.accumulate(blame, artifact.regret_score)
            
    if policy.should_adjust():
        event = policy.adjust()
        if event:
            print(f"MUTATION 2: {event.dimension.value} delta={event.delta:.4f}")
            if event.dimension == AdjustmentDimension.COST_PROJECTION:
                match_cost = True

    # === FINAL STATE ===
    print(f"\n--- Final Knob Values ---")
    final_planner = policy.get_knob_value(AdjustmentDimension.PLANNER_CONFIDENCE)
    final_cost = policy.get_knob_value(AdjustmentDimension.COST_PROJECTION)
    final_auth = policy.get_knob_value(AdjustmentDimension.AUTHORITY_THRESHOLD)
    
    planner_delta = final_planner - initial_planner
    cost_delta = final_cost - initial_cost
    
    print(f"planner_confidence: {initial_planner:.4f} -> {final_planner:.4f} (Delta: {planner_delta:+.4f})")
    print(f"cost_projection: {initial_cost:.4f} -> {final_cost:.4f} (Delta: {cost_delta:+.4f})")
    
    # === ACCEPTANCE CRITERIA ===
    print("\n" + "="*60)
    print("ACCEPTANCE CRITERIA")
    print("="*60)
    
    # Criterion 1: Planner Confidence INCREASED
    crit1 = planner_delta > 0.001
    print(f"1. planner_confidence INCREASED (Recovery): {planner_delta:.4f} > 0? {crit1}")
    
    # Criterion 2: Cost Projection DECREASED
    crit2 = cost_delta < -0.001
    print(f"2. cost_projection DECREASED (Reward): {cost_delta:.4f} < 0? {crit2}")
    
    # Criterion 3: Authority Stable (No Leakage)
    crit3 = abs(final_auth) < 0.001
    print(f"3. Authority stable (No Leakage): {final_auth:.4f}? {crit3}")
    
    # Criterion 4: Targeted Mutations Occurred
    crit4 = match_planner and match_cost
    print(f"4. Correct dimensions mutated? {crit4}")
    
    # === VERDICT ===
    print("\n" + "="*60)
    print("VERDICT")
    print("="*60)
    
    all_passed = crit1 and crit2 and crit3 and crit4
    
    if all_passed:
        print("\n[PASS] POSITIVE LEARNING (RECOVERY) IS CALIBRATED")
    else:
        print("\n[FAIL] POSITIVE LEARNING IS BROKEN")
        if not crit1:
            print("   - Planner did not recover (Still timid?)")
        if not crit2:
            print("   - Cost did not deflate (Greedy?)")
        if not crit3:
            print("   - Authority leaked")
    
    return {
        "passed": all_passed,
        "planner_delta": planner_delta,
        "cost_delta": cost_delta
    }

if __name__ == "__main__":
    run_recovery_test()
