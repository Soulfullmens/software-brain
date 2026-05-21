"""
error_memory.py — Records errors with full context, matches semantically.

NOT literal traceback matching. Matches ERROR CLASSES.

Stores in ~/.jarvis/error_memory.jsonl
Each entry: {error_class, traceback, file, context, fix_applied, timestamp}

Matching: Given current code, find past errors of the same CLASS
that happened in similar contexts.
"""
import os, json, time, re, math
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

from .pattern_library import (
    PATTERNS, match_traceback, scan_code_for_risks,
    ErrorPattern, get_pattern_by_class
)


MEMORY_DIR = os.path.join(os.path.expanduser("~"), ".jarvis")
MEMORY_FILE = os.path.join(MEMORY_DIR, "error_memory.jsonl")
MAX_ENTRIES = 500


@dataclass
class ErrorEntry:
    """One recorded error with full context."""
    error_class: str           # semantic class: "missing_import", "type_mismatch"
    traceback: str             # raw traceback text
    file_path: str             # which file caused it
    code_snippet: str          # relevant code around the error
    fix_applied: str           # what the user did to fix it (empty = unknown)
    command: str               # what command was run (python x.py, pytest, etc.)
    timestamp: float = 0.0
    session_id: str = ""       # groups errors in same coding session
    resolved: bool = False     # whether the user fixed it
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'ErrorEntry':
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class ErrorMemory:
    """
    Records errors and matches them semantically against future code.
    
    Core capability:
      - record(traceback, file, code) → stores classified error
      - check_risks(code) → returns pre-run warnings based on patterns + history
      - similar_past(error_class) → finds past errors of same class
    """
    
    def __init__(self, memory_file: str = None):
        self._file = memory_file or MEMORY_FILE
        os.makedirs(os.path.dirname(self._file), exist_ok=True)
        self._cache: Optional[List[ErrorEntry]] = None
    
    def record(self, traceback_text: str, file_path: str = "",
               code_snippet: str = "", command: str = "",
               fix_applied: str = "", session_id: str = "") -> Dict:
        """
        Record an error. Auto-classifies using pattern library.
        
        Returns: {classified, error_class, is_repeat, times_seen}
        """
        # Classify
        matches = match_traceback(traceback_text)
        error_class = matches[0].error_class if matches else "unclassified"
        
        entry = ErrorEntry(
            error_class=error_class,
            traceback=traceback_text[:2000],  # Cap traceback length
            file_path=file_path,
            code_snippet=code_snippet[:1000],
            fix_applied=fix_applied,
            command=command,
            timestamp=time.time(),
            session_id=session_id,
        )
        
        # Check if repeat
        past = self.get_by_class(error_class)
        times_seen = len(past) + 1
        is_repeat = times_seen > 1
        
        # Store
        self._append(entry)
        
        return {
            "classified": error_class != "unclassified",
            "error_class": error_class,
            "is_repeat": is_repeat,
            "times_seen": times_seen,
            "fix_hint": matches[0].fix_hint if matches else "",
            "entry": entry,
        }
    
    def check_risks(self, code_text: str, file_path: str = "") -> List[Dict]:
        """
        PRE-RUN CHECK: Scan code for patterns that predict errors.
        
        Combines:
          1. Pattern library (static analysis of code)
          2. Your personal error history (same class in same/similar files)
          3. Failure streak multiplier (unresolved repeats → escalate)
        
        Returns list of warnings, sorted by severity.
        Each warning includes 'confidence_reason' explaining the score.
        """
        warnings = []
        
        # Source 1: Pattern library (static)
        pattern_risks = scan_code_for_risks(code_text)
        for risk in pattern_risks:
            warning = {
                "source": "pattern",
                "error_class": risk["error_class"],
                "message": risk["fix_hint"],
                "severity": risk["severity"],
                "line_hint": risk["match"].get("line_hint"),
                "confidence": 0.6,  # Base confidence for pattern match
                "confidence_reason": "pattern match only",
                "is_history": False,
            }
            
            # Boost confidence if you've hit this before (HISTORY-FIRST)
            past = self.get_by_class(risk["error_class"])
            if past:
                past_in_file = [e for e in past if e.file_path == file_path]
                target_entries = past_in_file or past
                recency_boost = self._recency_weight(target_entries)
                streak = self._unresolved_streak(target_entries)
                streak_boost = min(streak * 0.03, 0.10)  # +3% per repeat, max +10%
                
                if past_in_file:
                    base_conf = 0.85 + (recency_boost * 0.1) + streak_boost
                    warning["confidence"] = min(base_conf, 0.98)
                    warning["is_history"] = True
                    
                    # Recency-aware message
                    last_entry = past_in_file[-1]
                    time_ago = self._time_ago(last_entry.timestamp)
                    
                    # Frequency message: "3 times today" is stronger than "before"
                    today_count = self._count_today(past_in_file)
                    if today_count >= 2:
                        warning["message"] = (
                            f"You hit this {today_count} times today. "
                            f"{risk['fix_hint']}"
                        )
                    else:
                        warning["message"] = (
                            f"This exact failure happened before ({time_ago}). "
                            f"{risk['fix_hint']}"
                        )
                    
                    # Add last fix if known
                    last_fix = next(
                        (e.fix_applied for e in reversed(past_in_file) if e.fix_applied),
                        None
                    )
                    if last_fix:
                        warning["message"] += f" Last fix: {last_fix}"
                    
                    # Confidence explanation line
                    reasons = [f"same file", f"{time_ago}"]
                    if streak > 1:
                        reasons.append(f"{streak}x streak")
                    if today_count >= 2:
                        reasons.append(f"{today_count}x today")
                    warning["confidence_reason"] = (
                        f"{warning['confidence']:.0%} — {', '.join(reasons)}"
                    )
                else:
                    base_conf = 0.70 + (recency_boost * 0.1) + streak_boost
                    warning["confidence"] = min(base_conf, 0.85)
                    warning["is_history"] = True
                    time_ago = self._time_ago(past[-1].timestamp)
                    warning["message"] = (
                        f"This may fail — you've hit {risk['error_class']} "
                        f"{len(past)} time(s) in other files ({time_ago}). "
                        f"{risk['fix_hint']}"
                    )
                    warning["confidence_reason"] = (
                        f"{warning['confidence']:.0%} — other files, {time_ago}"
                    )
            
            # AGGRESSIVE FILTER: only include if worth showing
            if self._should_show(warning):
                warnings.append(warning)
        
        # Source 2: File-specific history (even without pattern match)
        if file_path:
            file_errors = self.get_by_file(file_path)
            seen_classes = {w["error_class"] for w in warnings}
            
            for entry in file_errors[-3:]:
                if entry.error_class not in seen_classes:
                    pattern = get_pattern_by_class(entry.error_class)
                    recency = self._recency_weight([entry])
                    time_ago = self._time_ago(entry.timestamp)
                    
                    msg = (
                        f"This file had {entry.error_class} {time_ago}. "
                        f"{pattern.fix_hint if pattern else 'Check carefully.'}"
                    )
                    if recency < 0.3:
                        msg = f"(Old) {msg}"
                    
                    hist_warning = {
                        "source": "history",
                        "error_class": entry.error_class,
                        "message": msg,
                        "severity": pattern.severity_seconds if pattern else 60,
                        "line_hint": None,
                        "confidence": 0.4 + (recency * 0.3),
                        "confidence_reason": f"{0.4 + (recency * 0.3):.0%} — history only, {time_ago}",
                        "is_history": True,
                    }
                    if self._should_show(hist_warning):
                        warnings.append(hist_warning)
        
        # Sort by confidence × severity (most urgent first)
        warnings.sort(key=lambda w: w["confidence"] * w["severity"], reverse=True)
        
        return warnings
    
    @staticmethod
    def _unresolved_streak(entries: List['ErrorEntry']) -> int:
        """Count consecutive unresolved errors of same class (from most recent)."""
        streak = 0
        for entry in reversed(entries):
            if entry.resolved:
                break
            streak += 1
        return streak
    
    @staticmethod
    def _count_today(entries: List['ErrorEntry']) -> int:
        """Count errors from the last 24 hours."""
        cutoff = time.time() - 86400
        return sum(1 for e in entries if e.timestamp > cutoff)
    
    @staticmethod
    def _should_show(warning: Dict) -> bool:
        """
        AGGRESSIVE FILTER: Only show warnings worth the user's attention.
        
        Rules:
        - History-backed warnings: always show (confidence ≥ 0.4 from history)
        - Pattern-only (no history): only if confidence ≥ 0.7 (high pattern match)
        - Never show anything below 0.35 confidence
        """
        conf = warning.get("confidence", 0)
        if conf < 0.35:
            return False
        if warning.get("is_history"):
            return True  # History-backed = always worth showing
        return conf >= 0.70  # Pattern-only needs high confidence

    
    @staticmethod
    def _recency_weight(entries: List['ErrorEntry']) -> float:
        """How recent are these errors? 1.0 = today, 0.0 = months ago."""
        if not entries:
            return 0.0
        latest = max(e.timestamp for e in entries)
        age_hours = (time.time() - latest) / 3600
        # Exponential decay: half-life = 48 hours
        return math.exp(-0.693 * age_hours / 48)
    
    @staticmethod
    def _time_ago(timestamp: float) -> str:
        """Human-readable time ago."""
        if timestamp <= 0:
            return "some time ago"
        delta = time.time() - timestamp
        if delta < 3600:
            return f"{int(delta / 60)}min ago"
        elif delta < 86400:
            return f"{int(delta / 3600)}h ago"
        elif delta < 604800:
            return f"{int(delta / 86400)}d ago"
        else:
            return f"{int(delta / 604800)}w ago"

    
    def get_by_class(self, error_class: str) -> List[ErrorEntry]:
        """Get all past errors of a given class."""
        return [e for e in self._load() if e.error_class == error_class]
    
    def get_by_file(self, file_path: str) -> List[ErrorEntry]:
        """Get all past errors in a given file."""
        norm = os.path.normpath(file_path).lower()
        return [e for e in self._load() 
                if os.path.normpath(e.file_path).lower() == norm]
    
    def get_recent(self, n: int = 10) -> List[ErrorEntry]:
        """Get N most recent errors."""
        return self._load()[-n:]
    
    def mark_resolved(self, error_class: str, fix: str):
        """Mark most recent error of a class as resolved with a fix."""
        entries = self._load()
        for entry in reversed(entries):
            if entry.error_class == error_class and not entry.resolved:
                entry.resolved = True
                entry.fix_applied = fix
                break
        self._save_all(entries)
    
    def stats(self) -> Dict:
        """Error statistics for the user."""
        entries = self._load()
        if not entries:
            return {"total": 0, "classes": {}, "worst_files": []}
        
        classes = {}
        files = {}
        for e in entries:
            classes[e.error_class] = classes.get(e.error_class, 0) + 1
            if e.file_path:
                fname = os.path.basename(e.file_path)
                files[fname] = files.get(fname, 0) + 1
        
        top_classes = sorted(classes.items(), key=lambda x: -x[1])[:5]
        top_files = sorted(files.items(), key=lambda x: -x[1])[:5]
        
        # Estimated time saved if preemptive warnings worked
        total_severity = 0
        for e in entries:
            p = get_pattern_by_class(e.error_class)
            if p:
                total_severity += p.severity_seconds
        
        return {
            "total": len(entries),
            "classes": dict(top_classes),
            "worst_files": [{"file": f, "errors": c} for f, c in top_files],
            "estimated_time_wasted_minutes": total_severity // 60,
        }
    
    def count(self) -> int:
        return len(self._load())
    
    # ── Storage ──────────────────────────────────────
    
    def _load(self) -> List[ErrorEntry]:
        if self._cache is not None:
            return self._cache
        
        entries = []
        if os.path.exists(self._file):
            try:
                with open(self._file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            entries.append(ErrorEntry.from_dict(json.loads(line)))
            except (json.JSONDecodeError, IOError):
                pass
        
        self._cache = entries
        return entries
    
    def _append(self, entry: ErrorEntry):
        entries = self._load()
        entries.append(entry)
        
        # Cap total entries
        if len(entries) > MAX_ENTRIES:
            entries = entries[-MAX_ENTRIES:]
        
        self._cache = entries
        
        try:
            with open(self._file, 'a') as f:
                f.write(json.dumps(entry.to_dict()) + '\n')
        except IOError:
            pass
    
    def _save_all(self, entries: List[ErrorEntry]):
        """Rewrite entire memory file (for updates like mark_resolved)."""
        self._cache = entries
        try:
            with open(self._file, 'w') as f:
                for entry in entries:
                    f.write(json.dumps(entry.to_dict()) + '\n')
        except IOError:
            pass
