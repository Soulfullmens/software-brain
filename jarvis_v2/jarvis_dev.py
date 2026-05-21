"""
jarvis_dev.py — Jarvis V2 Developer Co-Pilot.

The main orchestrator. Watches terminal output, scans code before runs,
fires preemptive warnings through the interrupt policy.

This is the PRODUCT. Everything else exists to serve this file.

Core loop:
  You code → Jarvis scans for risk → Warns BEFORE run → You fix → Run succeeds

Usage:
    pilot = JarvisDev()
    
    # Pre-run check (THE addictive feature)
    warnings = pilot.check_before_run("python main.py", "main.py")
    
    # Record error when run fails
    pilot.record_error(traceback_text, "main.py", "python main.py")
    
    # Record success
    pilot.record_success("python main.py")
"""
import os, time, json
from typing import Dict, List, Optional
from datetime import datetime

from .pattern_library import PATTERNS, match_traceback, scan_code_for_risks
from .error_memory import ErrorMemory, ErrorEntry
from .interrupt_policy import InterruptPolicy, InterruptDecision
from .session_tracker import SessionTracker
from .llm_bridge import LLMBridge


EXPERIMENT_FILE = os.path.join(
    os.path.expanduser("~"), ".jarvis", "experiment.jsonl"
)


class JarvisDev:
    """
    Developer Workflow Co-Pilot.
    
    Python. VS Code. Nothing else.
    
    Makes you faster by preventing errors you've already hit,
    and warning about patterns that usually fail.
    """
    
    def __init__(self, memory_file: str = None, experiment_file: str = None):
        self.memory = ErrorMemory(memory_file=memory_file)
        self.policy = InterruptPolicy()
        self.session = SessionTracker()
        self.llm = LLMBridge()
        
        self._session_id = f"s_{int(time.time())}"
        self._warnings_shown: List[Dict] = []
        self._last_check_file: str = ""
        self._experiment_file = experiment_file or EXPERIMENT_FILE
        self._prevented_failures: int = 0  # THE core metric
        self._last_warned_classes: set = set()  # Track what we warned about
    
    # ═════════════════════════════════════
    # THE CORE FEATURE: PRE-RUN CHECK
    # ═════════════════════════════════════
    
    def check_before_run(self, command: str, file_path: str = "",
                         code_text: str = None) -> List[Dict]:
        """
        CHECK BEFORE RUNNING. This is the addictive feature.
        
        Scans the file for risk patterns + checks against error history.
        Returns list of warnings that pass the interrupt policy.
        
        Args:
            command: what the user is about to run ("python main.py")
            file_path: which file (for history matching)
            code_text: file contents (auto-read if not provided)
        
        Returns: List of approved warnings [{message, confidence, severity, is_soft}]
        """
        self.session.record_run(command)
        
        # Read file if not provided
        if code_text is None and file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    code_text = f.read()
            except Exception:
                code_text = ""
        
        if not code_text:
            return []
        
        self._last_check_file = file_path
        
        # Get all risks (pattern + history)
        risks = self.memory.check_risks(code_text, file_path)
        
        # Filter through interrupt policy
        approved = []
        for risk in risks:
            decision = self.policy.check(
                confidence=risk["confidence"],
                severity_seconds=risk["severity"]
            )
            
            if decision.should_interrupt:
                warning = {
                    "message": risk["message"],
                    "error_class": risk["error_class"],
                    "confidence": risk["confidence"],
                    "confidence_reason": risk.get("confidence_reason", ""),
                    "severity": risk["severity"],
                    "line_hint": risk.get("line_hint"),
                    "source": risk["source"],
                    "is_history": risk.get("is_history", False),
                    "type": "warning",
                }
                approved.append(warning)
                self.policy.record_interrupt()
            
            elif decision.is_soft:
                soft = {
                    "message": f"🤔 {decision.reason}",
                    "error_class": risk["error_class"],
                    "confidence": risk["confidence"],
                    "confidence_reason": risk.get("confidence_reason", ""),
                    "severity": risk["severity"],
                    "line_hint": risk.get("line_hint"),
                    "source": risk["source"],
                    "is_history": risk.get("is_history", False),
                    "type": "hint",
                }
                approved.append(soft)
        
        self._warnings_shown = approved
        self._last_warned_classes = {w["error_class"] for w in approved}
        return approved
    
    # ═════════════════════════════════════
    # ERROR RECORDING
    # ═════════════════════════════════════
    
    def record_error(self, traceback_text: str, file_path: str = "",
                     command: str = "", code_snippet: str = "") -> Dict:
        """
        Record a runtime error. Auto-classifies and checks for stuck loops.
        
        Returns: {error_class, is_repeat, times_seen, stuck, explain}
        """
        # Record in memory
        result = self.memory.record(
            traceback_text=traceback_text,
            file_path=file_path,
            command=command,
            code_snippet=code_snippet,
            session_id=self._session_id,
        )
        
        # Record in session tracker
        stuck = self.session.record_error(result["error_class"])
        
        # Build response
        response = {
            "error_class": result["error_class"],
            "is_repeat": result["is_repeat"],
            "times_seen": result["times_seen"],
            "fix_hint": result["fix_hint"],
            "stuck": stuck is not None,
        }
        
        # If stuck loop, escalate
        if stuck:
            response["stuck_message"] = (
                f"🔴 You've hit {result['error_class']} {result['times_seen']} times "
                f"this session. Want a deeper explanation?"
            )
        
        # If repeat, show history
        if result["is_repeat"]:
            response["repeat_message"] = (
                f"⚠️ This is {result['error_class']} again "
                f"({result['times_seen']} times total). {result['fix_hint']}"
            )
        
        return response
    
    def record_success(self, command: str):
        """Record a successful run."""
        self.session.record_success(command)
    
    def record_edit(self, file_path: str):
        """Record that a file was edited. Check if this is a prevention."""
        # If user edits after viewing warnings → likely Fixed Before Run
        if self._last_warned_classes:
            self._prevented_failures += 1
            self._last_warned_classes.clear()
        self.session.record_edit(file_path)
    
    # ═════════════════════════════════════
    # LLM EXPLANATION
    # ═════════════════════════════════════
    
    def explain_error(self, traceback_text: str, code_snippet: str = "") -> Dict:
        """
        Use LLM to explain an error (when pattern library isn't enough).
        LLM NEVER decides to interrupt — only explains.
        """
        matches = match_traceback(traceback_text)
        error_class = matches[0].error_class if matches else "unknown"
        
        context = self.session.get_flow_summary()
        
        return self.llm.explain_error(
            error_class=error_class,
            traceback=traceback_text,
            code_snippet=code_snippet,
            context=context,
        )
    
    # ═════════════════════════════════════
    # FEEDBACK (dismiss / accept warnings)
    # ═════════════════════════════════════
    
    def dismiss_warning(self):
        """User dismissed the last warning."""
        self.policy.record_dismissal()
    
    def accept_warning(self):
        """User found the last warning useful."""
        self.policy.record_accept()
    
    # ═════════════════════════════════════
    # STATUS & STATS
    # ═════════════════════════════════════
    
    def status(self) -> Dict:
        """Full status report."""
        return {
            "session": self.session.get_session_stats(),
            "memory": self.memory.stats(),
            "interrupts": self.policy.get_stats(),
            "llm": self.llm.get_status(),
            "session_id": self._session_id,
            "prevented_failures": self._prevented_failures,
        }
    
    def weekly_patterns(self) -> List[Dict]:
        """Top error patterns this week. Developers love pattern awareness."""
        cutoff = time.time() - 7 * 86400
        entries = self.memory._load()
        week_entries = [e for e in entries if e.timestamp > cutoff]
        
        counts: Dict[str, int] = {}
        for e in week_entries:
            counts[e.error_class] = counts.get(e.error_class, 0) + 1
        
        return sorted(
            [{"error_class": k, "count": v} for k, v in counts.items()],
            key=lambda x: -x["count"]
        )[:5]
    
    def display_status(self) -> str:
        """Human-readable status."""
        s = self.status()
        lines = []
        lines.append("═" * 45)
        lines.append("  🧠 JARVIS V2 — Developer Co-Pilot")
        lines.append("═" * 45)
        
        # Session
        session = s["session"]
        lines.append(f"  Session: {session['duration_minutes']}min")
        lines.append(f"  Phase: {session['current_phase'] or 'idle'}")
        lines.append(f"  Errors this session: {session['total_errors']}")
        lines.append(f"  Cycles completed: {session['cycles_completed']}")
        
        if session['stuck_errors']:
            lines.append("")
            lines.append("  🔴 STUCK ON:")
            for se in session['stuck_errors']:
                lines.append(f"    - {se['error_class']} ({se['count']}x)")
        
        # Memory
        mem = s["memory"]
        lines.append(f"\n  Total errors recorded: {mem['total']}")
        if mem.get('classes'):
            lines.append("  Top error classes:")
            for cls, count in list(mem['classes'].items())[:3]:
                lines.append(f"    {cls}: {count}")
        if mem.get('estimated_time_wasted_minutes'):
            lines.append(f"  Estimated time wasted: {mem['estimated_time_wasted_minutes']} min")
        
        # Interrupts
        intr = s["interrupts"]
        if intr["total"] > 0:
            lines.append(f"\n  Warnings shown: {intr['total']}")
            lines.append(f"  Accepted: {intr['accepted']} ({intr['accept_rate']:.0%})")
            lines.append(f"  Dismissed: {intr['dismissed']} ({intr['dismiss_rate']:.0%})")
        
        # LLM
        llm = s["llm"]
        lines.append(f"\n  LLM: {'✅ ' + llm['model'] if llm['available'] else '❌ not available'}")
        
        lines.append("═" * 45)
        return "\n".join(lines)
    
    # ═════════════════════════════════════
    # 14-DAY EXPERIMENT LOGGING
    # ═════════════════════════════════════
    
    def log_experiment(self, event_type: str, detail: str = "",
                       time_saved: int = 0) -> Dict:
        """
        Log a 14-day experiment event.
        
        Event types:
          - saved: Jarvis saved time
          - annoyed: Jarvis was annoying
          - missed: Jarvis should have helped but didn't
          - wrong: Prediction was wrong
          - silent: Jarvis should have been silent
        """
        entry = {
            "type": event_type,
            "detail": detail,
            "time_saved_seconds": time_saved,
            "time": datetime.now().isoformat(),
            "session_id": self._session_id,
            "session_stats": self.session.get_session_stats(),
        }
        
        os.makedirs(os.path.dirname(self._experiment_file), exist_ok=True)
        try:
            with open(self._experiment_file, 'a') as f:
                f.write(json.dumps(entry) + '\n')
        except IOError:
            pass
        
        return {"logged": True, "type": event_type}
    
    def experiment_summary(self) -> Dict:
        """Summarize the 14-day experiment."""
        if not os.path.exists(self._experiment_file):
            return {"total_events": 0, "message": "No experiment data yet."}
        
        events = {"saved": 0, "annoyed": 0, "missed": 0, "wrong": 0, "silent": 0}
        total_time_saved = 0
        days = set()
        
        try:
            with open(self._experiment_file) as f:
                for line in f:
                    entry = json.loads(line.strip())
                    etype = entry.get("type", "")
                    if etype in events:
                        events[etype] += 1
                    total_time_saved += entry.get("time_saved_seconds", 0)
                    if "time" in entry:
                        days.add(entry["time"][:10])
        except Exception:
            pass
        
        total = sum(events.values())
        
        return {
            "total_events": total,
            "days_tracked": len(days),
            "saved": events["saved"],
            "annoyed": events["annoyed"],
            "missed": events["missed"],
            "wrong": events["wrong"],
            "silent_should_be": events["silent"],
            "total_time_saved_minutes": total_time_saved // 60,
            "dismissal_rate": events["annoyed"] / max(total, 1),
            "verdict": (
                "ADDICTIVE ✅" if events["saved"] > events["annoyed"] * 2
                else "NEEDS WORK ⚠️" if events["saved"] > events["annoyed"]
                else "NOT READY ❌"
            ),
        }
