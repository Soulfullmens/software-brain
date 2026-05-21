"""
BIND ASSIGNMENT 001: SOURCE INTEGRITY MONITOR

Role:
- Compute deterministic Merkle Root Hash of src/
- Assert Mode == EVALUATE
- Write baseline to data/integrity_baselines/src.lock
- Log BIND event
"""
import os
import hashlib
import json
from pathlib import Path
from datetime import datetime

from src.core.config import DEFAULT_LEARNING_MODE
from src.learning.learning_mode import LearningMode
from src.ops.integrity import compute_merkle_root

TARGET_DIR = Path("src").resolve()
BASELINE_DIR = Path("data/integrity_baselines").resolve()
LOCK_FILE = BASELINE_DIR / "src.lock"
LOG_FILE = BASELINE_DIR / "binding.log"

def bind_assignment():
    print(">>> BINDING OPERATIONS ASSIGNMENT 001 <<<")
    
    # 1. Assert Mode
    print(f"Checking Mode... {DEFAULT_LEARNING_MODE}")
    if DEFAULT_LEARNING_MODE != LearningMode.EVALUATE:
        print("FAIL: System must be in EVALUATE mode to bind.")
        return False
        
    # 2. Compute Baseline
    print(f"Scanning {TARGET_DIR}...")
    root_hash = compute_merkle_root(TARGET_DIR)
    print(f"Merkle Root: {root_hash}")
    
    # 3. Persist Lock
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    
    lock_data = {
        "assignment_id": "OPERATIONS_ASSIGNMENT_001",
        "target": str(TARGET_DIR),
        "merkle_root": root_hash,
        "timestamp": datetime.now().isoformat(),
        "mode_at_bind": DEFAULT_LEARNING_MODE.value,
        "binding_agent": "Software Brain v0"
    }
    
    with open(LOCK_FILE, "w") as f:
        json.dump(lock_data, f, indent=2)
        
    print(f"LOCKED: {LOCK_FILE}")
    
    # 4. Log Event
    with open(LOG_FILE, "a") as f:
        log_entry = f"[{datetime.now().isoformat()}] BIND: {root_hash} (Mode={DEFAULT_LEARNING_MODE.value})\n"
        f.write(log_entry)
        
    print("SUCCESS: Assignment Bound.")
    return True

if __name__ == "__main__":
    bind_assignment()
