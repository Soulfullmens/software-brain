"""
Phase 25.2: Rollback / Shadow State Verification

Proves that:
1. Write operations create shadow backups of overwritten files.
2. Delete operations move files to .trash/ instead of permanent deletion.
3. Files can be restored from trash.
4. Rollback_possible is correctly reported in events.
"""

import pytest
from pathlib import Path
from src.embodiment.filesystem import FilesystemBody
from src.agency.action import Action


@pytest.fixture
def sandbox(tmp_path):
    """Create a temporary sandbox directory."""
    sandbox_dir = tmp_path / "agent_sandbox"
    sandbox_dir.mkdir()
    yield sandbox_dir


@pytest.fixture
def body(sandbox):
    """Create a filesystem body with the sandbox."""
    return FilesystemBody(sandbox_root=sandbox)


class TestRollbackSemantics:
    
    def test_shadow_write_on_overwrite(self, body, sandbox):
        """
        Scenario: Overwriting an existing file.
        Result: Shadow backup is created.
        """
        # Create original file
        original_content = "Original valuable content"
        (sandbox / "valuable.txt").write_text(original_content)
        
        # Overwrite with new content
        write_action = Action(
            id="write_file",
            description="New content replacing old",
            rationale="Testing shadow",
            target="valuable.txt",
            irreversible=True
        )
        result = body.execute(write_action)
        
        assert result.payload["success"] is True
        assert result.payload["rollback_possible"] is True
        assert result.payload["shadow_path"] is not None
        
        # Verify shadow exists
        shadow_dir = sandbox / ".shadow"
        assert shadow_dir.exists()
        
        # Find the shadow file
        shadow_files = list(shadow_dir.glob("valuable.txt.*.bak"))
        assert len(shadow_files) == 1
        
        # Verify shadow contains original content
        assert shadow_files[0].read_text() == original_content
        
    def test_no_shadow_for_new_file(self, body, sandbox):
        """
        Scenario: Writing a new file (not overwrite).
        Result: No shadow (nothing to backup).
        """
        write_action = Action(
            id="write_file",
            description="Brand new content",
            rationale="Creating new file",
            target="brand_new.txt"
        )
        result = body.execute(write_action)
        
        assert result.payload["success"] is True
        assert result.payload["rollback_possible"] is False
        assert result.payload["shadow_path"] is None
        
    def test_soft_delete_to_trash(self, body, sandbox):
        """
        Scenario: Deleting a file.
        Result: File moved to .trash/, not permanently deleted.
        """
        # Create file to delete
        (sandbox / "delete_me.txt").write_text("I will be trashed")
        
        delete_action = Action(
            id="delete_file",
            description="",
            rationale="Testing soft delete",
            target="delete_me.txt",
            irreversible=True
        )
        result = body.execute(delete_action)
        
        assert result.payload["success"] is True
        assert result.payload["rollback_possible"] is True
        assert result.payload["trash_path"] is not None
        
        # Original should be gone
        assert not (sandbox / "delete_me.txt").exists()
        
        # Trash should have the file
        trash_dir = sandbox / ".trash"
        assert trash_dir.exists()
        
        # Find trash entries
        entries = body.get_trash_entries()
        assert len(entries) == 1
        assert entries[0]["original_path"] == "delete_me.txt"
        
    def test_restore_from_trash(self, body, sandbox):
        """
        Scenario: Restore a deleted file.
        Result: File returns to original location.
        """
        # Create and delete
        (sandbox / "restore_me.txt").write_text("Please restore me")
        
        delete_action = Action(
            id="delete_file",
            description="",
            rationale="Will restore later",
            target="restore_me.txt"
        )
        body.execute(delete_action)
        
        # Get trash entry name
        entries = body.get_trash_entries()
        assert len(entries) == 1
        trash_entry_name = entries[0]["trash_entry"]
        
        # Restore
        success = body.restore_from_trash(trash_entry_name)
        
        assert success is True
        
        # File should be back
        assert (sandbox / "restore_me.txt").exists()
        assert (sandbox / "restore_me.txt").read_text() == "Please restore me"
        
        # Trash should be empty
        entries_after = body.get_trash_entries()
        assert len(entries_after) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
