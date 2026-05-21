"""
WATCH ASSIGNMENT 001: HEARTBEAT

Role:
- Read data/integrity_baselines/src.lock
- Recompute Merkle Root
- Compare
- Log OK or CRITICAL
"""
import json
import sys
from pathlib import Path
from datetime import datetime

from src.core.config import DEFAULT_LEARNING_MODE
from src.learning.learning_mode import LearningMode
from src.ops.integrity import compute_merkle_root

# Re-define paths here to avoid script import dependency, or keep referencing constants if needed.
# Better to define them locally or in a config, but for now we follow the pattern.
BASELINE_DIR = Path("data/integrity_baselines").resolve()
LOCK_FILE = BASELINE_DIR / "src.lock"
LOG_FILE = BASELINE_DIR / "binding.log"

def watch():
    print(">>> OPERATIONS WATCH 001: HEARTBEAT <<<")
    
    # 0. Mode Guard (REQUIRED FIX #1)
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
            expected_hash = lock_data["merkle_root"]
            target_path = Path(lock_data["target"])
    except Exception as e:
        print(f"FAIL: Corrupt lock file: {e}")
        sys.exit(1)
        
    # 2. Recompute
    print(f"Scanning {target_path}...")
    current_hash = compute_merkle_root(target_path)
    
    # 3. Compare
    timestamp = datetime.now().isoformat()
    match = (current_hash == expected_hash)
    
    status = "OK" if match else "CRITICAL_INTEGRITY_VIOLATION"
    message = f"[{timestamp}] WATCH: {status} (Expected={expected_hash[:8]}..., Actual={current_hash[:8]}...)"
    
    # 4. Log
    print(message)
    with open(LOG_FILE, "a") as f:
        f.write(message + "\n")
        
    if not match:
        print("!!! ALERT: SOURCE CODE INTEGRITY COMPROMISED !!!")
        sys.exit(2)
        
    print("Integrity Verified.")
    sys.exit(0)

if __name__ == "__main__":
    watch()
