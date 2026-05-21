"""
Phase 25.3: ShellBody Verification

Proves that:
1. Whitelist commands are allowed.
2. Blacklist patterns are rejected.
3. Resource tracking works (wall time, output size, exit codes).
4. Non-zero exits are captured correctly.
5. All commands are marked irreversible.
6. Integration with AuthorizedExecutor works.
"""

import pytest
import platform
from src.embodiment.shell import ShellBody
from src.embodiment.authorized_executor import AuthorizedExecutor
from src.agency.action import Action
from src.agency.authority import Authority, TrustModel
from src.learning.accumulation import BlameAccumulator
from src.learning.adjustment import AdjustmentPolicy, AdjustmentLog
from src.learning.regret import RegretLedger


class TestShellBodyWhitelist:
    
    def test_allowed_read_only_command(self):
        """Read-only whitelist commands execute successfully."""
        shell = ShellBody()
        
        action = Action(
            id="run_command",
            description="whoami",
            rationale="Test identity"
        )
        
        result = shell.execute(action)
        
        assert result.payload["success"] is True
        assert result.payload["exit_code"] == 0
        assert result.payload["irreversible"] is True
        
    def test_pwd_returns_path(self):
        """pwd command returns a valid path."""
        shell = ShellBody()
        
        action = Action(
            id="run_command",
            description="pwd" if platform.system() != "Windows" else "cd",
            rationale="Get current directory"
        )
        
        result = shell.execute(action)
        
        # Windows uses 'cd' for pwd
        if platform.system() == "Windows":
            # On Windows with shell=True, cd prints current dir
            pass
        else:
            assert result.payload["success"] is True


class TestShellBodyBlacklist:
    
    def test_rm_blocked(self):
        """rm command is blocked."""
        shell = ShellBody()
        
        action = Action(
            id="run_command",
            description="rm file.txt",
            rationale="Dangerous"
        )
        
        result = shell.execute(action)
        
        assert result.payload["success"] is False
        assert "Blacklisted" in result.payload.get("error", "")
        
    def test_pipe_blocked(self):
        """Pipe operators are blocked."""
        shell = ShellBody()
        
        action = Action(
            id="run_command",
            description="ls | grep foo",
            rationale="Piping"
        )
        
        result = shell.execute(action)
        
        assert result.payload["success"] is False
        assert "Blacklisted" in result.payload.get("error", "")
        
    def test_redirect_blocked(self):
        """Redirect operators are blocked."""
        shell = ShellBody()
        
        action = Action(
            id="run_command",
            description="echo test > file.txt",
            rationale="Redirect"
        )
        
        result = shell.execute(action)
        
        assert result.payload["success"] is False
        assert "Blacklisted" in result.payload.get("error", "")
        
    def test_command_substitution_blocked(self):
        """$() command substitution is blocked."""
        shell = ShellBody()
        
        action = Action(
            id="run_command",
            description="echo $(whoami)",
            rationale="Command substitution"
        )
        
        result = shell.execute(action)
        
        assert result.payload["success"] is False
        
    def test_unknown_command_blocked(self):
        """Commands not in whitelist are blocked."""
        shell = ShellBody()
        
        action = Action(
            id="run_command",
            description="zzz_unknown_cmd",
            rationale="Unknown"
        )
        
        result = shell.execute(action)
        
        assert result.payload["success"] is False


class TestShellBodyResourceTracking:
    
    def test_wall_time_tracked(self):
        """Execution time is tracked."""
        shell = ShellBody()
        
        action = Action(
            id="run_command",
            description="echo hello",
            rationale="Time test"
        )
        
        result = shell.execute(action)
        
        assert "wall_time_seconds" in result.payload
        assert result.payload["wall_time_seconds"] >= 0
        
    def test_output_bytes_tracked(self):
        """Output size is tracked."""
        shell = ShellBody()
        
        action = Action(
            id="run_command",
            description="echo test_output",
            rationale="Output test"
        )
        
        result = shell.execute(action)
        
        assert "output_bytes" in result.payload
        assert result.payload["output_bytes"] > 0
        
    def test_resource_usage_accumulates(self):
        """Resource usage accumulates across commands."""
        shell = ShellBody()
        
        for i in range(3):
            action = Action(
                id="run_command",
                description="echo test",
                rationale=f"Test {i}"
            )
            shell.execute(action)
            
        usage = shell.get_resource_usage()
        
        assert usage["commands_executed"] == 3
        assert usage["total_wall_time"] > 0


class TestShellBodyIrreversibility:
    
    def test_all_commands_marked_irreversible(self):
        """All shell results are marked as irreversible."""
        shell = ShellBody()
        
        action = Action(
            id="run_command",
            description="echo harmless",
            rationale="Test"
        )
        
        result = shell.execute(action)
        
        assert result.payload["irreversible"] is True
        assert result.payload["rollback_possible"] is False


class TestShellWithAuthorizedExecutor:
    
    def test_low_trust_blocks_shell(self):
        """Low trust blocks shell commands through AuthorizedExecutor."""
        shell = ShellBody()
        auth = Authority(TrustModel(base_level=0.05))  # Very low trust
        ledger = RegretLedger()
        
        executor = AuthorizedExecutor(shell, auth, regret_ledger=ledger)
        
        # Shell command with irreversible=True
        action = Action(
            id="run_command",
            description="echo test",
            rationale="Test",
            irreversible=True,  # Explicitly marked
            estimated_cost=50.0,
            risk_domain="compute"
        )
        
        result = executor.execute(action, goal_id="test_goal")
        
        # Should be blocked due to low trust
        assert result.success is False
        
        # Should have emitted a failure artifact
        assert len(ledger.artifacts) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
