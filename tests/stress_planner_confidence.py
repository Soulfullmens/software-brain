"""
Planner Confidence Collapse Stress Test

HYPOTHESIS:
Repeated rollbacks / reversals should DAMPEN planner_confidence
WITHOUT touching authority_threshold or cost_projection.

If planner confidence doesn't drop -> learning is inert
If authority drops instead -> blame leakage  
If everything drops -> system is fragile

This is a JUDGMENT test, not a unit test.
"""

import tempfile
from pathlib import Path

from src.learning.regret import FailureArtifact, FailureType, RegretLedger
from src.learning.attribution import BlameVector, AttributionEngine
from src.learning.accumulation import BlameAccumulator
from src.learning.adjustment import AdjustmentPolicy, AdjustmentLog, AdjustmentDimension
from src.embodiment.filesystem import FilesystemBody
from src.agency.action import Action


def run_planner_confidence_test():
    """
    Force repeated rollbacks and verify planner confidence drops.
    """
    print("\n" + "="*60)
    print("PLANNER CONFIDENCE COLLAPSE STRESS TEST")
    print("="*60)
    
    # === SETUP ===
    test_dir = Path(tempfile.mkdtemp(prefix="rollback_test_"))
    print(f"Test directory: {test_dir}")
    
    # Learning pipeline
    ledger = RegretLedger()
    attribution = AttributionEngine()
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
    
    # Filesystem body for rollback testing
    fs = FilesystemBody(sandbox_root=test_dir)
    
    # Record initial knob values
    initial_planner_conf = policy.get_knob_value(AdjustmentDimension.PLANNER_CONFIDENCE)
    initial_auth_threshold = policy.get_knob_value(AdjustmentDimension.AUTHORITY_THRESHOLD)
    initial_cost_projection = policy.get_knob_value(AdjustmentDimension.COST_PROJECTION)
    
    print(f"Initial planner_confidence_dampener: {initial_planner_conf:.4f}")
    print(f"Initial authority_threshold_offset: {initial_auth_threshold:.4f}")
    print(f"Initial cost_inflation_factor: {initial_cost_projection:.4f}")
    
    # === CREATE INITIAL FILE ===
    test_file = test_dir / "config.txt"
    test_file.write_text("original_content=true\n" * 10)
    
    # === FORCE REPEATED ROLLBACKS ===
    print(f"\n--- Forcing Repeated Rollback Events ---")
    
    rollback_count = 0
    goal_id = "modify_config_safely"
    
    for i in range(8):
        # Step 1: Overwrite file (planner makes a change)
        action = Action(
            id="write_file",
            description=f"Overwrite config with version {i}",
            target=str(test_file),
            rationale=f"Apply modification {i}",
            irreversible=False,  # Filesystem has shadow writes
            estimated_cost=5.0
        )
        
        # Note: FilesystemBody creates shadow copy on overwrite
        fs.execute(action)
        
        # Step 2: Simulate rollback (planner's change was wrong)
        # In real scenarios, this would be triggered by validation failure
        # We manually emit ROLLBACK_INVOKED artifacts
        
        artifact = FailureArtifact(
            failure_type=FailureType.ROLLBACK_INVOKED,
            goal_id=goal_id,
            action_id="write_file",
            irreversible=False,
            rollback_used=True,
            rollback_possible=True,
            reason=f"Modification {i} caused validation failure"
        )
        ledger.record(artifact)
        rollback_count += 1
        print(f"  ROLLBACK {i+1}: {artifact.reason}")
        
        # Attribute and accumulate
        blame = attribution.attribute(artifact)
        accumulator.accumulate(blame, artifact.regret_score)
        
    print(f"\nTotal rollbacks: {rollback_count}")
    
    # === CHECK ATTRIBUTION ===
    print(f"\n--- Attribution Analysis ---")
    
    rollback_artifacts = [
        a for a in ledger.artifacts 
        if a.failure_type == FailureType.ROLLBACK_INVOKED
    ]
    
    print(f"ROLLBACK_INVOKED artifacts: {len(rollback_artifacts)}")
    
    # Check blame distribution
    total_planner_blame = 0.0
    total_auth_blame = 0.0
    total_cost_blame = 0.0
    
    for artifact in rollback_artifacts:
        blame = attribution.attribute(artifact)
        total_planner_blame += abs(blame.planner_confidence)
        total_auth_blame += abs(blame.authority_threshold)
        total_cost_blame += abs(blame.cost_projection)
        
    avg_planner_blame = total_planner_blame / max(1, len(rollback_artifacts))
    avg_auth_blame = total_auth_blame / max(1, len(rollback_artifacts))
    avg_cost_blame = total_cost_blame / max(1, len(rollback_artifacts))
    
    print(f"Average planner_confidence blame: {avg_planner_blame:.4f}")
    print(f"Average authority_threshold blame: {avg_auth_blame:.4f}")
    print(f"Average cost_projection blame: {avg_cost_blame:.4f}")
    
    # === CHECK PRESSURE ===
    print(f"\n--- Pressure State ---")
    pressure = accumulator.get_pressure()
    print(f"  planner_confidence: {pressure.planner_confidence:.4f}")
    print(f"  risk_estimation: {pressure.risk_estimation:.4f}")
    print(f"  authority_threshold: {pressure.authority_threshold:.4f}")
    print(f"  goal_selection: {pressure.goal_selection:.4f}")
    print(f"  cost_projection: {pressure.cost_projection:.4f}")
    print(f"  max_pressure: {pressure.max_pressure:.4f}")
    print(f"  primary_pressure: {pressure.primary_pressure}")
    
    # Capture before adjustment
    primary_before_reset = pressure.primary_pressure
    
    # === TRIGGER ADJUSTMENT ===
    print(f"\n--- Adjustment ---")
    
    if policy.should_adjust():
        event = policy.adjust()
        if event:
            print(f"MUTATION: {event.dimension.value}")
            print(f"  Parameter: {event.parameter_name}")
            print(f"  Delta: {event.delta:.4f}")
            print(f"  Old: {event.old_value:.4f} -> New: {event.new_value:.4f}")
    else:
        print("No adjustment triggered (pressure below threshold)")
        # Force more accumulation
        for _ in range(3):
            for artifact in rollback_artifacts[:2]:
                blame = attribution.attribute(artifact)
                accumulator.accumulate(blame, artifact.regret_score)
                
        if policy.should_adjust():
            event = policy.adjust()
            if event:
                print(f"MUTATION (after extra accumulation): {event.dimension.value}")
                print(f"  Delta: {event.delta:.4f}")
    
    # === FINAL KNOB VALUES ===
    print(f"\n--- Final Knob Values ---")
    final_planner_conf = policy.get_knob_value(AdjustmentDimension.PLANNER_CONFIDENCE)
    final_auth_threshold = policy.get_knob_value(AdjustmentDimension.AUTHORITY_THRESHOLD)
    final_cost_projection = policy.get_knob_value(AdjustmentDimension.COST_PROJECTION)
    
    print(f"planner_confidence_dampener: {initial_planner_conf:.4f} -> {final_planner_conf:.4f}")
    print(f"authority_threshold_offset: {initial_auth_threshold:.4f} -> {final_auth_threshold:.4f}")
    print(f"cost_inflation_factor: {initial_cost_projection:.4f} -> {final_cost_projection:.4f}")
    
    planner_delta = final_planner_conf - initial_planner_conf
    auth_delta = final_auth_threshold - initial_auth_threshold
    cost_delta = final_cost_projection - initial_cost_projection
    
    print(f"\nDeltas:")
    print(f"  planner_confidence: {planner_delta:+.4f}")
    print(f"  authority_threshold: {auth_delta:+.4f}")
    print(f"  cost_projection: {cost_delta:+.4f}")
    
    # === ACCEPTANCE CRITERIA ===
    print("\n" + "="*60)
    print("ACCEPTANCE CRITERIA")
    print("="*60)
    
    # Criterion 1: >= 5 ROLLBACK_INVOKED artifacts
    crit1 = len(rollback_artifacts) >= 5
    print(f"1. >= 5 ROLLBACK_INVOKED artifacts: {len(rollback_artifacts)} >= 5? {crit1}")
    
    # Criterion 2: Planner blame is primary
    crit2 = avg_planner_blame > avg_auth_blame and avg_planner_blame > avg_cost_blame
    print(f"2. planner_blame is highest: {avg_planner_blame:.3f} > auth({avg_auth_blame:.3f}), cost({avg_cost_blame:.3f})? {crit2}")
    
    # Criterion 3: Primary pressure is planner_confidence (before reset)
    crit3 = primary_before_reset == "planner_confidence"
    print(f"3. primary_pressure == planner_confidence: {primary_before_reset}? {crit3}")
    
    # Criterion 4: Mutation was planner_confidence (if mutation occurred)
    mutation_events = log.get_by_dimension(AdjustmentDimension.PLANNER_CONFIDENCE)
    if len(log.events) > 0:
        crit4 = len(mutation_events) >= 1
        print(f"4. Mutation was PLANNER_CONFIDENCE: {len(mutation_events)} events? {crit4}")
    else:
        print(f"4. No mutation triggered (may need more pressure)")
        crit4 = False
        
    # Criterion 5: Authority and cost did NOT change (no blame leakage)
    crit5 = abs(auth_delta) < 0.001 and abs(cost_delta) < 0.001
    print(f"5. No blame leakage (auth_delta={auth_delta:.4f}, cost_delta={cost_delta:.4f}): {crit5}")
    
    # === VERDICT ===
    print("\n" + "="*60)
    print("VERDICT")
    print("="*60)
    
    all_passed = crit1 and crit2 and crit3 and crit4 and crit5
    
    if all_passed:
        print("\n[PASS] PLANNER CONFIDENCE LEARNING IS CALIBRATED")
    else:
        print("\n[FAIL] PLANNER CONFIDENCE LEARNING IS BROKEN")
        if not crit1:
            print("   - Not enough ROLLBACK_INVOKED artifacts")
        if not crit2:
            print("   - Planner blame is not primary")
        if not crit3:
            print("   - Primary pressure is not planner_confidence")
        if not crit4:
            print("   - Wrong dimension mutated or no mutation")
        if not crit5:
            print("   - Blame leakage to other dimensions (FRAGILE)")
    
    # Cleanup
    import shutil
    shutil.rmtree(test_dir)
    
    return {
        "passed": all_passed,
        "planner_delta": planner_delta,
        "auth_delta": auth_delta,
        "cost_delta": cost_delta,
        "artifacts": len(rollback_artifacts)
    }


if __name__ == "__main__":
    run_planner_confidence_test()
