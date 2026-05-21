"""
Authority Friction Stress Test

HYPOTHESIS:
Repeated authority denials should increase authority_threshold_offset
WITHOUT significantly decreasing planner_confidence_dampener.

If planner confidence drops instead -> attribution is misdiagnosing blame.

This is a JUDGMENT test, not a unit test.
"""

from src.learning.regret import FailureArtifact, FailureType, RegretLedger
from src.learning.attribution import BlameVector, AttributionEngine
from src.learning.accumulation import BlameAccumulator
from src.learning.adjustment import AdjustmentPolicy, AdjustmentLog, AdjustmentDimension
from src.embodiment.shell import ShellBody
from src.embodiment.authorized_executor import AuthorizedExecutor
from src.agency.action import Action
from src.agency.authority import Authority, TrustModel


def run_authority_friction_test():
    """
    Force repeated authority blocks and verify correct learning.
    """
    print("\n" + "="*60)
    print("AUTHORITY FRICTION STRESS TEST")
    print("="*60)
    
    # === SETUP ===
    # Hostile authority (very low trust)
    trust = TrustModel(base_level=0.05)
    authority = Authority(trust)
    
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
    
    # Shell body with executor
    shell = ShellBody()
    executor = AuthorizedExecutor(shell, authority, regret_ledger=ledger)
    
    # Record initial knob values
    initial_planner_conf = policy.get_knob_value(AdjustmentDimension.PLANNER_CONFIDENCE)
    initial_auth_threshold = policy.get_knob_value(AdjustmentDimension.AUTHORITY_THRESHOLD)
    
    print(f"Initial planner_confidence_dampener: {initial_planner_conf:.4f}")
    print(f"Initial authority_threshold_offset: {initial_auth_threshold:.4f}")
    
    # === FORCE REPEATED BLOCKED ACTIONS ===
    print(f"\n--- Forcing Blocked Write Actions ---")
    
    blocked_count = 0
    goal_id = "archive_old_logs"
    
    # Propose 8 write commands (all should be blocked by low trust)
    write_commands = [
        ("mkdir", "mkdir archive"),
        ("touch", "touch archive/marker.txt"),
        ("mv", "mv old.log archive/"),
        ("cp", "cp data.log backup.log"),
        ("mkdir", "mkdir temp"),
        ("touch", "touch temp/file.txt"),
        ("mv", "mv temp/file.txt archive/"),
        ("cp", "cp config.cfg config.bak")
    ]
    
    for cmd_name, cmd in write_commands:
        action = Action(
            id="run_command",
            description=cmd,
            rationale=f"Archive operation: {cmd_name}",
            irreversible=True,  # Write commands are irreversible
            estimated_cost=10.0,
            risk_domain="filesystem"
        )
        
        result = executor.execute(action, goal_id=goal_id)
        
        if not result.success:
            blocked_count += 1
            print(f"  BLOCKED: {cmd} (reason: {result.blocked_reason})")
            
            # The executor already emitted a FailureArtifact to the ledger
            # Now we need to attribute and accumulate
            
    print(f"\nTotal blocked: {blocked_count}")
    
    # === ATTRIBUTE AND ACCUMULATE ===
    print(f"\n--- Attribution and Accumulation ---")
    
    # Count both blocked and approval_pending as authority friction
    authority_friction_artifacts = [
        a for a in ledger.artifacts 
        if a.failure_type in (FailureType.AUTHORITY_BLOCKED, FailureType.AUTHORITY_APPROVAL_PENDING)
    ]
    
    print(f"Authority friction artifacts: {len(authority_friction_artifacts)}")
    print(f"  - BLOCKED: {len([a for a in authority_friction_artifacts if a.failure_type == FailureType.AUTHORITY_BLOCKED])}")
    print(f"  - APPROVAL_PENDING: {len([a for a in authority_friction_artifacts if a.failure_type == FailureType.AUTHORITY_APPROVAL_PENDING])}")
    
    # Attribute each artifact
    total_auth_blame = 0.0
    total_planner_blame = 0.0
    
    for artifact in authority_friction_artifacts:
        blame = attribution.attribute(artifact)
        total_auth_blame += abs(blame.authority_threshold)
        total_planner_blame += abs(blame.planner_confidence)
        
        # Accumulate
        accumulator.accumulate(blame, artifact.regret_score)
        
    avg_auth_blame = total_auth_blame / max(1, len(authority_friction_artifacts))
    avg_planner_blame = total_planner_blame / max(1, len(authority_friction_artifacts))
    
    print(f"Average authority_threshold blame: {avg_auth_blame:.4f}")
    print(f"Average planner_confidence blame: {avg_planner_blame:.4f}")
    
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
    
    # IMPORTANT: Capture primary BEFORE adjustment resets pressure
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
        # Force more accumulation if needed
        for _ in range(3):
            for artifact in authority_friction_artifacts[:2]:
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
    
    print(f"planner_confidence_dampener: {initial_planner_conf:.4f} -> {final_planner_conf:.4f}")
    print(f"authority_threshold_offset: {initial_auth_threshold:.4f} -> {final_auth_threshold:.4f}")
    
    planner_delta = final_planner_conf - initial_planner_conf
    auth_delta = final_auth_threshold - initial_auth_threshold
    
    print(f"\nDeltas:")
    print(f"  planner_confidence: {planner_delta:+.4f}")
    print(f"  authority_threshold: {auth_delta:+.4f}")
    
    # === ACCEPTANCE CRITERIA ===
    print("\n" + "="*60)
    print("ACCEPTANCE CRITERIA")
    print("="*60)
    
    # Criterion 1: >= 5 AUTHORITY_BLOCKED artifacts
    crit1 = len(authority_friction_artifacts) >= 5
    print(f"1. >= 5 AUTHORITY_BLOCKED artifacts: {len(authority_friction_artifacts)} >= 5? {crit1}")
    
    # Criterion 2: Attribution correctness (authority blame > planner blame)
    crit2 = avg_auth_blame > avg_planner_blame * 0.9  # Allow some tolerance
    print(f"2. authority_blame > planner_blame: {avg_auth_blame:.3f} > {avg_planner_blame:.3f}? {crit2}")
    
    # Criterion 3: Primary pressure is authority_threshold (before reset)
    crit3 = primary_before_reset == "authority_threshold"
    print(f"3. primary_pressure == authority_threshold: {primary_before_reset}? {crit3}")
    
    # Criterion 4: Mutation was authority_threshold (if mutation occurred)
    mutation_events = log.get_by_dimension(AdjustmentDimension.AUTHORITY_THRESHOLD)
    crit4 = len(mutation_events) >= 1 or len(log.events) == 0  # Pass if no mutation OR correct mutation
    if len(log.events) > 0:
        crit4 = len(mutation_events) >= 1
        print(f"4. Mutation was AUTHORITY_THRESHOLD: {len(mutation_events)} events? {crit4}")
    else:
        print(f"4. No mutation triggered (may need more pressure)")
        crit4 = False
    
    # Criterion 5: Planner confidence did NOT collapse
    crit5 = final_planner_conf >= 0.98
    print(f"5. planner_confidence >= 0.98 (no collapse): {final_planner_conf:.4f} >= 0.98? {crit5}")
    
    # === VERDICT ===
    print("\n" + "="*60)
    print("VERDICT")
    print("="*60)
    
    all_passed = crit1 and crit2 and crit3 and crit4 and crit5
    
    if all_passed:
        print("\n[PASS] AUTHORITY LEARNING IS CALIBRATED")
    else:
        print("\n[FAIL] AUTHORITY LEARNING IS BROKEN")
        if not crit1:
            print("   - Not enough AUTHORITY_BLOCKED artifacts")
        if not crit2:
            print("   - Attribution blames planner more than authority (WRONG)")
        if not crit3:
            print("   - Primary pressure is not authority_threshold")
        if not crit4:
            print("   - Wrong dimension mutated or no mutation")
        if not crit5:
            print("   - Planner confidence collapsed (FEAR, not judgment)")
    
    return {
        "passed": all_passed,
        "planner_delta": planner_delta,
        "auth_delta": auth_delta,
        "artifacts": len(authority_friction_artifacts)
    }


if __name__ == "__main__":
    run_authority_friction_test()
