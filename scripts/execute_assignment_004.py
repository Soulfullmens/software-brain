"""
EXECUTE ASSIGNMENT 004: ROLLBACK DRILL

Objective:
- Prove we can UNDO a destructive action.
- Target: tmp_ops_sandbox/logs/rollback_test.log
- Sequence: Create -> Delete (Action) -> Rollback (Body) -> Verify
- Mode: EVALUATE only
"""
import sys
import hashlib
import time
from pathlib import Path

# Fix path
sys.path.append(".")

from src.core.config import DEFAULT_LEARNING_MODE
from src.learning.learning_mode import LearningMode
from src.embodiment.filesystem import FilesystemBody
from src.agency.action import Action

SANDBOX_PATH = Path("tmp_ops_sandbox").resolve()
TEST_FILE_REL = "logs/rollback_test.log"
TEST_CONTENT = "This is a drill. This file must survive."

def execution_drill():
    print(">>> ASSIGNMENT 004: ROLLBACK DRILL <<<")
    
    # 1. Mode Guard
    if DEFAULT_LEARNING_MODE != LearningMode.EVALUATE:
        print("CRITICAL: Assignment must run in EVALUATE mode.")
        sys.exit(3)
        
    fs = FilesystemBody(sandbox_root=SANDBOX_PATH)
    
    # 2. Setup (Controlled Damage Prep)
    print("Step 1: Creating Test File...")
    # Using underlying FS to set up the 'world state' before the agent acts
    target_path = SANDBOX_PATH / TEST_FILE_REL
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(TEST_CONTENT, encoding="utf-8")
    
    # Record Baseline
    original_size = target_path.stat().st_size
    original_hash = hashlib.sha256(target_path.read_bytes()).hexdigest()
    print(f"  Created: {target_path} (Size: {original_size}, Hash: {original_hash[:8]})")
    
    # 3. Execute Destructive Action
    print("Step 2: Executing 'delete_file' Action...")
    action = Action(
        id="delete_file",
        target=TEST_FILE_REL,
        irreversible=False, # Soft delete
        estimated_cost=0.5,
        description="Rollback Drill Deletion",
        rationale="Testing undo capability"
    )
    
    event = fs.execute(action)
    
    if not event or not event.payload.get("success"):
        print("FAIL: Deletion failed.")
        sys.exit(1)
        
    # Verify Deletion
    if target_path.exists():
        print("FAIL: File still exists after deletion!")
        sys.exit(1)
        
    print("  File Deleted.")
    
    # 4. Extract Rollback Metadata
    payload = event.payload
    trash_path_str = payload.get("trash_path")
    rollback_possible = payload.get("rollback_possible")
    
    print(f"  Trash Path: {trash_path_str}")
    
    if not rollback_possible or not trash_path_str:
        print("FAIL: Rollback metadata missing!")
        sys.exit(2)
        
    # Extract trash entry ID (Parent folder name)
    # Payload trash_path is full path to file inside trash entry
    trash_path = Path(trash_path_str)
    trash_entry_name = trash_path.parent.name
    
    print(f"Step 3: Initiating Rollback (Entry: {trash_entry_name})...")
    
    # 5. Execute Rollback
    # Note: restore_from_trash is a Body method, not an Action yet.
    # In a full agent, this would be an Action("restore_file"), but strictly speaking
    # the Body exposes it. The drill tests the CAPABILITY.
    
    success = fs.restore_from_trash(trash_entry_name)
    
    if not success:
        print("FAIL: restore_from_trash returned False")
        sys.exit(2)
        
    # 6. Verification
    print("Step 4: Verifying Restoration...")
    
    if not target_path.exists():
        print("FAIL: File not found after restore!")
        sys.exit(3)
        
    restored_content = target_path.read_text(encoding="utf-8")
    restored_hash = hashlib.sha256(restored_content.encode("utf-8")).hexdigest()
    
    print(f"  Restored Hash: {restored_hash[:8]}")
    
    if restored_hash != original_hash:
        print("FAIL: Content mismatch!")
        print(f"Expected: {TEST_CONTENT}")
        print(f"Got:      {restored_content}")
        sys.exit(3)
        
    print("SUCCESS: Full cycle complete. Integrity preserved.")
    
    # Cleanup (Clean trace)
    target_path.unlink()
    
if __name__ == "__main__":
    execution_drill()
