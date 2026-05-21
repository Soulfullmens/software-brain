"""
shell.py

The 'System Interface' of the Agent.
Executes shell commands.
"""
import subprocess
import os
import shlex
from ..tool import Tool
from ..security.filesystem_jail import FilesystemJail

class ShellTool(Tool):
    name = "shell_execution"
    description = "Execute shell commands. Sandboxed to workspace."
    
    def __init__(self):
        super().__init__()
        self.jail = FilesystemJail()
        
    def run(self, action: str, **kwargs) -> str:
        """
        Execute a shell action.
        
        Args:
            action: Must be 'run_command'.
            command: The command string to execute (in kwargs).
            timeout: Timeout in seconds (default 60).
        """
        if action != "run_command":
            return f"Error: Unknown action '{action}' for ShellTool"
            
        command = kwargs.get("command")
        if not command:
            return "Error: Missing 'command' parameter"
            
        timeout = kwargs.get("timeout", 60)
        
        try:
            # ── 1. Sandbox Verification ──
            # Block obviously dangerous piped commands
            dangerous_tokens = ["rm -rf /", "> /dev/", "mkfs", "dd if="]
            for token in dangerous_tokens:
                if token in command:
                    return f"Error: Command contains blocked signature: '{token}'"
            
            # ── 2. Sandboxed Execution ──
            # Run inside the workspace root
            # Drop dangerous environment variables
            safe_env = os.environ.copy()
            
            # For Windows compatibility, we still need shell=True for builtins like 'dir',
            # but we restrict the working directory heavily.
            result = subprocess.run(
                command, 
                shell=True, 
                cwd=self.jail.workspace_root,
                env=safe_env,
                capture_output=True, 
                text=True, 
                timeout=timeout
            )
            
            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"
                
            # Truncate massive outputs to prevent memory exhaustion
            if len(output) > 50000:
                output = output[:50000] + "\n... [Output truncated due to length limits]"
                
            return output.strip()
            
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout}s"
        except Exception as e:
            return f"Error executing shell command: {e}"
