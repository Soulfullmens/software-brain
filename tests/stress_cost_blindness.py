"""
Cost Blindness Stress Test

This is NOT a unit test. This is a judgment test.

Episode 1: Forced failure (budget exceeded, no mutation yet)
Episode 2: Learning trigger (mutation fires)
Episode 3: Behavioral proof (cost decreases)

If Episode 3 cost >= Episode 1 cost, learning is fake.
"""

import tempfile
import os
from pathlib import Path

from src.learning.regret import FailureArtifact, FailureType, RegretLedger
from src.learning.attribution import BlameVector, AttributionEngine
from src.learning.accumulation import BlameAccumulator
from src.learning.adjustment import AdjustmentPolicy, AdjustmentLog, AdjustmentDimension
from src.embodiment.shell import ShellBody
from src.embodiment.authorized_executor import AuthorizedExecutor
from src.agency.action import Action
from src.agency.authority import Authority, TrustModel


# === CONSTANTS ===
BUDGET_CEILING = 40  # Low ceiling to force failure
COST_PER_COMMAND = 5  # Each shell command costs 5
FORCED_COMMANDS_EP1 = 11  # 1 ls + 10 wc -c = 55 total (exceeds 40)


def setup_test_directory() -> Path:
    """Create directory with 50 small files + 3 large files."""
    test_dir = Path(tempfile.mkdtemp(prefix="stress_test_"))
    
    # 50 small files (~1 KB)
    for i in range(50):
        (test_dir / f"small_{i:03d}.txt").write_text("x" * 1024)
        
    # 3 large files (~10 KB for test speed)
    for i in range(3):
        (test_dir / f"large_{i}.txt").write_text("X" * 10240)
        
    return test_dir


def run_episode(
    episode_num: int,
    test_dir: Path,
    shell: ShellBody,
    ledger: RegretLedger,
    attribution: AttributionEngine,
    accumulator: BlameAccumulator,
    policy: AdjustmentPolicy,
    log: AdjustmentLog,
    forced_naive: bool = True
) -> dict:
    """
    Run one episode of the stress test.
    
    Returns metrics dict.
    """
    print(f"\n{'='*60}")
    print(f"EPISODE {episode_num}")
    print(f"{'='*60}")
    
    total_commands = 0
    total_cost = 0.0
    
    # Get cost inflation factor (affects planning)
    cost_factor = policy.get_knob_value(AdjustmentDimension.COST_PROJECTION)
    print(f"cost_inflation_factor at start: {cost_factor:.4f}")
    
    # === PLAN ===
    # For Episode 1, force naive (all files). For later episodes, allow pruning.
    files = list(test_dir.glob("*.txt"))
    
    if forced_naive:
        # Naive: check all files (forced in Episode 1)
        files_to_check = files[:10]  # Force exactly 10 wc calls
    else:
        # "Smart" behavior: use cost factor to decide sample size
        # Higher cost_factor → fewer files checked
        sample_size = max(3, int(10 / cost_factor))
        files_to_check = files[:sample_size]
        
    # === EXECUTE ===
    # Command 1: ls
    action_ls = Action(
        id="run_command",
        description=f"ls {test_dir}",
        rationale="List directory",
        irreversible=True,
        estimated_cost=COST_PER_COMMAND
    )
    shell.execute(action_ls)
    total_commands += 1
    total_cost += COST_PER_COMMAND
    
    # Commands 2-N: wc -c on each file
    for f in files_to_check:
        action_wc = Action(
            id="run_command",
            description=f"wc -c {f}",
            rationale=f"Count bytes in {f.name}",
            irreversible=True,
            estimated_cost=COST_PER_COMMAND
        )
        shell.execute(action_wc)
        total_commands += 1
        total_cost += COST_PER_COMMAND
        
        # Check budget after each command
        if total_cost > BUDGET_CEILING:
            # Emit COST_THRESHOLD_EXCEEDED artifact
            artifact = FailureArtifact(
                failure_type=FailureType.COST_THRESHOLD_EXCEEDED,
                goal_id=f"find_largest_ep{episode_num}",
                action_id="run_command",
                delta_cost=total_cost - BUDGET_CEILING,
                cost_before=BUDGET_CEILING,
                cost_after=total_cost,
                reason=f"Budget {BUDGET_CEILING} exceeded at {total_cost}"
            )
            ledger.record(artifact)
            
            # Attribution
            blame = attribution.attribute(artifact)
            
            # Accumulation
            accumulator.accumulate(blame, artifact.regret_score)
    
    # === POST-EPISODE METRICS ===
    print(f"\n--- Episode {episode_num} Metrics ---")
    print(f"total_shell_commands: {total_commands}")
    print(f"total_estimated_cost: {total_cost}")
    print(f"RegretLedger.summary(): {ledger.summary()}")
    print(f"PressureVector: {accumulator.get_pressure().to_dict()}")
    print(f"AdjustmentPolicy.summary(): {policy.summary()}")
    
    # === LEARNING (only after Episode 1) ===
    if episode_num >= 2:
        event = policy.adjust()
        if event:
            print(f"\n>>> MUTATION TRIGGERED: {event.dimension.value}")
            print(f"    delta: {event.delta:.4f}")
            print(f"    old: {event.old_value:.4f} -> new: {event.new_value:.4f}")
    
    return {
        "episode": episode_num,
        "total_commands": total_commands,
        "total_cost": total_cost,
        "ledger_summary": ledger.summary(),
        "pressure": accumulator.get_pressure().to_dict(),
        "policy": policy.summary()
    }


def run_stress_test():
    """Run the full 3-episode stress test."""
    print("\n" + "="*60)
    print("COST BLINDNESS STRESS TEST")
    print("="*60)
    print(f"Budget ceiling: {BUDGET_CEILING}")
    print(f"Cost per command: {COST_PER_COMMAND}")
    print(f"Forced commands (Episode 1): {FORCED_COMMANDS_EP1}")
    print(f"Expected total cost (Episode 1): {FORCED_COMMANDS_EP1 * COST_PER_COMMAND}")
    
    # Setup
    test_dir = setup_test_directory()
    print(f"Test directory: {test_dir}")
    
    # Components
    shell = ShellBody(working_dir=test_dir)
    ledger = RegretLedger()
    attribution = AttributionEngine()
    
    # Use settings that allow learning to trigger
    accumulator = BlameAccumulator(
        ema_alpha=0.5,
        decay_rate=1.0,  # No decay
        max_single_contribution=1.0  # No capping
    )
    log = AdjustmentLog()
    policy = AdjustmentPolicy(
        accumulator=accumulator,
        log=log,
        threshold=0.15,  # Moderate threshold
        sensitivity=0.1
    )
    
    results = []
    
    # === EPISODE 1: Forced Failure ===
    ep1 = run_episode(
        episode_num=1,
        test_dir=test_dir,
        shell=shell,
        ledger=ledger,
        attribution=attribution,
        accumulator=accumulator,
        policy=policy,
        log=log,
        forced_naive=True  # LOCKED naive behavior
    )
    results.append(ep1)
    
    # Verify Episode 1 acceptance criteria
    cost_exceeded_count = len([
        a for a in ledger.artifacts 
        if a.failure_type == FailureType.COST_THRESHOLD_EXCEEDED
    ])
    print(f"\nEpisode 1 acceptance: {cost_exceeded_count} >= 2? {cost_exceeded_count >= 2}")
    
    # === EPISODE 2: Learning Trigger ===
    ep2 = run_episode(
        episode_num=2,
        test_dir=test_dir,
        shell=shell,
        ledger=ledger,
        attribution=attribution,
        accumulator=accumulator,
        policy=policy,
        log=log,
        forced_naive=True  # Still naive to build more pressure
    )
    results.append(ep2)
    
    # === EPISODE 3: Behavioral Proof ===
    ep3 = run_episode(
        episode_num=3,
        test_dir=test_dir,
        shell=shell,
        ledger=ledger,
        attribution=attribution,
        accumulator=accumulator,
        policy=policy,
        log=log,
        forced_naive=False  # NOW allow learning to influence
    )
    results.append(ep3)
    
    # === FINAL VERDICT ===
    print("\n" + "="*60)
    print("FINAL VERDICT")
    print("="*60)
    
    print(f"\nEpisode 1 cost: {ep1['total_cost']}")
    print(f"Episode 3 cost: {ep3['total_cost']}")
    
    cost_reduced = ep3['total_cost'] < ep1['total_cost']
    mutation_triggered = len(log.events) > 0
    
    print(f"\nCost reduced: {cost_reduced}")
    print(f"Mutation triggered: {mutation_triggered}")
    print(f"AdjustmentLog events: {len(log.events)}")
    
    if cost_reduced and mutation_triggered:
        print("\n[PASS] LEARNING IS REAL")
    else:
        print("\n[FAIL] LEARNING IS FAKE")
        if not mutation_triggered:
            print("   - No mutation triggered")
        if not cost_reduced:
            print("   - Cost did not decrease")
    
    # Cleanup
    import shutil
    shutil.rmtree(test_dir)
    
    return results


if __name__ == "__main__":
    run_stress_test()
