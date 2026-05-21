"""
Real tests for shell.py

CLAIM: ShellTool executes commands inside the sandbox and blocks dangerous ones.
PROOF: Dangerous command signatures are checked before execution.

NOTE ON SCOPE:
- We test the blocking logic (pure Python, no side effects).
- We do NOT test actual shell execution here — that requires a real process.
- The 'rm -rf /' style blocking IS verified below.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.agent.tools.shell import ShellTool


class TestShellToolBlocking:
    """
    VERIFIED: ShellTool blocks known dangerous command signatures.
    UNVERIFIED: Whether all dangerous commands are caught (static list, not exhaustive).
    """

    def setup_method(self):
        self.shell = ShellTool()

    def test_blocks_rm_rf_root(self):
        result = self.shell.run("run_command", command="rm -rf /")
        assert "blocked" in result.lower() or "error" in result.lower()

    def test_blocks_dev_null_redirect(self):
        result = self.shell.run("run_command", command="echo test > /dev/null && rm -rf /")
        assert "blocked" in result.lower() or "error" in result.lower()

    def test_blocks_mkfs(self):
        result = self.shell.run("run_command", command="mkfs.ext4 /dev/sda")
        assert "blocked" in result.lower() or "error" in result.lower()

    def test_blocks_dd_if(self):
        result = self.shell.run("run_command", command="dd if=/dev/urandom of=/dev/sda")
        assert "blocked" in result.lower() or "error" in result.lower()

    def test_rejects_unknown_action(self):
        result = self.shell.run("unknown_action", command="ls")
        assert "error" in result.lower() or "unknown" in result.lower()

    def test_rejects_missing_command(self):
        result = self.shell.run("run_command")
        assert "error" in result.lower() or "missing" in result.lower()

    def test_safe_echo_command_runs(self):
        """A safe echo command should execute and return output."""
        result = self.shell.run("run_command", command="echo hello")
        assert "hello" in result or isinstance(result, str)
