"""
Phase 25: Embodiment Verification

Proves that:
1. FilesystemBody can read/write/delete files within sandbox.
2. Path escape attempts are blocked.
3. Resource accounting works.
4. Errors are returned properly.
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


class TestFilesystemBody:
    
    def test_write_and_read(self, body, sandbox):
        """Basic write/read cycle."""
        # Write
        write_action = Action(
            id="write_file",
            description="Hello, World!",
            rationale="Testing write",
            target="test.txt"
        )
        result = body.execute(write_action)
        
        assert result.payload["success"] is True
        assert result.payload["type"] == "file_written"
        
        # Read
        read_action = Action(
            id="read_file",
            description="",
            rationale="Testing read",
            target="test.txt"
        )
        result = body.execute(read_action)
        
        assert result.payload["success"] is True
        assert result.payload["content"] == "Hello, World!"
        
    def test_delete_file(self, body, sandbox):
        """Delete a file."""
        # Create file first
        (sandbox / "to_delete.txt").write_text("delete me")
        
        delete_action = Action(
            id="delete_file",
            description="",
            rationale="Testing delete",
            target="to_delete.txt"
        )
        result = body.execute(delete_action)
        
        assert result.payload["success"] is True
        assert not (sandbox / "to_delete.txt").exists()
        
    def test_list_dir(self, body, sandbox):
        """List directory contents."""
        # Create some files
        (sandbox / "file1.txt").write_text("a")
        (sandbox / "file2.txt").write_text("b")
        (sandbox / "subdir").mkdir()
        
        list_action = Action(
            id="list_dir",
            description="",
            rationale="Testing list",
            target="."
        )
        result = body.execute(list_action)
        
        assert result.payload["success"] is True
        assert result.payload["count"] == 3
        
    def test_sandbox_escape_blocked(self, body, sandbox):
        """Attempt to escape sandbox is blocked."""
        # Try to read parent directory
        escape_action = Action(
            id="read_file",
            description="",
            rationale="MALICIOUS",
            target="../../../etc/passwd"
        )
        result = body.execute(escape_action)
        
        assert result.payload["success"] is False
        assert "sandbox escape" in result.payload["content"].lower()
        
    def test_resource_accounting(self, body, sandbox):
        """Resource usage is tracked."""
        # Write
        write_action = Action(
            id="write_file",
            description="12345",  # 5 bytes
            rationale="",
            target="accounting_test.txt"
        )
        body.execute(write_action)
        
        # Read
        read_action = Action(
            id="read_file",
            description="",
            rationale="",
            target="accounting_test.txt"
        )
        body.execute(read_action)
        
        # Delete
        delete_action = Action(
            id="delete_file",
            description="",
            rationale="",
            target="accounting_test.txt"
        )
        body.execute(delete_action)
        
        usage = body.get_resource_usage()
        
        assert usage["operations"] == 3
        assert usage["bytes_written"] == 5
        assert usage["bytes_read"] == 5
        assert usage["files_deleted"] == 1
        
    def test_file_not_found(self, body, sandbox):
        """Proper error on missing file."""
        read_action = Action(
            id="read_file",
            description="",
            rationale="",
            target="nonexistent.txt"
        )
        result = body.execute(read_action)
        
        assert result.payload["success"] is False
        assert "not found" in result.payload["content"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
