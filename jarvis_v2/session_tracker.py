"""
session_tracker.py — Code-Run-Fix Cycle Detection + Stuck Loop Detector.

Tracks ONLY the dev workflow loop:
  edit → run → error → fix → run

Not general "workflow detection" — only code-run-fix cycles.

Stuck loop: same error 3+ times in a session = escalate help.
"""
import time
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class SessionEvent:
    """One event in the coding session."""
    event_type: str  # "edit", "run", "error", "fix"
    detail: str      # file/command/error_class
    timestamp: float


class SessionTracker:
    """
    Tracks the code-run-fix cycle within a single coding session.
    
    Detects:
      - Error-fix cycles (run → error → fix → run)
      - Stuck loops (same error 3+ times)
      - Time-to-progress (no state change for 90s)
      - Session duration and productivity stats
    """
    
    STUCK_THRESHOLD = 3  # Same error class N times = stuck
    STALE_TIMEOUT = 90   # Seconds without progress = stuck
    
    def __init__(self):
        self._events: List[SessionEvent] = []
        self._error_counts: Dict[str, int] = {}  # error_class → count this session
        self._last_state_change: float = time.time()
        self._session_start: float = time.time()
        self._cycles_completed: int = 0
        self._current_error: Optional[str] = None
        self._was_fixing: bool = False
    
    def record_edit(self, file_path: str):
        """User edited a file."""
        self._events.append(SessionEvent("edit", file_path, time.time()))
        self._last_state_change = time.time()
        
        # If we had an error and user edited, that's a fix attempt
        if self._current_error:
            self._events.append(SessionEvent("fix", self._current_error, time.time()))
            self._current_error = None
            self._was_fixing = True
    
    def record_run(self, command: str):
        """User ran a command (python, pytest, etc)."""
        self._events.append(SessionEvent("run", command, time.time()))
        self._last_state_change = time.time()
    
    def record_error(self, error_class: str) -> Optional[str]:
        """
        Record an error in the session.
        
        Returns stuck signal if same error class hit STUCK_THRESHOLD times.
        """
        self._events.append(SessionEvent("error", error_class, time.time()))
        self._current_error = error_class
        self._error_counts[error_class] = self._error_counts.get(error_class, 0) + 1
        
        # Stuck detection
        if self._error_counts[error_class] >= self.STUCK_THRESHOLD:
            return "stuck_loop"
        
        return None
    
    def record_success(self, command: str):
        """Command ran without error."""
        self._events.append(SessionEvent("run", command, time.time()))
        self._last_state_change = time.time()
        
        if self._current_error or self._was_fixing:
            self._cycles_completed += 1
            self._current_error = None
            self._was_fixing = False
    
    def check_stale(self) -> bool:
        """Is the user stuck (no state change for STALE_TIMEOUT seconds)?"""
        return (time.time() - self._last_state_change) > self.STALE_TIMEOUT
    
    def get_stuck_errors(self) -> List[Dict]:
        """Get error classes that have hit stuck threshold."""
        return [
            {"error_class": cls, "count": count}
            for cls, count in self._error_counts.items()
            if count >= self.STUCK_THRESHOLD
        ]
    
    def get_current_cycle(self) -> Optional[str]:
        """What phase of the code-run-fix cycle are we in?"""
        if not self._events:
            return None
        
        # Look at last 3 events to determine phase
        recent = self._events[-3:]
        types = [e.event_type for e in recent]
        
        if self._current_error:
            return "fixing"  # Error happened, user should be fixing
        
        if types and types[-1] == "edit":
            return "editing"
        
        if types and types[-1] == "run":
            return "running"
        
        return "idle"
    
    def get_session_stats(self) -> Dict:
        """Session productivity stats."""
        duration = time.time() - self._session_start
        total_errors = sum(self._error_counts.values())
        
        return {
            "duration_minutes": round(duration / 60, 1),
            "total_events": len(self._events),
            "total_errors": total_errors,
            "unique_error_classes": len(self._error_counts),
            "cycles_completed": self._cycles_completed,
            "stuck_errors": self.get_stuck_errors(),
            "current_phase": self.get_current_cycle(),
            "seconds_since_progress": round(time.time() - self._last_state_change, 1),
        }
    
    def get_flow_summary(self) -> str:
        """Human-readable session flow."""
        if not self._events:
            return "No activity yet."
        
        # Condense consecutive same-type events
        flow = []
        for event in self._events[-12:]:
            label = f"{event.event_type}({event.detail[:30]})"
            if not flow or flow[-1] != label:
                flow.append(label)
        
        return " → ".join(flow[-8:])
    
    def reset(self):
        """Start a new session."""
        self._events.clear()
        self._error_counts.clear()
        self._last_state_change = time.time()
        self._session_start = time.time()
        self._cycles_completed = 0
        self._current_error = None
        self._was_fixing = False
