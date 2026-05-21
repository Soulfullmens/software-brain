"""
BIND ASSIGNMENT 002: ENVIRONMENT SENTINEL

Role:
- Capture Environment Snapshot (Python, OS, Disk, Pip)
- Assert Mode == EVALUATE
- Write baseline to data/environment_baselines/env.lock
- Log BIND event
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

def bind_assignment():
    print(">>> BINDING OPERATIONS ASSIGNMENT 002 <<<")
    
    # 1. Assert Mode
    print(f"Checking Mode... {DEFAULT_LEARNING_MODE}")
    if DEFAULT_LEARNING_MODE != LearningMode.EVALUATE:
        print("FAIL: System must be in EVALUATE mode to bind.")
        sys.exit(1)
        
    # 2. Capture Snapshot
    print("Capturing Environment Snapshot...")
    snapshot = get_full_environment_snapshot()
    
    # 3. Persist Lock
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    
    lock_data = {
        "assignment_id": "OPERATIONS_ASSIGNMENT_002",
        "snapshot": snapshot,
        "timestamp": datetime.now().isoformat(),
        "mode_at_bind": DEFAULT_LEARNING_MODE.value,
        "binding_agent": "Software Brain v0"
    }
    
    with open(LOCK_FILE, "w") as f:
        json.dump(lock_data, f, indent=2)
        
    print(f"LOCKED: {LOCK_FILE}")
    
    # 4. Log Event
    with open(LOG_FILE, "a") as f:
        log_entry = f"[{datetime.now().isoformat()}] BIND: EnvHash={snapshot['pip_hash'][:8]}... (Mode={DEFAULT_LEARNING_MODE.value})\n"
        f.write(log_entry)
        
    print("SUCCESS: Assignment Bound.")
    return True

if __name__ == "__main__":
    bind_assignment()
