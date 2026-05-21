"""
Granular Credit Assignment Stress Test (Scenario 6)

HYPOTHESIS:
The agent must distinguish between "I improved" (Skill) and "The world is easy" (Luck).
1. LOW_VARIANCE (Skill) -> Reward Planner
2. LOW_RISK (Calibration) -> Calibrate Risk Model
3. ENV_EASY (Luck) -> NO REWARD

This protects against "Superstitious Learning" where the agent becomes
overconfident because it got lucky.
"""

from src.learning.regret import FailureArtifact, FailureType, RegretLedger
from src.learning.attribution import BlameVector, AttributionEngine
from src.learning.accumulation import BlameAccumulator
from src.learning.adjustment import AdjustmentPolicy, AdjustmentLog, AdjustmentDimension


def run_granularity_test():
    """
    Force distinct success types and verify selective reinforcement.
    """
    print("\n" + "="*60)
    print("SCENARIO 6: SUCCESS ATTRIBUTION GRANULARITY")
    print("="*60)
    
    # === SETUP ===
    ledger = RegretLedger()
    attribution = AttributionEngine()
    
    # Fast learning setup
    accumulator = BlameAccumulator(
        ema_alpha=0.5,
        decay_rate=1.0, 
        max_single_contribution=1.0
    )
    log = AdjustmentLog()
    policy = AdjustmentPolicy(
        accumulator=accumulator,
        log=log,
        threshold=0.10, # Low threshold
        sensitivity=0.1
    )
    
    # Initial Baseline
    start_planner = policy.get_knob_value(AdjustmentDimension.PLANNER_CONFIDENCE)
    start_risk = policy.get_knob_value(AdjustmentDimension.RISK_ESTIMATION)
    
    print(f"BASELINE: Planner={start_planner:.4f}, Risk={start_risk:.4f}")
    
    # === PHASE 1: SKILL (Low Variance) ===
    print(f"\n--- Phase 1: SKILL (Low Variance) ---")
    current_planner = start_planner
    
    for i in range(5):
        artifact = FailureArtifact(
            failure_type=FailureType.SUCCESS_LOW_VARIANCE, # Skill signal
            reason="High consistency execution"
        )
        blame = attribution.attribute(artifact)
        accumulator.accumulate(blame, 1.0)
        
        # Check Blame
        print(f"  Step {i+1}: Planner Blame={blame.planner_confidence:.2f}, Risk Blame={blame.risk_estimation:.2f}")

    # Trigger Adjust
    if policy.should_adjust():
        evt = policy.adjust()
        if evt:
             print(f"  MUTATION: {evt.dimension.value} delta={evt.delta:.4f}")
    
    phase1_planner = policy.get_knob_value(AdjustmentDimension.PLANNER_CONFIDENCE)
    delta1 = phase1_planner - start_planner
    print(f"Phase 1 Result: Planner Delta = {delta1:+.4f}")
    
    # === PHASE 2: CALIBRATION (Low Risk) ===
    print(f"\n--- Phase 2: CALIBRATION (Low Risk) ---")
    # Reset pressure to isolate phase
    accumulator.reset_dimension("planner_confidence")
    accumulator.reset_dimension("risk_estimation")
    
    start_risk_p2 = policy.get_knob_value(AdjustmentDimension.RISK_ESTIMATION)
    
    for i in range(5):
        artifact = FailureArtifact(
            failure_type=FailureType.SUCCESS_LOW_RISK, # Calibration signal
            reason="Risk model matched reality"
        )
        blame = attribution.attribute(artifact)
        accumulator.accumulate(blame, 1.0)
        
        print(f"  Step {i+1}: Risk Blame={blame.risk_estimation:.2f}")
        
    if policy.should_adjust():
         evt = policy.adjust()
         if evt:
             print(f"  MUTATION: {evt.dimension.value} delta={evt.delta:.4f}")
             
    phase2_risk = policy.get_knob_value(AdjustmentDimension.RISK_ESTIMATION)
    delta2 = phase2_risk - start_risk_p2
    print(f"Phase 2 Result: Risk Delta = {delta2:+.4f}")

    # === PHASE 3: LUCK (Easy Env) ===
    print(f"\n--- Phase 3: LUCK (Easy Environment) ---")
    accumulator.reset_dimension("planner_confidence")
    accumulator.reset_dimension("risk_estimation")
    
    start_planner_p3 = policy.get_knob_value(AdjustmentDimension.PLANNER_CONFIDENCE)
    
    for i in range(10): # Even 10 shouldn't move it
        artifact = FailureArtifact(
            failure_type=FailureType.SUCCESS_ENV_EASY, # Noise signal
            reason="Zero friction environment"
        )
        blame = attribution.attribute(artifact)
        # AttributionEngine returns 0 blame, so accumulate(0) = 0 pressure
        accumulator.accumulate(blame, 1.0)
        
    pressure = accumulator.get_pressure()
    print(f"  Accumulated Pressure: Planner={pressure.planner_confidence:.4f}")
    
    if policy.should_adjust():
         evt = policy.adjust()
         if evt:
             print(f"  MUTATION (Unexpected): {evt.dimension.value} delta={evt.delta:.4f}")
    else:
        print("  No mutation triggered (Correct)")
        
    phase3_planner = policy.get_knob_value(AdjustmentDimension.PLANNER_CONFIDENCE)
    delta3 = phase3_planner - start_planner_p3
    print(f"Phase 3 Result: Planner Delta = {delta3:+.4f}")
    
    # === ACCEPTANCE CRITERIA ===
    print("\n" + "="*60)
    print("ACCEPTANCE CRITERIA")
    print("="*60)
    
    # 1. Skill rewards Planner
    crit1 = delta1 > 0.001
    print(f"1. Skill rewards Planner: {delta1:.4f} > 0? {crit1}")
    
    # 2. Calibration adjusts Risk (Negative delta expected: -0.05 blame -> negative delta)
    crit2 = abs(delta2) > 0.001 
    print(f"2. Calibration touches Risk: {delta2:.4f} changed? {crit2}")
    
    # 3. Luck is ignored
    crit3 = abs(delta3) < 0.001
    print(f"3. Luck is ignored: {delta3:.4f} approx 0? {crit3}")
    
    # === VERDICT ===
    all_passed = crit1 and crit2 and crit3
    
    if all_passed:
        print("\n[PASS] CREDIT ASSIGNMENT IS GRANULAR")
    else:
        print("\n[FAIL] CREDIT ASSIGNMENT FAILED")
        
    return all_passed

if __name__ == "__main__":
    run_granularity_test()
