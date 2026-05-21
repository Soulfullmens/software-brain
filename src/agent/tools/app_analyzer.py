"""
app_analyzer.py — Passive Application Analysis.

Understands application UIs WITHOUT interacting with them.
Reads window titles, menus, visible text — then explains.

CAPABILITIES:
  • Identify what app is running (by window title/process)
  • Map visible UI elements (via screen intelligence)
  • Explain application functionality to user
  • Guide user through features they haven't discovered
  • Track app usage patterns

DOES NOT:
  • Click anything
  • Modify any settings
  • Access app internals
  • Read app data/files
"""
import os, time, subprocess, re
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field

# Known application signatures
APP_DATABASE = {
    # Process name → app info
    "chrome.exe": {
        "name": "Google Chrome", "category": "browser",
        "features": ["tabs", "bookmarks", "extensions", "dev_tools", "incognito"],
        "tips": ["Ctrl+T: new tab", "Ctrl+Shift+N: incognito", "F12: dev tools",
                 "Ctrl+L: address bar", "Ctrl+W: close tab"],
    },
    "msedge.exe": {
        "name": "Microsoft Edge", "category": "browser",
        "features": ["tabs", "collections", "vertical_tabs", "web_capture"],
        "tips": ["Ctrl+Shift+B: toggle bookmarks", "Ctrl+Shift+O: collections"],
    },
    "code.exe": {
        "name": "VS Code", "category": "development",
        "features": ["editor", "terminal", "extensions", "git", "debug", "search"],
        "tips": ["Ctrl+Shift+P: command palette", "Ctrl+`: terminal",
                 "Ctrl+P: quick open", "Ctrl+Shift+F: search all files"],
    },
    "explorer.exe": {
        "name": "File Explorer", "category": "file_manager",
        "features": ["browse", "search", "copy", "move", "delete", "properties"],
        "tips": ["Alt+D: address bar", "Ctrl+E: search", "Alt+Enter: properties"],
    },
    "notepad.exe": {
        "name": "Notepad", "category": "text_editor",
        "features": ["edit", "save", "find", "replace"],
        "tips": ["Ctrl+G: go to line", "Ctrl+H: find and replace"],
    },
    "WINWORD.EXE": {
        "name": "Microsoft Word", "category": "office",
        "features": ["document", "formatting", "review", "track_changes", "export"],
        "tips": ["Ctrl+Shift+S: styles", "F7: spell check", "Ctrl+Enter: page break"],
    },
    "EXCEL.EXE": {
        "name": "Microsoft Excel", "category": "office",
        "features": ["spreadsheet", "formulas", "charts", "pivot_tables", "macros"],
        "tips": ["Ctrl+;: insert date", "Ctrl+Shift+;: insert time", "Alt+=: autosum"],
    },
    "POWERPNT.EXE": {
        "name": "Microsoft PowerPoint", "category": "office",
        "features": ["slides", "animations", "transitions", "presenter_view"],
        "tips": ["F5: present", "Shift+F5: present from current", "Ctrl+M: new slide"],
    },
    "Discord.exe": {
        "name": "Discord", "category": "communication",
        "features": ["voice", "text", "screen_share", "servers", "bots"],
        "tips": ["Ctrl+Shift+M: mute", "Ctrl+Shift+D: deafen"],
    },
    "spotify.exe": {
        "name": "Spotify", "category": "media",
        "features": ["music", "playlists", "podcasts", "radio"],
        "tips": ["Space: play/pause", "Ctrl+Right: next", "Ctrl+Up: volume up"],
    },
}


class AppAnalyzer:
    """Passive application analysis — understand without touching."""
    
    name = "app_analyzer"
    description = "Analyze running applications — explain features, guide users"
    
    def __init__(self):
        self._analysis_cache: Dict[str, Dict] = {}
        self._usage_log: List[Dict] = []
    
    def run(self, action: str, **kwargs) -> Any:
        actions = {
            "identify_app": lambda: self._identify_app(kwargs.get("process", "") or kwargs.get("title", "")),
            "explain_app": lambda: self._explain_app(kwargs.get("process", "") or kwargs.get("title", "")),
            "get_tips": lambda: self._get_tips(kwargs.get("process", "")),
            "list_known_apps": lambda: self._list_known(),
            "analyze_focused": self._analyze_focused_app,
            "suggest_shortcuts": lambda: self._suggest_shortcuts(kwargs.get("process", "")),
            "detect_category": lambda: self._detect_category(kwargs.get("process", "")),
        }
        fn = actions.get(action)
        if not fn:
            return {"error": f"Unknown action: {action}"}
        return fn()
    
    def _identify_app(self, query: str) -> Dict:
        """Identify an application by process name or window title."""
        query_lower = query.lower()
        for proc, info in APP_DATABASE.items():
            if proc.lower() == query_lower or info["name"].lower() in query_lower:
                return {"found": True, "process": proc, **info}
        
        # Heuristic: guess from window title
        if any(w in query_lower for w in ["browser", "chrome", "edge", "firefox"]):
            return {"found": True, "category": "browser", "name": query, "features": ["tabs", "navigation"]}
        if any(w in query_lower for w in [".py", ".js", ".ts", "code", "editor"]):
            return {"found": True, "category": "development", "name": query}
        
        return {"found": False, "query": query, "hint": "Not in database — screen analysis needed"}
    
    def _explain_app(self, query: str) -> Dict:
        """Explain what an application does and its key features."""
        app = self._identify_app(query)
        if not app.get("found"):
            return {"explanation": f"I don't have detailed info about '{query}'. I can analyze it visually if you'd like."}
        
        name = app.get("name", query)
        category = app.get("category", "unknown")
        features = app.get("features", [])
        
        explanation = f"**{name}** ({category})\n\n"
        explanation += f"**Features:** {', '.join(features)}\n\n"
        
        tips = app.get("tips", [])
        if tips:
            explanation += "**Shortcuts:**\n"
            for tip in tips:
                explanation += f"  • {tip}\n"
        
        return {"app": name, "category": category, "features": features, "explanation": explanation}
    
    def _get_tips(self, process: str) -> Dict:
        """Get productivity tips for an application."""
        for proc, info in APP_DATABASE.items():
            if proc.lower() == process.lower():
                return {"app": info["name"], "tips": info.get("tips", []), "features": info.get("features", [])}
        return {"tips": [], "hint": "App not in database"}
    
    def _list_known(self) -> List[Dict]:
        """List all known applications."""
        return [{"process": p, "name": i["name"], "category": i["category"]} for p, i in APP_DATABASE.items()]
    
    def _analyze_focused_app(self) -> Dict:
        """Analyze the currently focused application."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            
            # Get process name
            pid_buf = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_buf))
            pid = pid_buf.value
            
            proc_name = ""
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True, timeout=3
                )
                parts = result.stdout.strip().strip('"').split('","')
                if parts:
                    proc_name = parts[0]
            except Exception:
                pass
            
            app_info = self._identify_app(proc_name or title)
            app_info["window_title"] = title
            app_info["pid"] = pid
            app_info["process_name"] = proc_name
            
            self._usage_log.append({"app": proc_name or title, "time": datetime.now().isoformat()})
            return app_info
        except Exception as e:
            return {"error": str(e)}
    
    def _suggest_shortcuts(self, process: str) -> Dict:
        """Suggest keyboard shortcuts based on what user is doing."""
        tips = self._get_tips(process)
        if tips.get("tips"):
            return {"shortcuts": tips["tips"], "app": process}
        
        # Universal shortcuts
        return {
            "shortcuts": [
                "Ctrl+C: Copy", "Ctrl+V: Paste", "Ctrl+Z: Undo",
                "Ctrl+S: Save", "Ctrl+F: Find", "Alt+Tab: Switch apps",
                "Win+D: Desktop", "Win+E: File Explorer",
                "Ctrl+Shift+Esc: Task Manager",
            ],
            "app": "universal"
        }
    
    def _detect_category(self, process: str) -> Dict:
        """Detect category of an application."""
        app = self._identify_app(process)
        return {"category": app.get("category", "unknown"), "process": process}
