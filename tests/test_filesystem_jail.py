"""
Real tests for filesystem_jail.py

CLAIM: The filesystem jail prevents path traversal and escaping the workspace.
PROOF: These tests verify path resolution, traversal blocking, and snapshot/restore.
"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.agent.security.filesystem_jail import FilesystemJail, JailViolation


class TestFilesystemJail:
    """Tests that the workspace confinement actually works."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.jail = FilesystemJail(workspace_root=self.tmpdir)

    def test_valid_path_resolves_inside_workspace(self):
        path = self.jail.resolve_path("myfile.txt")
        assert path.startswith(self.tmpdir)

    def test_path_traversal_is_blocked(self):
        """CRITICAL: ../../../etc/passwd must be blocked."""
        with pytest.raises(JailViolation):
            self.jail.resolve_path("../../../etc/passwd")

    def test_absolute_path_outside_workspace_is_blocked(self):
        """Absolute paths outside the workspace must be blocked."""
        with pytest.raises(JailViolation):
            self.jail.resolve_path("/etc/passwd")

    def test_nested_traversal_is_blocked(self):
        with pytest.raises(JailViolation):
            self.jail.resolve_path("subdir/../../outside.txt")

    def test_subdirectory_inside_workspace_is_allowed(self):
        path = self.jail.resolve_path("subdir/file.txt")
        assert path.startswith(self.tmpdir)

    def test_snapshot_and_restore(self):
        """
        CLAIM: The jail creates pre-execution snapshots so files can be restored.
        PROOF: Write a file, snapshot it, modify it, restore it — verify original content.
        """
        test_file = os.path.join(self.tmpdir, "important.txt")
        with open(test_file, "w") as f:
            f.write("original content")

        snapshot_id = self.jail.snapshot_file(test_file)
        assert snapshot_id is not None

        # Modify the file (simulates agent writing to it)
        with open(test_file, "w") as f:
            f.write("modified by agent")

        # Restore
        self.jail.restore_snapshot(snapshot_id)

        with open(test_file, "r") as f:
            content = f.read()

        assert content == "original content", "Snapshot restore failed"

    def test_workspace_directories_created_on_init(self):
        """Jail should create workspace and snapshots dirs automatically."""
        assert os.path.isdir(self.jail.workspace_root)
        assert os.path.isdir(self.jail.snapshots_dir)
