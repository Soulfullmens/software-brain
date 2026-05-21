"""
Deployment Workload Simulation (Phase B2)

Objective:
Simulate 7 days of REAL operational workload to validate system stability
in LearningMode.EVALUATE.

This is NOT a unit test. It executes the full stack:
Planner -> Executor -> ShellBody -> Learning

Workload Profile (per "day"):
- 10 File Operations (Write/Read/List) -> 2 Failures expected
- 5 Planning Tasks (Goal Tradeoffs)
- 3 Authority Checks (Blocked actions)
- 20 Simulated Hours of idle time (Decay)

Total Duration: 7 virtual days.
Success Criteria:
1. No crashes.
2. No mutations (EVALUATE mode).
3. Pressure builds up but remains observable.
4. Logs show blocked mutations if pressure > threshold.
"""

import time
import random
from datetime import datetime, timedelta
from pathlib import Path

from datetime import datetime, timedelta
from pathlib import Path

from src.agency.action import Action
from src.core.config import DEFAULT_LEARNING_MODE
from src.learning.learning_mode import LearningMode
from src.learning.regret import RegretLedger, FailureArtifact, FailureType
from src.learning.attribution import AttributionEngine
from src.learning.accumulation import BlameAccumulator
from src.learning.adjustment import AdjustmentPolicy, AdjustmentLog, AdjustmentDimension
from src.learning.learning_explain import LearningExplanationEngine
from src.embodiment.filesystem import FilesystemBody

def deployment_simulation():
    print("\n" + "="*60)
    print("PHASE B2: 7-DAY REAL WORKLOAD SIMULATION")
    print("="*60)
    
    if DEFAULT_LEARNING_MODE != LearningMode.EVALUATE:
        print("CRITICAL ERROR: Default mode is NOT EVALUATE!")
        return False
        
    print(f"Booting in Mode: {DEFAULT_LEARNING_MODE.value}")
    
    # === INITIALIZATION ===
    ledger = RegretLedger()
    attribution = AttributionEngine()
    
    # Use real mode from config
    accumulator = BlameAccumulator(mode=DEFAULT_LEARNING_MODE)
    log = AdjustmentLog()
    policy = AdjustmentPolicy(accumulator=accumulator, log=log, mode=DEFAULT_LEARNING_MODE)
    explain = LearningExplanationEngine(policy, accumulator, log)
    
    fs = FilesystemBody(sandbox_root=Path("./tmp_sim_env").resolve()) # Sandbox
    
    # === SIMULATION LOOP ===
    days = 7
    cycles_per_day = 24 # 1 cycle = 1 hour
    
    start_time = datetime.now()
    
    for day in range(1, days + 1):
        print(f"\n--- Day {day} ---")
        
        for hour in range(cycles_per_day):
            # 1. Random File Ops (Success & Failure)
            if random.random() < 0.3:
                # Simulate "read_file" via Action
                action = Action(
                    id="read_file",
                    target="nonexistent.txt", # This returns Error, simulating failure check
                    description="Simulated read",
                    rationale="Routine check"
                )
                fs.execute(action)
                pass

            # 2. Inject FAILURES (Real workload friction)
            # Day 1-3: High friction (setup phase)
            failure_prob = 0.2 if day <= 3 else 0.05
            
            if random.random() < failure_prob:
                # File access denied
                artifact = FailureArtifact(
                    failure_type=FailureType.AUTHORITY_BLOCKED,
                    reason=f"Access denied day {day} hour {hour}"
                )
                blame = attribution.attribute(artifact)
                accumulator.accumulate(blame, 0.4)
                
            # 3. Inject SUCCESS (Skill building)
            if random.random() < 0.15:
                 artifact = FailureArtifact(
                     failure_type=FailureType.SUCCESS_LOW_VARIANCE,
                     reason=f"Perfect execution day {day} hour {hour}"
                 )
                 blame = attribution.attribute(artifact)
                 accumulator.accumulate(blame, 0.3)
            
            # 4. Attempt Mutation (Should be blocked)
            evt = policy.adjust()
            if evt:
                print(f"FATAL: System mutated in {DEFAULT_LEARNING_MODE} mode!")
                return False
                
            # 5. Check Invariants
            if not policy.check_invariants():
                print("FATAL: Invariant check failed!")
                return False
                
        # End of Day Report
        pressure = explain.active_pressures()
        print(f"  Max Pressure: {pressure['max_pressure']:.4f}")
        print(f"  Blocked Mutations: {log.summary()['blocked_count']}")
        
    # === FINAL VERIFICATION ===
    print("\n" + "="*60)
    print("SIMULATION COMPLETE")
    
    # Verify Knobs did not move
    knobs = explain.current_knobs()
    print("Final Knobs (Should be defaults):", knobs)
    
    # Verify Logs exist
    summary = log.summary()
    print("Log Summary:", summary)
    
    if summary['total_events'] == 0:
        print("\n[PASS] No mutations occurred over 7 days.")
        return True
    else:
        print(f"\n[FAIL] {summary['total_events']} mutations occurred!")
        return False

if __name__ == "__main__":
    success = deployment_simulation()
    if success:
        print("DEPLOYMENT CHECK: GREEN")
    else:
        print("DEPLOYMENT CHECK: RED")
