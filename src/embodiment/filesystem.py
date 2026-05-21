"""
Filesystem Body - The First Real Body

A restricted adapter that can read/write/delete files within a sandboxed directory.
This body has REAL CONSEQUENCES.

Actions:
- read_file: Read file contents
- write_file: Create or overwrite file
- delete_file: Remove file
- list_dir: List directory contents
- file_exists: Check if file exists

ALL operations are restricted to a sandbox directory.
Any attempt to escape is blocked.
"""

from typing import Set, Optional
from datetime import datetime
from pathlib import Path
import os

from src.embodiment.base import Embodiment
from src.agency.action import Action
from src.perception.input_event import InputEvent


class FilesystemBody(Embodiment):
    """
    A body that can manipulate files in a sandboxed directory.
    
    This is where the agent learns that actions have consequences.
    """
    
    def __init__(self, sandbox_root: Path, body_id: str = "filesystem_v0"):
        """
        Initialize with a sandbox directory.
        
        Args:
            sandbox_root: The ONLY directory where operations are allowed.
            body_id: Unique ID for this body instance.
        """
        self._id = body_id
        self._sandbox = sandbox_root.resolve()
        
        # Ensure sandbox exists
        self._sandbox.mkdir(parents=True, exist_ok=True)
        
        self._capabilities = {
            "read_file",
            "write_file",
            "delete_file",
            "list_dir",
            "file_exists"
        }
        
        # Resource accounting
        self.operations_count = 0
        self.bytes_written = 0
        self.bytes_read = 0
        self.files_deleted = 0
        
    @property
    def embodiment_id(self) -> str:
        return self._id
        
    @property
    def capabilities(self) -> Set[str]:
        return self._capabilities
        
    @property
    def sandbox_path(self) -> Path:
        return self._sandbox
        
    def _validate_path(self, target: str) -> Optional[Path]:
        """
        Validate that the target path is within the sandbox.
        Returns resolved Path if valid, None if escape attempt.
        """
        if not target:
            return None
            
        # Resolve the target relative to sandbox
        try:
            target_path = (self._sandbox / target).resolve()
        except Exception:
            return None
            
        # Check if still within sandbox
        try:
            target_path.relative_to(self._sandbox)
            return target_path
        except ValueError:
            # Escape attempt!
            return None
            
    def can_execute(self, action: Action) -> bool:
        return action.id in self._capabilities
        
    def execute(self, action: Action) -> Optional[InputEvent]:
        """
        Execute the action.
        
        Returns:
            InputEvent with result or error.
        """
        self.operations_count += 1
        
        if action.id == "read_file":
            return self._read_file(action)
        elif action.id == "write_file":
            return self._write_file(action)
        elif action.id == "delete_file":
            return self._delete_file(action)
        elif action.id == "list_dir":
            return self._list_dir(action)
        elif action.id == "file_exists":
            return self._file_exists(action)
        else:
            return self._error_event(f"Unknown action: {action.id}")
            
    def _read_file(self, action: Action) -> InputEvent:
        path = self._validate_path(action.target)
        if not path:
            return self._error_event("Path validation failed (possible sandbox escape)")
            
        if not path.exists():
            return self._error_event(f"File not found: {action.target}")
            
        if not path.is_file():
            return self._error_event(f"Not a file: {action.target}")
            
        try:
            content = path.read_text(encoding="utf-8")
            self.bytes_read += len(content)
            
            return InputEvent(
                source=self._id,
                modality="text",
                timestamp=datetime.now(),
                payload={
                    "type": "file_content",
                    "target_id": action.target,
                    "content": content,
                    "size_bytes": len(content),
                    "success": True
                }
            )
        except Exception as e:
            return self._error_event(f"Read failed: {str(e)}")
            
    def _write_file(self, action: Action) -> InputEvent:
        path = self._validate_path(action.target)
        if not path:
            return self._error_event("Path validation failed (possible sandbox escape)")
            
        # Get content from action description (or a dedicated field)
        content = action.description
        
        try:
            # Create parent directories if needed
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Phase 25.2: Shadow Write (backup before overwrite)
            shadow_path = None
            if path.exists():
                shadow_path = self._create_shadow(path, action)
            
            path.write_text(content, encoding="utf-8")
            self.bytes_written += len(content)
            
            return InputEvent(
                source=self._id,
                modality="text",
                timestamp=datetime.now(),
                payload={
                    "type": "file_written",
                    "target_id": action.target,
                    "size_bytes": len(content),
                    "shadow_path": str(shadow_path) if shadow_path else None,
                    "rollback_possible": shadow_path is not None,
                    "success": True
                }
            )
        except Exception as e:
            return self._error_event(f"Write failed: {str(e)}")
            
    def _delete_file(self, action: Action) -> InputEvent:
        path = self._validate_path(action.target)
        if not path:
            return self._error_event("Path validation failed (possible sandbox escape)")
            
        if not path.exists():
            return self._error_event(f"File not found: {action.target}")
            
        try:
            # Phase 25.2: Soft Delete (move to trash instead of unlink)
            trash_path = self._move_to_trash(path, action)
            
            self.files_deleted += 1
            
            return InputEvent(
                source=self._id,
                modality="text",
                timestamp=datetime.now(),
                payload={
                    "type": "file_deleted",
                    "target_id": action.target,
                    "trash_path": str(trash_path) if trash_path else None,
                    "rollback_possible": trash_path is not None,
                    "success": True
                }
            )
        except Exception as e:
            return self._error_event(f"Delete failed: {str(e)}")
            
    def _list_dir(self, action: Action) -> InputEvent:
        path = self._validate_path(action.target or ".")
        if not path:
            return self._error_event("Path validation failed")
            
        if not path.exists():
            return self._error_event(f"Directory not found: {action.target}")
            
        if not path.is_dir():
            return self._error_event(f"Not a directory: {action.target}")
            
        try:
            entries = []
            for entry in path.iterdir():
                entries.append({
                    "name": entry.name,
                    "is_dir": entry.is_dir(),
                    "size": entry.stat().st_size if entry.is_file() else 0
                })
                
            return InputEvent(
                source=self._id,
                modality="text",
                timestamp=datetime.now(),
                payload={
                    "type": "directory_listing",
                    "target_id": action.target or ".",
                    "entries": entries,
                    "count": len(entries),
                    "success": True
                }
            )
        except Exception as e:
            return self._error_event(f"List failed: {str(e)}")
            
    def _file_exists(self, action: Action) -> InputEvent:
        path = self._validate_path(action.target)
        if not path:
            return self._error_event("Path validation failed")
            
        exists = path.exists()
        
        return InputEvent(
            source=self._id,
            modality="text",
            timestamp=datetime.now(),
            payload={
                "type": "file_exists",
                "target_id": action.target,
                "exists": exists,
                "success": True
            }
        )
        
    def _error_event(self, message: str) -> InputEvent:
        return InputEvent(
            source=self._id,
            modality="text",
            timestamp=datetime.now(),
            payload={
                "type": "error",
                "content": message,
                "success": False
            }
        )
        
    def get_resource_usage(self) -> dict:
        """Return resource accounting summary."""
        return {
            "operations": self.operations_count,
            "bytes_written": self.bytes_written,
            "bytes_read": self.bytes_read,
            "files_deleted": self.files_deleted
        }
        
    # ==================== Phase 25.2: Rollback Semantics ====================
    
    def _create_shadow(self, path: Path, action: Action) -> Optional[Path]:
        """
        Create a shadow backup before overwriting a file.
        
        Shadow files are stored in .shadow/ with metadata.
        """
        import hashlib
        import json
        
        shadow_dir = self._sandbox / ".shadow"
        shadow_dir.mkdir(exist_ok=True)
        
        # Create unique shadow filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        content_hash = hashlib.md5(path.read_bytes()).hexdigest()[:8]
        shadow_filename = f"{path.name}.{timestamp}.{content_hash}.bak"
        
        shadow_path = shadow_dir / shadow_filename
        
        try:
            # Copy file content
            import shutil
            shutil.copy2(path, shadow_path)
            
            # Write metadata
            metadata = {
                "original_path": str(path.relative_to(self._sandbox)),
                "action_id": action.id,
                "rationale": action.rationale,
                "timestamp": datetime.now().isoformat(),
                "size_bytes": path.stat().st_size
            }
            metadata_path = shadow_path.with_suffix(".meta.json")
            metadata_path.write_text(json.dumps(metadata, indent=2))
            
            return shadow_path
        except Exception:
            return None
            
    def _move_to_trash(self, path: Path, action: Action) -> Optional[Path]:
        """
        Move file to trash instead of deleting permanently.
        
        Trash files can be restored. Trash has cost.
        """
        import uuid
        import json
        
        trash_dir = self._sandbox / ".trash"
        trash_dir.mkdir(exist_ok=True)
        
        # Create unique trash entry
        trash_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Preserve directory structure under trash
        relative_path = path.relative_to(self._sandbox)
        trash_entry_dir = trash_dir / f"{timestamp}_{trash_id}"
        trash_entry_dir.mkdir()
        
        trash_path = trash_entry_dir / relative_path.name
        
        try:
            import shutil
            
            if path.is_file():
                shutil.move(str(path), str(trash_path))
            elif path.is_dir():
                shutil.move(str(path), str(trash_path))
                
            # Write metadata
            metadata = {
                "original_path": str(relative_path),
                "action_id": action.id,
                "rationale": action.rationale,
                "timestamp": datetime.now().isoformat(),
                "is_dir": path.is_dir()
            }
            metadata_path = trash_entry_dir / "meta.json"
            metadata_path.write_text(json.dumps(metadata, indent=2))
            
            return trash_path
        except Exception:
            return None
            
    def restore_from_trash(self, trash_entry_name: str) -> bool:
        """
        Restore a file from trash to its original location.
        
        This is the agent learning to undo.
        """
        import json
        import shutil
        
        trash_dir = self._sandbox / ".trash"
        trash_entry = trash_dir / trash_entry_name
        
        if not trash_entry.exists():
            return False
            
        # Read metadata
        metadata_path = trash_entry / "meta.json"
        if not metadata_path.exists():
            return False
            
        try:
            metadata = json.loads(metadata_path.read_text())
            original_path = self._sandbox / metadata["original_path"]
            
            # Find the actual trashed file (first non-meta file in entry)
            for item in trash_entry.iterdir():
                if item.name != "meta.json":
                    # Ensure parent exists
                    original_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(item), str(original_path))
                    break
                    
            # Clean up trash entry
            shutil.rmtree(trash_entry)
            
            return True
        except Exception:
            return False
            
    def get_trash_entries(self) -> list:
        """List all trash entries with metadata."""
        import json
        
        trash_dir = self._sandbox / ".trash"
        if not trash_dir.exists():
            return []
            
        entries = []
        for entry in trash_dir.iterdir():
            if entry.is_dir():
                meta_path = entry / "meta.json"
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text())
                        entries.append({
                            "trash_entry": entry.name,
                            **meta
                        })
                    except Exception:
                        pass
                        
        return entries

