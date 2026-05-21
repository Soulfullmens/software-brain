"""
jarvis.py — Jarvis V1.5: Cognitive Prosthetic for Software Use.

NOT an assistant. NOT automation. NOT an agent.
→ Makes your computer UNDERSTANDABLE.
→ Predicts what you'll do next. Explains WHY.

3 MODES:
  Insight  — "What am I looking at?" (hotkey/voice/auto)
  Guide    — "How do I do X?" (step-by-step instructions)
  Assist   — "Do step 1 for me" (safe execution only)

V1.5 ADDITIONS:
  Session Intelligence — flow-based, not snapshot-based
  Next Likely Action   — habit-aware prediction
  WHY transparency     — every suggestion explains itself
  Repeated action detection — catches struggle patterns
"""
import os, sys, time, threading, json, traceback
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field

# Add project path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from agent.tools.screen_intelligence import ScreenIntelligence
from agent.tools.app_analyzer import AppAnalyzer
from agent.tools.desktop_v2 import DesktopToolV2
from agent.tools.readonly_fs import ReadOnlyFS
from agent.security.security_kernel import SecurityKernel, AuthorityLevel, ActionVerdict


class RiskLevel(Enum):
    SAFE = "safe"       # 🟢 Navigation / read-only
    MODIFIES = "modify"  # 🟡 Changes app state
    RISKY = "risky"     # 🔴 Irreversible / destructive


RISK_ICONS = {
    RiskLevel.SAFE: "🟢",
    RiskLevel.MODIFIES: "🟡",
    RiskLevel.RISKY: "🔴",
}


@dataclass
class Suggestion:
    """A suggested action with risk label + WHY transparency."""
    text: str
    risk: RiskLevel
    action_type: str  # "navigate", "open", "click", "type", "shortcut", "guide"
    action_data: Dict = field(default_factory=dict)
    why: str = ""  # WHY this suggestion — transparency builds trust
    
    def display(self, index: int) -> str:
        icon = RISK_ICONS[self.risk]
        line = f"  {index}. {icon} {self.text}"
        if self.why:
            line += f"\n       WHY: {self.why}"
        return line


class Confidence(Enum):
    HIGH = "high"       # App known + good OCR + clear context
    MEDIUM = "medium"   # Partial match or sparse text
    LOW = "low"         # Unknown app + no OCR + ambiguous


CONFIDENCE_ICONS = {
    Confidence.HIGH: "🟩",
    Confidence.MEDIUM: "🟨",
    Confidence.LOW: "🟥",
}


@dataclass
class InsightResult:
    """Structured insight from screen analysis."""
    app_name: str = "Unknown"
    app_category: str = "unknown"
    window_title: str = ""
    screen_text: str = ""
    context_summary: str = ""
    likely_intent: str = ""
    important_areas: List[str] = field(default_factory=list)
    suggestions: List[Suggestion] = field(default_factory=list)
    recall_prompt: str = ""  # "Last time you did X..."
    confidence: Confidence = Confidence.MEDIUM
    confidence_reasons: List[str] = field(default_factory=list)
    timestamp: str = ""
    analysis_ms: float = 0
    
    def display(self) -> str:
        lines = []
        lines.append("═" * 50)
        lines.append(f"  🧠 JARVIS INSIGHT")
        lines.append("═" * 50)
        lines.append(f"  APP: {self.app_name}")
        lines.append(f"  CONTEXT: {self.context_summary}")
        if self.likely_intent:
            lines.append(f"  LIKELY INTENT: {self.likely_intent}")
        
        # Confidence line
        icon = CONFIDENCE_ICONS[self.confidence]
        lines.append(f"  CONFIDENCE: {icon} {self.confidence.value.upper()}")
        if self.confidence_reasons:
            for r in self.confidence_reasons:
                lines.append(f"    ↳ {r}")
        if self.confidence == Confidence.LOW:
            lines.append("    ⚠ I may be wrong. Run insight again or provide context.")
        
        # Memory recall
        if self.recall_prompt:
            lines.append("")
            lines.append(f"  💾 {self.recall_prompt}")
        
        if self.important_areas:
            lines.append("")
            lines.append("  IMPORTANT AREAS:")
            for area in self.important_areas:
                lines.append(f"   → {area}")
        
        if self.suggestions:
            lines.append("")
            lines.append("  SUGGESTIONS:")
            for i, s in enumerate(self.suggestions, 1):
                lines.append(s.display(i))
        
        # Next Likely Action prediction (shown if available)
        if hasattr(self, '_prediction') and self._prediction:
            lines.append("")
            p = self._prediction
            conf_icon = "🟩" if p.get('confidence') == 'high' else "🟨"
            lines.append(f"  🔮 NEXT: {p['action']}")
            lines.append(f"     {conf_icon} (from {p['source']})")
        
        lines.append("")
        lines.append(f"  ⏱ {self.analysis_ms:.0f}ms")
        lines.append("═" * 50)
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# CONFUSION DETECTOR
# ═══════════════════════════════════════════════════════

class ConfusionDetector:
    """
    Detects when user seems confused or lost.
    Auto-surfaces "Need help?" instead of waiting for hotkey.
    
    Tracks: rapid switching, new windows, errors, cursor hesitation.
    """
    
    def __init__(self):
        self._window_switches: List[float] = []
        self._last_window: str = ""
        self._inactivity_start: float = 0
        self._error_count: int = 0
        self._known_windows: set = set()
        # Cursor hesitation tracking
        self._last_mouse_pos: Optional[Tuple[int, int]] = None
        self._hover_start: float = 0
        self._hover_region_hits: int = 0
        self._scroll_directions: List[str] = []  # "up"/"down" sequence
    
    def observe(self, window_title: str, has_error_dialog: bool = False,
                mouse_pos: Optional[Tuple[int, int]] = None) -> Optional[str]:
        """Observe user behavior. Returns confusion reason or None."""
        now = time.time()
        
        # ── Cursor hesitation detection ──
        if mouse_pos is not None:
            hesitation = self._check_hesitation(mouse_pos, now)
            if hesitation:
                return hesitation
        
        # ── Rapid window switching (3+ switches in 10 seconds) ──
        if window_title != self._last_window:
            self._window_switches.append(now)
            self._window_switches = [t for t in self._window_switches if now - t < 10]
            self._last_window = window_title
            
            if len(self._window_switches) >= 3:
                self._window_switches.clear()
                return "rapid_switching"
        
        # ── New/unknown window ──
        if window_title and window_title not in self._known_windows:
            self._known_windows.add(window_title)
            if len(self._known_windows) > 1:  # Skip the very first window
                return "new_window"
        
        # ── Error dialog detected ──
        if has_error_dialog:
            self._error_count += 1
            if self._error_count >= 1:
                self._error_count = 0
                return "error_detected"
        
        return None
    
    def _check_hesitation(self, pos: Tuple[int, int], now: float) -> Optional[str]:
        """Detect cursor hovering, repeated region visits, scroll loops."""
        if self._last_mouse_pos is None:
            self._last_mouse_pos = pos
            self._hover_start = now
            return None
        
        dx = abs(pos[0] - self._last_mouse_pos[0])
        dy = abs(pos[1] - self._last_mouse_pos[1])
        
        # Mouse barely moved for 5+ seconds = hovering/staring
        if dx < 20 and dy < 20:
            if now - self._hover_start > 5.0:
                self._hover_start = now  # Reset to avoid spam
                return "cursor_hesitation"
        else:
            self._hover_start = now
        
        # Same 100px region visited 3+ times = confusion
        region = (pos[0] // 100, pos[1] // 100)
        last_region = (self._last_mouse_pos[0] // 100, self._last_mouse_pos[1] // 100)
        if region == last_region:
            self._hover_region_hits += 1
            if self._hover_region_hits >= 5:
                self._hover_region_hits = 0
                return "repeated_hover"
        else:
            self._hover_region_hits = 0
        
        self._last_mouse_pos = pos
        return None
    
    def observe_scroll(self, direction: str) -> Optional[str]:
        """Track scroll patterns. Returns 'scroll_loop' if user scrolls up/down repeatedly."""
        self._scroll_directions.append(direction)
        if len(self._scroll_directions) > 10:
            self._scroll_directions = self._scroll_directions[-10:]
        
        # Detect scroll loop: up-down-up-down = 4 reversals
        reversals = 0
        for i in range(1, len(self._scroll_directions)):
            if self._scroll_directions[i] != self._scroll_directions[i-1]:
                reversals += 1
        if reversals >= 4:
            self._scroll_directions.clear()
            return "scroll_loop"
        return None
    
    def observe_repeated_action(self, action: str) -> Optional[str]:
        """Detect repeated failed actions — the strongest confusion signal.
        
        Catches: clicking same button, opening/closing menus, undo-redo loops, re-running commands.
        """
        if not hasattr(self, '_action_history'):
            self._action_history: List[str] = []
        
        self._action_history.append(action)
        if len(self._action_history) > 20:
            self._action_history = self._action_history[-20:]
        
        # Same action 3+ times = struggle
        if len(self._action_history) >= 3:
            last_3 = self._action_history[-3:]
            if len(set(last_3)) == 1:
                self._action_history.clear()
                return "repeated_action"
        
        # Undo-redo loop: alternating pattern
        if len(self._action_history) >= 4:
            last_4 = self._action_history[-4:]
            if last_4[0] == last_4[2] and last_4[1] == last_4[3] and last_4[0] != last_4[1]:
                self._action_history.clear()
                return "undo_redo_loop"
        
        return None
    
    def get_nudge_message(self, reason: str) -> str:
        messages = {
            "rapid_switching": "💡 Switching apps quickly? Press J for context help.",
            "new_window": "💡 New screen detected. Press J to understand it.",
            "error_detected": "💡 Error detected. Press J for guidance.",
            "inactivity": "💡 Stuck? Press J and I'll explain this screen.",
            "cursor_hesitation": "💡 Staring at this area? Press J for explanation.",
            "repeated_hover": "💡 Looking for something? Press J for help.",
            "scroll_loop": "💡 Scrolling back and forth? Press J to find what you need.",
            "repeated_action": "💡 Doing the same thing repeatedly? Press J — maybe there's a better way.",
            "undo_redo_loop": "💡 Undo-redo loop detected. Press J for guidance.",
        }
        return messages.get(reason, "💡 Need help? Press J.")
    
    def reset(self):
        self._window_switches.clear()
        self._last_window = ""
        self._error_count = 0
        self._known_windows.clear()
        self._last_mouse_pos = None
        self._hover_start = 0
        self._hover_region_hits = 0
        self._scroll_directions.clear()
        if hasattr(self, '_action_history'):
            self._action_history.clear()


# ═══════════════════════════════════════════════════════
# VISUAL OVERLAY
# ═══════════════════════════════════════════════════════

class VisualOverlay:
    """
    Draw highlights on screen — boxes, labels, arrows.
    Uses tkinter for cross-platform transparent overlays.
    """
    
    def __init__(self):
        self._overlay_window = None
        self._active = False
    
    def highlight_region(self, x: int, y: int, w: int, h: int, 
                         label: str = "", color: str = "green"):
        """Draw a highlight box on screen."""
        try:
            import tkinter as tk
            
            if self._overlay_window:
                self.clear()
            
            root = tk.Tk()
            root.attributes('-topmost', True)
            root.attributes('-alpha', 0.3)
            root.overrideredirect(True)
            root.geometry(f"{w}x{h}+{x}+{y}")
            
            color_map = {"green": "#00ff00", "yellow": "#ffff00", "red": "#ff0000", "blue": "#0088ff"}
            bg = color_map.get(color, color)
            
            canvas = tk.Canvas(root, width=w, height=h, bg=bg, highlightthickness=3,
                             highlightbackground=bg)
            canvas.pack()
            
            if label:
                canvas.create_text(w//2, h//2, text=label, fill="white",
                                 font=("Arial", 12, "bold"))
            
            self._overlay_window = root
            self._active = True
            
            # Auto-dismiss after 3 seconds
            root.after(3000, self.clear)
            root.mainloop()
            
            return {"success": True, "highlighted": {"x": x, "y": y, "w": w, "h": h}}
        except Exception as e:
            return {"error": str(e)}
    
    def highlight_async(self, x: int, y: int, w: int, h: int,
                        label: str = "", color: str = "green"):
        """Non-blocking highlight."""
        t = threading.Thread(
            target=self.highlight_region,
            args=(x, y, w, h, label, color), daemon=True
        )
        t.start()
    
    def clear(self):
        """Remove overlay."""
        if self._overlay_window:
            try:
                self._overlay_window.destroy()
            except Exception:
                pass
            self._overlay_window = None
            self._active = False


# ═══════════════════════════════════════════════════════
# SESSION INTELLIGENCE
# ═══════════════════════════════════════════════════════

class SessionIntelligence:
    """
    Tracks the FLOW of user actions, not just snapshots.
    
    Humans operate in sequences:
      Open VS Code → Edit file → Run test → Check error → Google error
    
    Session intelligence assists the workflow, not just the moment.
    """
    
    # Common workflow patterns: (chain → likely_next)
    WORKFLOW_PATTERNS = {
        # Development workflows
        ("development", "development"): {
            "Writing/editing code": ["Run tests", "Open terminal", "Save file"],
            "Debugging code": ["Search for solution", "Check StackOverflow", "Read documentation"],
            "Running/writing tests": ["Fix failing test", "Check coverage", "Commit changes"],
            "Version control": ["Push changes", "Create PR", "Deploy"],
        },
        # Dev → Browser (search for help)
        ("development", "browser"): {
            "Debugging code": ["Search error message", "Check StackOverflow"],
            "Writing/editing code": ["Look up documentation", "Search API reference"],
        },
        # Browser → Dev (apply what you found)
        ("browser", "development"): {
            "Searching for information": ["Apply the solution", "Copy code snippet"],
            "Web browsing": ["Return to coding"],
        },
        # File manager → any
        ("file_manager", "development"): {
            "Organizing files": ["Open file in editor", "Start new project"],
        },
    }
    
    def __init__(self):
        self._chain: List[Dict] = []  # [{app, category, intent, ts}]
        self._max_chain = 50
    
    def record(self, app: str, category: str, intent: str):
        """Record an action in the session chain."""
        entry = {
            "app": app, "category": category,
            "intent": intent, "ts": time.time()
        }
        self._chain.append(entry)
        if len(self._chain) > self._max_chain:
            self._chain = self._chain[-self._max_chain:]
    
    def predict_next(self, current_app: str, current_category: str,
                     current_intent: str, memory=None) -> Optional[Dict]:
        """
        Predict next likely action based on:
          - Session flow (what came before)
          - Workflow patterns (common sequences)
          - User habits (memory)
        
        Returns: {"action": str, "confidence": str, "source": str} or None
        """
        predictions = []
        
        # Source 1: Workflow patterns
        if len(self._chain) >= 1:
            prev = self._chain[-1]
            pattern_key = (prev["category"], current_category)
            if pattern_key in self.WORKFLOW_PATTERNS:
                intent_map = self.WORKFLOW_PATTERNS[pattern_key]
                if current_intent in intent_map:
                    for action in intent_map[current_intent][:1]:
                        predictions.append({
                            "action": action,
                            "confidence": "medium",
                            "source": "workflow_pattern"
                        })
        
        # Source 2: Session flow (what you did after this intent before)
        for i, entry in enumerate(self._chain[:-1]):
            if (entry["category"] == current_category and
                entry["intent"] == current_intent and
                i + 1 < len(self._chain)):
                next_entry = self._chain[i + 1]
                predictions.append({
                    "action": f"Switch to {next_entry['app']} ({next_entry['intent']})",
                    "confidence": "medium",
                    "source": "session_flow"
                })
                break  # Only use the most recent match
        
        # Source 3: User habits (memory)
        if memory:
            freq = memory.get_frequent(current_app, "intents", top_n=2)
            if len(freq) >= 2:
                # If current intent is the most frequent, predict second-most
                if freq[0]["value"] == current_intent and freq[1]["count"] >= 3:
                    predictions.append({
                        "action": f"You often do: {freq[1]['value']}",
                        "confidence": "high" if freq[1]["count"] >= 5 else "medium",
                        "source": "habit"
                    })
        
        # Return highest-confidence prediction
        if predictions:
            # Prioritize: habit > session_flow > workflow_pattern
            priority = {"habit": 3, "session_flow": 2, "workflow_pattern": 1}
            predictions.sort(key=lambda p: priority.get(p["source"], 0), reverse=True)
            return predictions[0]
        
        return None
    
    def get_workflow_summary(self) -> str:
        """Summarize what the user has been doing this session."""
        if not self._chain:
            return "No activity recorded yet."
        
        # Deduplicate consecutive same-app entries
        flow = []
        for entry in self._chain[-10:]:
            label = f"{entry['app']}({entry['intent']})"
            if not flow or flow[-1] != label:
                flow.append(label)
        
        return " → ".join(flow[-6:])  # Show last 6 steps
    
    def detect_workflow(self) -> Optional[str]:
        """Detect if user is in a recognizable workflow."""
        if len(self._chain) < 3:
            return None
        
        recent = [e["intent"] for e in self._chain[-5:]]
        
        # Code-test-debug cycle
        if any("code" in r.lower() for r in recent) and any("test" in r.lower() for r in recent):
            if any("debug" in r.lower() or "error" in r.lower() for r in recent):
                return "code-test-debug cycle"
            return "code-test cycle"
        
        # Research workflow
        categories = [e["category"] for e in self._chain[-5:]]
        if categories.count("browser") >= 2 and categories.count("development") >= 1:
            return "research-and-implement"
        
        return None
    
    def reset(self):
        self._chain.clear()


# ═══════════════════════════════════════════════════════
# JARVIS V1.5 — THE PRODUCT
# ═══════════════════════════════════════════════════════

class JarvisV1:
    """
    Situational Intelligence for Computers.
    
    One runtime. Three modes. Daily use.
    
    Usage:
        jarvis = JarvisV1()
        result = jarvis.insight()     # What am I looking at?
        jarvis.guide(1)               # How do I do suggestion 1?
        jarvis.assist(1)              # Do suggestion 1 for me
    """
    
    def __init__(self, authority: AuthorityLevel = AuthorityLevel.SAFE):
        # Core modules (all pre-built)
        self.screen = ScreenIntelligence()
        self.apps = AppAnalyzer()
        self.desktop = DesktopToolV2()
        self.fs = ReadOnlyFS()
        self.security = SecurityKernel(authority=authority)
        
        # Jarvis-specific layers
        self.confusion = ConfusionDetector()
        self.overlay = VisualOverlay()
        self.session = SessionIntelligence()  # V1.5: flow-based intelligence
        
        # Context memory (lazy import to avoid circular)
        from agent.context_memory import ContextMemory
        self.memory = ContextMemory()
        
        # Failure log for self-improvement
        self._failure_log_path = os.path.join(
            os.path.expanduser("~"), ".jarvis", "failures.jsonl"
        )
        os.makedirs(os.path.dirname(self._failure_log_path), exist_ok=True)
        
        # State
        self._last_insight: Optional[InsightResult] = None
        self._last_prediction: Optional[Dict] = None
        self._running = False
        self._hotkey_thread = None
        self._session_log: List[Dict] = []
        
        # Config
        self.hotkey = "ctrl+shift+j"
        self.authority = authority
    
    # ═════════════════════════════════════
    # MODE 1: INSIGHT
    # ═════════════════════════════════════
    
    def insight(self) -> InsightResult:
        """
        CORE FEATURE: Capture screen → analyze → explain → suggest.
        This is the thing people use every day.
        """
        start = time.time()
        result = InsightResult(timestamp=datetime.now().isoformat())
        
        # Step 1: Get focused window
        window = self.desktop.run("get_focused_window")
        result.window_title = window.get("title", "Unknown")
        
        # Step 2: Identify the app
        app_info = self.apps.run("analyze_focused")
        result.app_name = app_info.get("name", app_info.get("process_name", "Unknown"))
        result.app_category = app_info.get("category", "unknown")
        
        # Step 3: OCR the screen
        screen_data = self.screen.run("analyze_screen")
        result.screen_text = screen_data.get("text", "")
        
        # Step 4: Build context summary  
        result.context_summary = self._build_context(result)
        
        # Step 5: Detect important areas
        result.important_areas = self._detect_important_areas(result)
        
        # Step 6: Infer likely intent
        result.likely_intent = self._infer_intent(result)
        
        # Step 7: Generate suggestions with risk labels + WHY
        result.suggestions = self._generate_suggestions(result)
        
        # Step 8: Compute confidence
        result.confidence, result.confidence_reasons = self._compute_confidence(result)
        
        # Step 9: Memory recall prompt
        result.recall_prompt = self._generate_recall(result)
        
        # Step 10: Session Intelligence — record + predict
        self.session.record(result.app_name, result.app_category, result.likely_intent)
        prediction = self.session.predict_next(
            result.app_name, result.app_category,
            result.likely_intent, self.memory
        )
        self._last_prediction = prediction
        
        # Step 11: Remember this context
        self.memory.remember(result.app_name, "windows", result.window_title)
        self.memory.remember(result.app_name, "contexts", result.context_summary)
        self.memory.remember(result.app_name, "intents", result.likely_intent)
        
        # Step 12: Check confusion
        confusion = self.confusion.observe(result.window_title)
        if confusion:
            result.important_areas.insert(0, 
                f"⚡ {self.confusion.get_nudge_message(confusion)}")
        
        result.analysis_ms = (time.time() - start) * 1000
        self._last_insight = result
        self._log("insight", result.app_name)
        
        return result
    
    def _compute_confidence(self, result: InsightResult) -> Tuple[Confidence, List[str]]:
        """Score how confident we are in this insight. Users must see when we're guessing."""
        score = 0
        reasons = []
        
        # App known in database? +3
        if result.app_category != "unknown":
            score += 3
            reasons.append("Known application")
        else:
            reasons.append("Unknown application")
        
        # Got OCR text? +2
        if result.screen_text and len(result.screen_text) > 20:
            score += 2
            reasons.append(f"OCR captured {len(result.screen_text)} chars")
        elif result.screen_text:
            score += 1
            reasons.append("OCR captured limited text")
        else:
            reasons.append("No OCR text available")
        
        # Window title informative? +1
        if result.window_title and len(result.window_title) > 5:
            score += 1
        else:
            reasons.append("Minimal window title")
        
        # Have memory for this app? +1
        past = self.memory.recall(result.app_name, "contexts", last_n=1)
        if past:
            score += 1
            reasons.append("Previous context available")
        
        # Map score to confidence level
        if score >= 5:
            return Confidence.HIGH, reasons
        elif score >= 3:
            return Confidence.MEDIUM, reasons
        else:
            return Confidence.LOW, reasons
    
    def _generate_recall(self, result: InsightResult) -> str:
        """Generate memory recall prompt. Makes the system feel intelligent."""
        app = result.app_name
        
        # Get last intent for this app
        past_intents = self.memory.recall(app, "intents", last_n=3)
        if past_intents:
            last_intent = past_intents[-1]
            if last_intent != result.likely_intent:
                return f"Last time in {app}: {last_intent}. Now: {result.likely_intent}."
            else:
                return f"Continuing: {last_intent} (same as last session)."
        
        # Get frequent contexts
        freq = self.memory.get_frequent(app, "contexts", top_n=1)
        if freq:
            return f"You usually do: {freq[0]['value']} ({freq[0]['count']}x)"
        
        return ""
    
    def _build_context(self, result: InsightResult) -> str:
        """Build human-readable context from raw data."""
        title = result.window_title
        app = result.app_name
        category = result.app_category
        text = result.screen_text[:200] if result.screen_text else ""
        
        # App-specific context builders
        if category == "browser":
            # Extract URL or page title from window title
            if " - " in title:
                page = title.rsplit(" - ", 1)[0]
                return f"Browsing: {page}"
            return f"Web browsing in {app}"
        
        elif category == "development":
            if ".py" in title:
                return f"Editing Python file: {title.split(' - ')[0].strip()}"
            elif ".js" in title or ".ts" in title:
                return f"Editing JavaScript/TypeScript: {title.split(' - ')[0].strip()}"
            return f"Programming in {app}"
        
        elif category == "office":
            if "Word" in app:
                return f"Writing document: {title.split(' - ')[0].strip()}"
            elif "Excel" in app:
                return f"Working on spreadsheet: {title.split(' - ')[0].strip()}"
            elif "PowerPoint" in app:
                return f"Editing presentation: {title.split(' - ')[0].strip()}"
            return f"Working in {app}"
        
        elif category == "file_manager":
            return f"Browsing files: {title}"
        
        elif category == "communication":
            return f"Communicating via {app}"
        
        elif category == "media":
            return f"Using media: {app}"
        
        # Generic
        if title:
            return f"Using {app}: {title[:60]}"
        return f"Using {app}"
    
    def _detect_important_areas(self, result: InsightResult) -> List[str]:
        """Detect what's important on screen."""
        areas = []
        text = result.screen_text.lower() if result.screen_text else ""
        title = result.window_title.lower()
        
        # Error detection
        error_words = ["error", "failed", "exception", "warning", "denied",
                       "not found", "crash", "fatal", "invalid", "timeout"]
        for word in error_words:
            if word in text:
                areas.append(f"⚠️ Error/warning detected: '{word}' found on screen")
                break
        
        # Unsaved changes
        if any(w in title for w in ["unsaved", "modified", "●", "*"]):
            areas.append("📝 Unsaved changes detected")
        
        # Dialog boxes
        dialog_words = ["save", "cancel", "ok", "yes", "no", "confirm", "apply"]
        dialog_count = sum(1 for w in dialog_words if w in text)
        if dialog_count >= 3:
            areas.append("💬 Dialog box — action required")
        
        # Login/auth
        if any(w in text for w in ["sign in", "log in", "password", "username", "email"]):
            areas.append("🔐 Login/authentication screen")
        
        # Settings
        if any(w in text for w in ["settings", "preferences", "configuration", "options"]):
            areas.append("⚙️ Settings/configuration page")
        
        # Install/update 
        if any(w in text for w in ["install", "update", "download", "upgrade"]):
            areas.append("📦 Installation/update in progress")
        
        if not areas:
            areas.append("✅ Normal operation — no alerts")
        
        return areas
    
    def _infer_intent(self, result: InsightResult) -> str:
        """Guess what the user is trying to do."""
        category = result.app_category
        text = result.screen_text.lower() if result.screen_text else ""
        title = result.window_title.lower()
        
        # Check memory for patterns
        past_contexts = self.memory.recall(result.app_name, "contexts", last_n=3)
        
        if category == "browser":
            if any(w in text for w in ["search", "google", "bing"]):
                return "Searching for information"
            if any(w in text for w in ["cart", "buy", "price", "add to"]):
                return "Online shopping"
            if any(w in text for w in ["inbox", "compose", "reply"]):
                return "Managing email"
            return "Web browsing"
        
        if category == "development":
            if "error" in text or "exception" in text:
                return "Debugging code"
            if "test" in text:
                return "Running/writing tests"
            if "commit" in text or "push" in text:
                return "Version control"
            return "Writing/editing code"
        
        if category == "file_manager":
            return "Organizing files"
        
        if "error" in text or "failed" in text:
            return "Troubleshooting an issue"
        
        if "settings" in text or "preferences" in text:
            return "Configuring application"
        
        return "General use"
    
    def _generate_suggestions(self, result: InsightResult) -> List[Suggestion]:
        """Generate top 3 contextual suggestions with risk labels."""
        suggestions = []
        category = result.app_category
        text = result.screen_text.lower() if result.screen_text else ""
        app = result.app_name
        
        # Get app tips
        tips = self.apps.run("get_tips", process=app + ".exe" if "." not in app else app)
        
        # ── Error on screen ──
        if any(w in text for w in ["error", "failed", "exception"]):
            suggestions.append(Suggestion(
                text="Open error details / diagnostic panel",
                risk=RiskLevel.SAFE,
                action_type="shortcut",
                action_data={"key": "ctrl+shift+m" if category == "development" else "f1"},
                why=f"Error keyword detected on screen"
            ))
        
        # ── Unsaved changes ──
        if any(w in result.window_title for w in ["●", "*", "unsaved", "Modified"]):
            # Check save frequency from memory
            save_freq = self.memory.get_frequent(app, "intents", top_n=1)
            why_save = "Unsaved changes detected in title"
            if save_freq and "save" in str(save_freq[0].get("value", "")).lower():
                why_save += f" + you save frequently ({save_freq[0]['count']}x)"
            suggestions.append(Suggestion(
                text="Save current file",
                risk=RiskLevel.MODIFIES,
                action_type="shortcut",
                action_data={"key": "ctrl+s"},
                why=why_save
            ))
        
        # ── Category-specific ──
        if category == "browser":
            suggestions.append(Suggestion(
                text="Open new tab", risk=RiskLevel.SAFE,
                action_type="shortcut", action_data={"key": "ctrl+t"},
                why="Browser detected — quick navigation"
            ))
            if "sign in" in text or "log in" in text:
                suggestions.append(Suggestion(
                    text="⚠️ Login page — be careful with credentials",
                    risk=RiskLevel.RISKY,
                    action_type="guide",
                    action_data={"steps": ["Verify the URL is correct", "Check for HTTPS", "Don't save password if public computer"]},
                    why="Login form detected — credential safety matters"
                ))
        
        elif category == "development":
            suggestions.append(Suggestion(
                text="Open command palette",
                risk=RiskLevel.SAFE,
                action_type="shortcut",
                action_data={"key": "ctrl+shift+p"},
                why="IDE detected — command palette is the fastest way to do anything"
            ))
            suggestions.append(Suggestion(
                text="Open integrated terminal",
                risk=RiskLevel.SAFE,
                action_type="shortcut",
                action_data={"key": "ctrl+`"},
                why="Code editing context — terminal access likely needed"
            ))
        
        elif category == "file_manager":
            suggestions.append(Suggestion(
                text="Open search in this folder",
                risk=RiskLevel.SAFE,
                action_type="shortcut",
                action_data={"key": "ctrl+e"},
                why="File manager detected — search is faster than browsing"
            ))
        
        elif category == "office":
            suggestions.append(Suggestion(
                text="Save document",
                risk=RiskLevel.MODIFIES,
                action_type="shortcut",
                action_data={"key": "ctrl+s"},
                why="Office document open — save early, save often"
            ))
        
        # ── Always include: app tips ──
        if tips.get("tips") and len(suggestions) < 3:
            for tip in tips["tips"][:2]:
                if len(suggestions) >= 3:
                    break
                suggestions.append(Suggestion(
                    text=tip, risk=RiskLevel.SAFE,
                    action_type="guide", action_data={"tip": tip},
                    why=f"App-specific tip for {app}"
                ))
        
        # ── Default: universal suggestions ──
        if not suggestions:
            suggestions = [
                Suggestion(text="Take screenshot for reference", risk=RiskLevel.SAFE,
                          action_type="shortcut", action_data={"key": "win+shift+s"},
                          why="Universal — capture what you see for later"),
                Suggestion(text="Open Task Manager", risk=RiskLevel.SAFE,
                          action_type="shortcut", action_data={"key": "ctrl+shift+esc"},
                          why="System monitoring — check resource usage"),
                Suggestion(text="Switch to last window", risk=RiskLevel.SAFE,
                          action_type="shortcut", action_data={"key": "alt+tab"},
                          why="Quick context switch"),
            ]
        
        return suggestions[:3]
    
    # ═════════════════════════════════════
    # MODE 2: GUIDE
    # ═════════════════════════════════════
    
    def guide(self, suggestion_index: int) -> Dict:
        """
        GUIDE MODE: Visual-first, text-second.
        Highlight → Label → Step.  Does NOT execute.
        """
        if not self._last_insight or not self._last_insight.suggestions:
            return {"error": "Run insight() first to get suggestions."}
        
        if suggestion_index < 1 or suggestion_index > len(self._last_insight.suggestions):
            return {"error": f"Pick 1-{len(self._last_insight.suggestions)}"}
        
        suggestion = self._last_insight.suggestions[suggestion_index - 1]
        
        guide = {
            "suggestion": suggestion.text,
            "risk": f"{RISK_ICONS[suggestion.risk]} {suggestion.risk.value}",
            "steps": [],
            "visual_hints": [],  # Visual-first: [{region, label, color}]
        }
        
        if suggestion.action_type == "shortcut":
            key = suggestion.action_data.get("key", "")
            guide["steps"] = [
                f"Step 1: Make sure {self._last_insight.app_name} is focused",
                f"Step 2: Press {key.upper().replace('+', ' + ')}",
                f"Step 3: The action will execute immediately",
            ]
            # Visual hint: highlight keyboard area
            guide["visual_hints"].append({
                "type": "keyboard", "key": key,
                "label": f"Press {key.upper()}", "color": "blue"
            })
        elif suggestion.action_type == "guide":
            steps = suggestion.action_data.get("steps", [])
            if steps:
                guide["steps"] = [f"Step {i+1}: {s}" for i, s in enumerate(steps)]
            else:
                guide["steps"] = [f"Follow this tip: {suggestion.text}"]
        elif suggestion.action_type == "navigate":
            path = suggestion.action_data.get("path", "")
            guide["steps"] = [
                f"Step 1: Click on the menu/navigation area",
                f"Step 2: Navigate to: {path}",
                f"Step 3: Click to open",
            ]
            # Visual hint: highlight top menu bar
            guide["visual_hints"].append({
                "type": "screen_region", "region": "top_menu",
                "label": f"Click here → {path}", "color": "green"
            })
        elif suggestion.action_type == "open":
            target = suggestion.action_data.get("target", "")
            guide["steps"] = [
                f"Step 1: Open {target}",
            ]
        
        # Display: Visual-first
        print("\n" + "─" * 40)
        print(f"  📋 GUIDE: {suggestion.text}")
        print(f"  Risk: {guide['risk']}")
        print("─" * 40)
        
        for hint in guide["visual_hints"]:
            print(f"  👁️  LOOK: {hint['label']}")
        
        for step in guide["steps"]:
            print(f"  {step}")
        print("─" * 40 + "\n")
        
        # Try to show visual overlay if we have region info
        for hint in guide.get("visual_hints", []):
            if hint.get("type") == "screen_region" and hint.get("region") == "top_menu":
                # Highlight the top menu bar area
                self.overlay.highlight_async(0, 0, 400, 40,
                    label=hint["label"], color=hint.get("color", "green"))
        
        self._log("guide", suggestion.text)
        return guide
    
    # ═════════════════════════════════════
    # MODE 3: ASSIST (Limited Execution)
    # ═════════════════════════════════════
    
    def assist(self, suggestion_index: int) -> Dict:
        """
        ASSIST MODE: Execute a suggestion — SAFE actions only.
        🟢 = Auto-execute
        🟡 = Ask first
        🔴 = Refuse, show guide instead
        """
        if not self._last_insight or not self._last_insight.suggestions:
            return {"error": "Run insight() first."}
        
        if suggestion_index < 1 or suggestion_index > len(self._last_insight.suggestions):
            return {"error": f"Pick 1-{len(self._last_insight.suggestions)}"}
        
        suggestion = self._last_insight.suggestions[suggestion_index - 1]
        
        # 🔴 RISKY = Never execute, show guide
        if suggestion.risk == RiskLevel.RISKY:
            print(f"\n  🔴 Too risky to auto-execute: {suggestion.text}")
            print("  Showing guide instead...\n")
            return self.guide(suggestion_index)
        
        # Security gate
        sec_result = self.security.check_action(
            "desktop_control",
            suggestion.action_type,
            suggestion.action_data
        )
        
        if sec_result.verdict == ActionVerdict.BLOCK:
            return {"blocked": True, "reason": sec_result.reason}
        
        if sec_result.verdict == ActionVerdict.ASK_USER:
            print(f"\n  🟡 This action modifies state: {suggestion.text}")
            print(f"  {sec_result.message_to_user}")
            confirm = input("  Execute? (y/n): ").strip().lower()
            if confirm != 'y':
                return {"cancelled": True}
        
        # Execute
        if suggestion.action_type == "shortcut":
            key = suggestion.action_data.get("key", "")
            result = self.desktop.run("key_press", key=key)
        elif suggestion.action_type == "open":
            target = suggestion.action_data.get("target", "")
            result = self.desktop.run("launch_app", name=target)
        elif suggestion.action_type == "navigate":
            result = {"guided": True, "message": "Navigation requires manual steps"}
        else:
            result = {"guided": True, "message": "Action requires manual execution"}
        
        icon = "🟢" if suggestion.risk == RiskLevel.SAFE else "🟡"
        print(f"\n  {icon} Executed: {suggestion.text}")
        self._log("assist", suggestion.text)
        
        return result
    
    # ═════════════════════════════════════
    # BACKGROUND LISTENER
    # ═════════════════════════════════════
    
    def start(self):
        """Start Jarvis with hotkey listener."""
        if self._running:
            return {"error": "Already running"}
        
        self._running = True
        print("\n" + "═" * 50)
        print("  🧠 JARVIS V1.5 — ACTIVE")
        print(f"  Hotkey: {self.hotkey.upper()}")
        print(f"  Authority: {self.authority.value.upper()}")
        print("  Commands: insight | guide N | assist N | flow | quit")
        print("═" * 50 + "\n")
        
        # Try to register global hotkey
        try:
            import keyboard
            keyboard.add_hotkey(self.hotkey, self._on_hotkey)
            print(f"  ✅ Hotkey {self.hotkey.upper()} registered")
        except ImportError:
            print("  ⚠️ 'keyboard' module not installed — hotkey disabled")
            print("    Install: pip install keyboard")
        except Exception as e:
            print(f"  ⚠️ Hotkey registration failed: {e}")
        
        self._log("start", f"authority={self.authority.value}")
    
    def stop(self):
        """Stop Jarvis."""
        self._running = False
        try:
            import keyboard
            keyboard.remove_hotkey(self.hotkey)
        except Exception:
            pass
        print("\n  🛑 Jarvis stopped.\n")
        self._log("stop", "")
    
    def _on_hotkey(self):
        """Called when hotkey is pressed."""
        print("\n  ⚡ Hotkey triggered — analyzing...\n")
        result = self.insight()
        print(result.display())
    
    # ═════════════════════════════════════
    # REPL (Interactive Mode)
    # ═════════════════════════════════════
    
    def repl(self):
        """Interactive command loop."""
        self.start()
        
        while self._running:
            try:
                cmd = input("jarvis> ").strip().lower()
                
                if cmd in ("quit", "exit", "q"):
                    self.stop()
                    break
                elif cmd in ("insight", "i", ""):
                    result = self.insight()
                    # Inject prediction into result for display
                    result._prediction = self._last_prediction
                    print(result.display())
                elif cmd.startswith("guide ") or cmd.startswith("g "):
                    n = int(cmd.split()[-1])
                    self.guide(n)
                elif cmd.startswith("assist ") or cmd.startswith("a "):
                    n = int(cmd.split()[-1])
                    self.assist(n)
                elif cmd in ("flow", "f"):
                    # Session flow summary
                    summary = self.session.get_workflow_summary()
                    workflow = self.session.detect_workflow()
                    print(f"  📊 Session flow: {summary}")
                    if workflow:
                        print(f"  🔄 Detected workflow: {workflow}")
                    if self._last_prediction:
                        p = self._last_prediction
                        print(f"  🔮 Next predicted: {p['action']} ({p['source']})")
                elif cmd == "memory":
                    apps = self.memory.list_apps()
                    print(f"  Apps with memory: {apps}")
                elif cmd.startswith("memory "):
                    app = cmd.split(None, 1)[1]
                    profile = self.memory.get_app_profile(app)
                    print(f"  Memory for {app}: {json.dumps(profile, indent=2)}")
                elif cmd == "status":
                    print(f"  Authority: {self.authority.value}")
                    print(f"  Sessions: {len(self._session_log)}")
                    print(f"  Session steps: {len(self.session._chain)}")
                    if self._last_insight:
                        print(f"  Last app: {self._last_insight.app_name}")
                    if self._last_prediction:
                        print(f"  Next prediction: {self._last_prediction['action']}")
                elif cmd.startswith("fail "):
                    why = cmd.split(None, 1)[1]
                    app = self._last_insight.app_name if self._last_insight else "unknown"
                    r = self.log_failure(app, "unknown", "better help", "see log", why)
                    print(f"  📝 Failure logged ({r['total']} total)")
                elif cmd == "failures":
                    summary = self.failure_summary()
                    print(f"  Total failures: {summary['total']}")
                    if summary.get('worst_apps'):
                        print("  Worst apps:")
                        for a in summary['worst_apps']:
                            print(f"    {a['app']}: {a['failures']}")
                    if summary.get('top_reasons'):
                        print("  Top reasons:")
                        for r in summary['top_reasons']:
                            print(f"    {r['reason']}: {r['count']}")
                elif cmd == "help":
                    print("  insight (i)     — Analyze current screen + predict next")
                    print("  guide N (g N)   — Step-by-step guide for suggestion N")
                    print("  assist N (a N)  — Execute suggestion N (safe only)")
                    print("  flow (f)        — Show session flow + workflow detection")
                    print("  memory          — Show app memory")
                    print("  fail <reason>   — Log a failure")
                    print("  failures        — Show failure patterns")
                    print("  status          — Show Jarvis status")
                    print("  quit (q)        — Stop Jarvis")
                else:
                    print(f"  Unknown: '{cmd}'. Type 'help' for commands.")
            
            except KeyboardInterrupt:
                self.stop()
                break
            except Exception as e:
                print(f"  Error: {e}")
    
    def _log(self, action: str, detail: str):
        self._session_log.append({
            "action": action, "detail": detail,
            "time": datetime.now().isoformat()
        })
    
    # ═════════════════════════════════════
    # FAILURE LOGGING (Self-Improvement)
    # ═════════════════════════════════════
    
    def log_failure(self, app: str, screen_type: str, 
                    expected: str, actual: str, why: str) -> Dict:
        """
        Record a failure for post-mortem analysis.
        After 50 failures, you know exactly what to fix.
        
        Args:
            app: What app was active
            screen_type: What kind of screen (settings, editor, dialog, etc.)
            expected: What help was expected
            actual: What Jarvis actually did
            why: Why it failed
        """
        entry = {
            "app": app,
            "screen_type": screen_type,
            "expected": expected,
            "actual": actual,
            "why": why,
            "time": datetime.now().isoformat(),
            "last_insight": {
                "app": self._last_insight.app_name if self._last_insight else None,
                "confidence": self._last_insight.confidence.value if self._last_insight else None,
                "context": self._last_insight.context_summary if self._last_insight else None,
            }
        }
        
        try:
            with open(self._failure_log_path, 'a') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception:
            pass
        
        self._log("failure", f"{app}: {why}")
        return {"logged": True, "total": self.failure_count()}
    
    def failure_count(self) -> int:
        """How many failures logged."""
        try:
            if os.path.exists(self._failure_log_path):
                with open(self._failure_log_path) as f:
                    return sum(1 for _ in f)
        except Exception:
            pass
        return 0
    
    def failure_summary(self) -> Dict:
        """Analyze failure patterns."""
        if not os.path.exists(self._failure_log_path):
            return {"total": 0, "message": "No failures logged yet."}
        
        apps = {}
        reasons = {}
        total = 0
        
        try:
            with open(self._failure_log_path) as f:
                for line in f:
                    entry = json.loads(line.strip())
                    total += 1
                    app = entry.get("app", "unknown")
                    why = entry.get("why", "unknown")
                    apps[app] = apps.get(app, 0) + 1
                    reasons[why] = reasons.get(why, 0) + 1
        except Exception:
            pass
        
        top_apps = sorted(apps.items(), key=lambda x: -x[1])[:5]
        top_reasons = sorted(reasons.items(), key=lambda x: -x[1])[:5]
        
        return {
            "total": total,
            "worst_apps": [{"app": a, "failures": c} for a, c in top_apps],
            "top_reasons": [{"reason": r, "count": c} for r, c in top_reasons],
        }
