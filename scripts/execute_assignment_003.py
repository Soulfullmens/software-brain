"""
EXECUTE ASSIGNMENT 003: DETERMINISTIC LOG RETENTION

Objective:
- Enforce hygiene in tmp_ops_sandbox/logs
- Delete *.log > 7 days old
- Assert EVALUATE mode
- Use FilesystemBody Action (delete_file)
"""
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Fix path to allow imports from src
sys.path.append(".")

from src.core.config import DEFAULT_LEARNING_MODE
from src.learning.learning_mode import LearningMode
from src.embodiment.filesystem import FilesystemBody
from src.agency.action import Action

# === CONFIGURATION ===
SANDBOX_PATH = Path("tmp_ops_sandbox").resolve()
TARGET_SUBDIR = "logs"
RETENTION_DAYS = 7
DRY_RUN = False # Safety switch for testing logic logic if needed, but we want real execution.

def execute_maintenance():
    print(">>> ASSIGNMENT 003: LOG RETENTION <<<")
    
    # 1. Mode Guard
    if DEFAULT_LEARNING_MODE != LearningMode.EVALUATE:
        print("CRITICAL: Assignment must run in EVALUATE mode.")
        sys.exit(3)
        
    start_time = time.time()
    
    # 2. Setup Embodiment (The "Hands")
    fs = FilesystemBody(sandbox_root=SANDBOX_PATH)
    
    # 3. Scanning logic
    scan_path = SANDBOX_PATH / TARGET_SUBDIR
    if not scan_path.exists():
         print(f"Target directory {scan_path} does not exist.")
         sys.exit(0)
         
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    
    files_scanned = 0
    files_deleted = 0
    bytes_reclaimed = 0
    
    print(f"Scanning {scan_path} for logs older than {RETENTION_DAYS} days...")
    
    for item in scan_path.iterdir():
        if not item.is_file():
            continue
        if item.suffix != ".log":
            continue
            
        files_scanned += 1
        stat = item.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime)
        size = stat.st_size
        
        if mtime < cutoff:
            # === ACTION EXECUTION ===
            rel_path = item.relative_to(SANDBOX_PATH).as_posix()
            
            # Explicit Safety Check (Sandbox)
            if not item.resolve().is_relative_to(SANDBOX_PATH):
                print(f"SECURITY VIOLATION: Path escape attempt: {item}")
                continue
                
            print(f"Deleting {rel_path} (Age: {mtime})...")
            
            # Construct Action
            action = Action(
                id="delete_file",
                target=rel_path,
                irreversible=False, # Soft delete is reversible
                estimated_cost=float(size),
                description="Routine Maintenance: Log Pruning",
                rationale="File exceeds retention policy (>7 days)"
            )
            
            # Execute via Body
            event = fs.execute(action)
            
            if event and event.payload.get("success"):
                files_deleted += 1
                bytes_reclaimed += size
                # Check for trash metadata in payload
                trash_path = event.payload.get("trash_path")
                print(f"  [OK] Moved to {trash_path}")
            else:
                error = event.payload.get("content") if event else "Unknown error"
                print(f"  [FAIL] {error}")
                
    duration = time.time() - start_time
    
    # 4. Accounting (Not Learning)
    print("\n=== EXECUTION SUMMARY ===")
    print(f"Duration: {duration:.4f}s")
    print(f"Scanned: {files_scanned}")
    print(f"Deleted: {files_deleted}")
    print(f"Reclaimed: {bytes_reclaimed} bytes")
    print("=========================")
    
    if files_deleted == 0 and files_scanned > 0:
        print("Idempotency: No actions needed.")
        
if __name__ == "__main__":
    execute_maintenance()
