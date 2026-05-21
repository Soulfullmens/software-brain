"""
Verification Loop Tool — Ensuring 100% Technical Accuracy.

Implements a multi-step "Red/Green/Refactor" cycle for mission-critical tasks.
Tracks session state across init → check(s) → validate so the agent can run
multiple verification commands and get a final certificate.
"""

import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..tool import Tool, ToolResult


# ────────────────────────────────────────────────────────
#  Verification Session State
# ────────────────────────────────────────────────────────

@dataclass
class CheckRecord:
    command: str
    passed: bool
    output: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class VerificationSession:
    goal: str
    checks: List[CheckRecord] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    validated: bool = False

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks) and len(self.checks) > 0

    @property
    def pass_rate(self) -> str:
        if not self.checks:
            return "0/0"
        passed = sum(1 for c in self.checks if c.passed)
        return f"{passed}/{len(self.checks)}"


# ────────────────────────────────────────────────────────
#  Verification Loop Tool
# ────────────────────────────────────────────────────────

class VerificationLoop(Tool):
    """
    Multi-turn verification tool:
      1. init   — define what success looks like
      2. check  — run one or more shell commands / tests
      3. validate — issue a Technical Certificate
    """

    # Safety: max commands per session, max command runtime
    MAX_CHECKS = 20
    COMMAND_TIMEOUT = 60  # seconds

    def __init__(self):
        super().__init__(
            name="verification_loop",
            description=(
                "Run a multi-turn technical verification loop "
                "(Red/Green/Refactor). Use for mission-critical code, "
                "engineering designs, or security checks."
            ),
        )
        self._sessions: Dict[str, VerificationSession] = {}
        self._current_session_id: Optional[str] = None

    # ── Actions ──────────────────────────────────────

    def run(self, action: str, **kwargs) -> ToolResult:
        """
        Actions:
          init     — Start a new verification context.
          check    — Run a verification command.
          validate — Finalize and issue a Technical Certificate.
          status   — Return current session state.
        """
        action = action.lower()
        dispatch = {
            "init": self._action_init,
            "check": self._action_check,
            "validate": self._action_validate,
            "status": self._action_status,
        }
        handler = dispatch.get(action)
        if handler is None:
            return ToolResult(
                success=False,
                error=f"Unknown action '{action}'. Valid: {list(dispatch)}",
            )
        return handler(**kwargs)

    # ── Init ─────────────────────────────────────────

    def _action_init(self, **kwargs) -> ToolResult:
        goal = kwargs.get("goal", "Generic Verification")
        session_id = f"vs_{int(time.time())}_{hash(goal) % 10000:04d}"
        session = VerificationSession(goal=goal)
        self._sessions[session_id] = session
        self._current_session_id = session_id
        return ToolResult(
            success=True,
            output=f"✅ Verification session [{session_id}] initialized for: {goal}",
            metadata={"session_id": session_id, "goal": goal},
        )

    # ── Check ────────────────────────────────────────

    def _action_check(self, **kwargs) -> ToolResult:
        session = self._get_current_session()
        if session is None:
            return ToolResult(success=False, error="No active session. Call 'init' first.")

        command = kwargs.get("command")
        if not command:
            return ToolResult(success=False, error="No 'command' provided for check.")

        if len(session.checks) >= self.MAX_CHECKS:
            return ToolResult(
                success=False,
                error=f"Max checks ({self.MAX_CHECKS}) reached for this session.",
            )

        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=self.COMMAND_TIMEOUT,
            )
            passed = result.returncode == 0
            output = result.stdout.strip() or result.stderr.strip()
            record = CheckRecord(command=command, passed=passed, output=output)
            session.checks.append(record)

            if passed:
                return ToolResult(
                    success=True,
                    output=f"✅ CHECK PASSED ({session.pass_rate}):\n{output[:2000]}",
                    metadata={"passed": True, "check_index": len(session.checks)},
                )
            else:
                return ToolResult(
                    success=False,
                    output=f"❌ CHECK FAILED (RC={result.returncode}) ({session.pass_rate}):\n{result.stderr[:1000]}\n{result.stdout[:1000]}",
                    metadata={"passed": False, "return_code": result.returncode},
                )

        except subprocess.TimeoutExpired:
            record = CheckRecord(command=command, passed=False, output="TIMEOUT")
            session.checks.append(record)
            return ToolResult(success=False, error=f"Command timed out ({self.COMMAND_TIMEOUT}s): {command}")

        except Exception as e:
            record = CheckRecord(command=command, passed=False, output=str(e))
            session.checks.append(record)
            return ToolResult(success=False, error=str(e))

    # ── Validate ─────────────────────────────────────

    def _action_validate(self, **kwargs) -> ToolResult:
        session = self._get_current_session()
        if session is None:
            return ToolResult(success=False, error="No active session. Call 'init' first.")

        session.validated = True
        elapsed = time.time() - session.started_at
        status = "PASS" if session.all_passed else "FAIL"

        certificate = (
            f"═══ TECHNICAL CERTIFICATE ═══\n"
            f"  Goal       : {session.goal}\n"
            f"  Status     : {status}\n"
            f"  Checks     : {session.pass_rate}\n"
            f"  Duration   : {elapsed:.1f}s\n"
            f"  Issued     : {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"═════════════════════════════"
        )

        return ToolResult(
            success=session.all_passed,
            output=certificate,
            metadata={
                "status": status,
                "pass_rate": session.pass_rate,
                "duration_s": round(elapsed, 1),
                "checks": [
                    {"cmd": c.command, "passed": c.passed} for c in session.checks
                ],
            },
        )

    # ── Status ───────────────────────────────────────

    def _action_status(self, **kwargs) -> ToolResult:
        session = self._get_current_session()
        if session is None:
            return ToolResult(
                success=True,
                output="No active verification session.",
                metadata={"active_sessions": len(self._sessions)},
            )
        return ToolResult(
            success=True,
            output=f"Session for '{session.goal}' — {session.pass_rate} checks completed.",
            metadata={
                "goal": session.goal,
                "pass_rate": session.pass_rate,
                "validated": session.validated,
            },
        )

    # ── Helpers ──────────────────────────────────────

    def _get_current_session(self) -> Optional[VerificationSession]:
        if self._current_session_id:
            return self._sessions.get(self._current_session_id)
        return None

    def get_schema(self) -> Dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["init", "check", "validate", "status"],
                    "description": "The verification action to perform.",
                },
                "goal": {
                    "type": "string",
                    "description": "What are we verifying? (used with 'init')",
                },
                "command": {
                    "type": "string",
                    "description": "Shell command to run for verification (used with 'check').",
                },
            },
            "required": ["action"],
        }
