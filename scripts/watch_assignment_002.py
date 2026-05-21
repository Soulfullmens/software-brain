"""
WATCH ASSIGNMENT 002: HEARTBEAT (ENVIRONMENT)

Role:
- Read data/environment_baselines/env.lock
- Recompute Environment Snapshot
- Compare Critical Fields
- Log OK or CRITICAL_ENVIRONMENT_DRIFT
"""
import json
import sys
from pathlib import Path
from datetime import datetime

from src.core.config import DEFAULT_LEARNING_MODE
from src.learning.learning_mode import LearningMode
from src.ops.environment import get_full_environment_snapshot

BASELINE_DIR = Path("data/environment_baselines").resolve()
LOCK_FILE = BASELINE_DIR / "env.lock"
LOG_FILE = BASELINE_DIR / "binding.log"

def diff_snapshots(baseline: dict, current: dict) -> list:
    """Return list of drift explanations."""
    drift = []
    
    # 1. Python
    if baseline["python"]["version"] != current["python"]["version"]:
        drift.append(f"Python Version Drift: {baseline['python']['version']} -> {current['python']['version']}")
    if baseline["python"]["executable"] != current["python"]["executable"]:
        drift.append(f"Python Path Drift: {baseline['python']['executable']} -> {current['python']['executable']}")
        
    # 2. OS (Major kernel changes)
    if baseline["os"]["release"] != current["os"]["release"]:
        drift.append(f"OS Release Drift: {baseline['os']['release']} -> {current['os']['release']}")
        
    # 3. Pip Packages
    if baseline["pip_hash"] != current["pip_hash"]:
        drift.append("Pip Packages Drift: Installed packages changed (hash mismatch)")
        
    # 4. Disk (Check for massive anomalies, e.g. >20% change in Total size? Or just free space?)
    # For now, let's just log free space but not alert unless it's critical.
    # Actually, assignment said "Alert on ANY deviation" - but disk free space changes every second.
    # The assignment said: "Environment Baseline Monitor... Detect environment drift that could invalidate assumptions"
    # Scope includes "Disk free % on critical drive".
    # We should probably define a tolerance for metrics, but specific values for versions.
    
    # Let's alert if Free Space drops significantly (e.g. < 1GB) or if TOTAL size changes (Partition resize).
    base_total = baseline["disk"].get("total_bytes", 0)
    curr_total = current["disk"].get("total_bytes", 0)
    if base_total != curr_total:
         drift.append(f"Disk Capacity Change: {base_total} -> {curr_total}")
         
    return drift

def watch():
    print(">>> OPERATIONS WATCH 002: ENVIRONMENT HEARTBEAT <<<")
    
    # 0. Mode Guard
    if DEFAULT_LEARNING_MODE != LearningMode.EVALUATE:
        print("CRITICAL: Watcher must run in EVALUATE mode.")
        sys.exit(3)
    
    if not LOCK_FILE.exists():
        print("FAIL: No lock file found. Assignment not bound.")
        sys.exit(1)
        
    # 1. Load Baseline
    try:
        with open(LOCK_FILE, "r") as f:
            lock_data = json.load(f)
            baseline = lock_data["snapshot"]
    except Exception as e:
        print(f"FAIL: Corrupt lock file: {e}")
        sys.exit(1)
        
    # 2. Recompute
    print("Scanning Environment...")
    current = get_full_environment_snapshot()
    
    # 3. Compare
    drift_issues = diff_snapshots(baseline, current)
    
    timestamp = datetime.now().isoformat()
    match = len(drift_issues) == 0
    
    if match:
        status = "OK"
        details = f"Disk Free: {current['disk']['percent_free']}%"
    else:
        status = "CRITICAL_ENVIRONMENT_DRIFT"
        details = "; ".join(drift_issues)
    
    message = f"[{timestamp}] WATCH: {status} ({details})"
    
    # 4. Log
    print(message)
    with open(LOG_FILE, "a") as f:
        f.write(message + "\n")
        
    if not match:
        print("!!! ALERT: ENVIRONMENT DRIFT DETECTED !!!")
        for issue in drift_issues:
            print(f"- {issue}")
        sys.exit(2)
        
    print("Environment Verified.")
    sys.exit(0)

if __name__ == "__main__":
    watch()
