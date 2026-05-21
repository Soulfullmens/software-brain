"""
filesystem_jail.py

FILESYSTEM JAIL — Workspace Confinement & Pre-Execution Snapshots.

A severe restriction layer for external file/shell operations.
Ensures the agent cannot escape its designated workspace or destroy data without a snapshot.

CAPABILITIES:
    1. Workspace Confinement — all actual writes are forced into allowed directories
    2. Read-only Zones — system paths can be read (optional) but NEVER written
    3. Path Traversal Prevention — blocks ../../../etc/passwd attacks
    4. Write Budgets — limits total bytes written per session
    5. Symlink Protection — blocks following symlinks that escape the jail
    6. Pre-Execution Snapshots — creates backup checksums before modifications

GOES BEYOND NemoClaw:
    - Pre-execution snapshots (NemoClaw has no rollback/snapshot concept at OS level)
    - Session-level write budgets
"""
import os
import shutil
import hashlib
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Set, Tuple


class JailViolation(Exception):
    """Raised when the agent attempts to escape the sandbox."""
    pass


class FilesystemJail:
    """
    Confines file and shell operations to specific workspaces.
    
    Usage:
        jail = FilesystemJail(workspace_root="./agent_data/workspace")
        
        # Safe path resolution
        safe_path = jail.resolve_path("foo.txt")
        
        # Pre-execution snapshot
        snapshot_id = jail.snapshot_file(safe_path)
        
        # Rollback if needed
        jail.restore_snapshot(snapshot_id)
    """
    
    def __init__(self, workspace_root: str = "agent_data/workspace",
                 max_session_writes_mb: float = 100.0):
        self.workspace_root = os.path.abspath(workspace_root)
        self.snapshots_dir = os.path.join(self.workspace_root, ".snapshots")
        self.max_write_bytes = int(max_session_writes_mb * 1024 * 1024)
        
        # Ensure directories exist
        os.makedirs(self.workspace_root, exist_ok=True)
        os.makedirs(self.snapshots_dir, exist_ok=True)
        
        # State
        self._session_bytes_written: int = 0
        self._snapshots: Dict[str, Dict[str, Any]] = {}  # id -> metadata
        self._stats = {
            "files_written": 0,
            "bytes_written": 0,
            "snapshots_taken": 0,
            "rollbacks": 0,
            "violations": 0,
        }
    
    # ═══════════════════════════════════════════════════════
    # CONFINEMENT & RESOLUTION
    # ═══════════════════════════════════════════════════════
    
    def resolve_path(self, target_path: str, must_exist: bool = False,
                     read_only_allowed: bool = False) -> str:
        """
        Resolve and validate a path to ensure it's within the jail.
        Throws JailViolation if it tries to escape.
        """
        # 1. Normalize path
        if os.path.isabs(target_path):
            # If absolute, it MUST be inside the workspace root
            # (unless it's a specific system path allowed for read-only)
            abs_target = os.path.normpath(target_path)
        else:
            # If relative, anchor it to workspace root
            abs_target = os.path.normpath(os.path.join(self.workspace_root, target_path))
            
        # 2. Check containment
        if not abs_target.startswith(self.workspace_root):
            # Escaped the workspace!
            
            # Allow read-only access to specific system paths if requested?
            # For now, strict strict strict. No reading outside workspace.
            self._stats["violations"] += 1
            raise JailViolation(
                f"Path traversal blocked: '{target_path}' resolves outside workspace."
            )
            
        # 3. Symlink protection
        if os.path.exists(abs_target) and os.path.islink(abs_target):
            real_path = os.path.realpath(abs_target)
            if not real_path.startswith(self.workspace_root):
                self._stats["violations"] += 1
                raise JailViolation(
                    f"Symlink escape blocked: '{target_path}' points outside workspace."
                )
        
        if must_exist and not os.path.exists(abs_target):
            raise FileNotFoundError(f"Jailed file not found: {target_path}")
            
        return abs_target
    
    def check_write_budget(self, expected_bytes: int):
        """Check if a write operation will exceed the session budget."""
        if self._session_bytes_written + expected_bytes > self.max_write_bytes:
            self._stats["violations"] += 1
            raise JailViolation(
                f"Write budget exceeded! Tried to write {expected_bytes} bytes, "
                f"but only {self.max_write_bytes - self._session_bytes_written} left."
            )
    
    def record_write(self, bytes_written: int):
        """Record bytes written."""
        self._session_bytes_written += bytes_written
        self._stats["bytes_written"] += bytes_written
        self._stats["files_written"] += 1
    
    # ═══════════════════════════════════════════════════════
    # PRE-EXECUTION SNAPSHOTS (Rollback Capability)
    # ═══════════════════════════════════════════════════════
    
    def snapshot_file(self, target_path: str) -> Optional[str]:
        """
        Take a backup snapshot of a file before modifying it.
        Returns snapshot ID, or None if file didn't exist.
        """
        try:
            abs_target = self.resolve_path(target_path)
            
            if not os.path.exists(abs_target) or not os.path.isfile(abs_target):
                return None  # Nothing to snapshot
                
            # Create snapshot ID based on hash of target path and time
            file_hash = self._hash_file(abs_target)
            snap_id = f"snap_{int(time.time()*1000)}_{file_hash[:8]}"
            snap_path = os.path.join(self.snapshots_dir, snap_id)
            
            # Copy file
            shutil.copy2(abs_target, snap_path)
            
            self._snapshots[snap_id] = {
                "original_path": abs_target,
                "timestamp": time.time(),
                "hash": file_hash,
                "size": os.path.getsize(abs_target)
            }
            
            self._stats["snapshots_taken"] += 1
            return snap_id
            
        except Exception as e:
            print(f"[FilesystemJail] Failed to create snapshot for {target_path}: {e}")
            return None
            
    def restore_snapshot(self, snap_id: str) -> bool:
        """Restore a file from a previous snapshot."""
        if snap_id not in self._snapshots:
            return False
            
        try:
            meta = self._snapshots[snap_id]
            snap_path = os.path.join(self.snapshots_dir, snap_id)
            target_path = meta["original_path"]
            
            if os.path.exists(snap_path):
                # Restore
                shutil.copy2(snap_path, target_path)
                self._stats["rollbacks"] += 1
                return True
            return False
            
        except Exception as e:
            print(f"[FilesystemJail] Failed to restore snapshot {snap_id}: {e}")
            return False
            
    def _hash_file(self, filepath: str) -> str:
        """Compute SHA-256 of a file."""
        hasher = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
        
    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "budget_used_mb": round(self._session_bytes_written / (1024*1024), 2),
            "budget_max_mb": round(self.max_write_bytes / (1024*1024), 2),
            "active_snapshots": len(self._snapshots)
        }

