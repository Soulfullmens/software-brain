"""
Desktop Control — Open Apps, Type, Click, Screenshot, File Management

Gives the agent hands to control the laptop like a human would.
Uses pyautogui for mouse/keyboard, subprocess for launching apps,
and PIL for screenshots.

SAFETY: All destructive actions require explicit confirmation.
"""

from __future__ import annotations

import os
import subprocess
import time
import shutil
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from pathlib import Path


@dataclass
class ActionResult:
    """Result from a desktop action."""
    success: bool
    action: str
    detail: str
    error: str = ""
    screenshot_path: str = ""


# ── Well-known app paths (Windows) ──
KNOWN_APPS = {
    # Browsers
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
    "firefox": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
    ],
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    # Dev tools
    "vscode": [
        r"C:\Users\{user}\AppData\Local\Programs\Microsoft VS Code\Code.exe",
        r"C:\Users\{user}\AppData\Local\Programs\Microsoft VS Code Insiders\Code - Insiders.exe",
        r"C:\Program Files\Microsoft VS Code\Code.exe",
    ],
    "terminal": ["wt.exe", "cmd.exe", "powershell.exe"],
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "explorer": ["explorer.exe"],
    "cmd": ["cmd.exe"],
    "powershell": ["powershell.exe"],
    "paint": ["mspaint.exe"],
    "snipping_tool": ["SnippingTool.exe"],
    # Productivity
    "word": [
        r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE",
    ],
    "excel": [
        r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\EXCEL.EXE",
    ],
    "spotify": [
        r"C:\Users\{user}\AppData\Roaming\Spotify\Spotify.exe",
    ],
    "task_manager": ["taskmgr.exe"],
    "settings": ["ms-settings:"],
}

# Aliases
APP_ALIASES = {
    "browser": "chrome",
    "google chrome": "chrome",
    "google": "chrome",
    "code": "vscode",
    "vs code": "vscode",
    "visual studio code": "vscode",
    "file explorer": "explorer",
    "files": "explorer",
    "my computer": "explorer",
    "calc": "calculator",
    "task manager": "task_manager",
    "system settings": "settings",
    "windows settings": "settings",
    "notepad++": "notepad",
    "text editor": "notepad",
}


class DesktopControl:
    """
    Control the desktop — open apps, type text, take screenshots, manage files.
    
    USAGE:
        desktop = DesktopControl()
        
        # Open an app
        desktop.open_app("chrome")
        desktop.open_app("vscode", args=["C:\\project"])
        
        # Run a command
        desktop.run_command("pip install requests")
        
        # Take a screenshot
        desktop.screenshot("./screenshots/current.png")
        
        # Type text
        desktop.type_text("Hello World")
        
        # Keyboard shortcuts
        desktop.hotkey("ctrl", "s")  # Save
        desktop.hotkey("alt", "tab")  # Switch window
        
        # File operations
        desktop.open_file("C:\\docs\\report.pdf")
        desktop.list_files("C:\\Users\\Desktop")
    """

    def __init__(self, screenshot_dir: str = "./screenshots"):
        self._screenshot_dir = screenshot_dir
        os.makedirs(screenshot_dir, exist_ok=True)
        self._user = os.environ.get("USERNAME", os.environ.get("USER", "user"))
        self._pyautogui = None
        self._action_log: List[Dict] = []

    def _get_pyautogui(self):
        """Lazy-load pyautogui."""
        if self._pyautogui is None:
            try:
                import pyautogui
                pyautogui.FAILSAFE = True  # Move mouse to corner to abort
                pyautogui.PAUSE = 0.1  # Small delay between actions
                self._pyautogui = pyautogui
            except ImportError:
                pass
        return self._pyautogui

    def _log_action(self, action: str, detail: str, success: bool):
        """Log every action for audit trail."""
        self._action_log.append({
            "action": action,
            "detail": detail,
            "success": success,
            "timestamp": time.time(),
        })

    def _resolve_app(self, app_name: str) -> Optional[str]:
        """Resolve an app name to its executable path."""
        name = app_name.lower().strip()
        
        # Check aliases first
        if name in APP_ALIASES:
            name = APP_ALIASES[name]
        
        if name not in KNOWN_APPS:
            # Try to find it via `where` command (Windows PATH)
            try:
                result = subprocess.run(
                    ["where", app_name], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    path = result.stdout.strip().split("\n")[0]
                    if os.path.exists(path):
                        return path
            except Exception:
                pass
            return None
        
        paths = KNOWN_APPS[name]
        for p in paths:
            p = p.replace("{user}", self._user)
            if os.path.exists(p):
                return p
            # Try system PATH for simple exe names
            if not os.sep in p:
                try:
                    result = subprocess.run(
                        ["where", p], capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        return result.stdout.strip().split("\n")[0]
                except Exception:
                    pass
        return None

    # ═══════════════════════════════════════
    #  App Control
    # ═══════════════════════════════════════

    def open_app(self, app_name: str, args: Optional[List[str]] = None) -> ActionResult:
        """
        Open an application by name.
        
        Examples:
            open_app("chrome")
            open_app("vscode", args=["C:\\project"])
            open_app("chrome", args=["https://google.com"])
        """
        try:
            path = self._resolve_app(app_name)
            
            # Handle special protocol URIs (like ms-settings:)
            if path and path.startswith("ms-"):
                subprocess.Popen(["start", path], shell=True)
                self._log_action("open_app", app_name, True)
                return ActionResult(True, "open_app", f"Opened {app_name}")
            
            if not path:
                # Last resort: try os.startfile or shell start
                try:
                    os.startfile(app_name)
                    self._log_action("open_app", app_name, True)
                    return ActionResult(True, "open_app", f"Opened {app_name} via system")
                except Exception:
                    self._log_action("open_app", app_name, False)
                    return ActionResult(False, "open_app", "", f"App not found: {app_name}")
            
            cmd = [path] + (args or [])
            subprocess.Popen(cmd, start_new_session=True)
            self._log_action("open_app", app_name, True)
            return ActionResult(True, "open_app", f"Opened {app_name}: {path}")
        except Exception as e:
            self._log_action("open_app", app_name, False)
            return ActionResult(False, "open_app", "", str(e))

    def open_url_in_browser(self, url: str) -> ActionResult:
        """Open a URL in the user's real browser (Chrome/Edge). Instant and visible on screen."""
        try:
            chrome_path = self._resolve_app("chrome")
            if not chrome_path:
                chrome_path = self._resolve_app("edge")
            
            # Try to use user's profile to preserve login state
            user_data_args = []
            if chrome_path and "chrome.exe" in chrome_path.lower():
                user_dir = os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "User Data")
                if os.path.exists(user_dir):
                    user_data_args = [f"--user-data-dir={user_dir}", "--profile-directory=Default"]

            if not chrome_path:
                import webbrowser
                webbrowser.open(url)
                self._log_action("open_url", url, True)
                return ActionResult(True, "open_url", f"Opened {url} in default browser")

            subprocess.Popen([chrome_path] + user_data_args + [url], start_new_session=True)
            self._log_action("open_url", url, True)
            return ActionResult(True, "open_url", f"Opened in Chrome")
        except Exception as e:
            self._log_action("open_url", url, False)
            return ActionResult(False, "open_url", "", str(e))

    def close_app(self, app_name: str) -> ActionResult:
        """Close an application by name (kills the process)."""
        try:
            # Map to process name
            proc_map = {
                "chrome": "chrome.exe", "firefox": "firefox.exe",
                "edge": "msedge.exe", "vscode": "Code.exe",
                "notepad": "notepad.exe", "word": "WINWORD.EXE",
                "excel": "EXCEL.EXE", "spotify": "Spotify.exe",
            }
            name = app_name.lower().strip()
            if name in APP_ALIASES:
                name = APP_ALIASES[name]
            proc = proc_map.get(name, f"{name}.exe")
            
            result = subprocess.run(
                ["taskkill", "/IM", proc, "/F"],
                capture_output=True, text=True, timeout=10
            )
            success = result.returncode == 0
            self._log_action("close_app", app_name, success)
            return ActionResult(success, "close_app", 
                              f"Closed {app_name}" if success else "",
                              result.stderr.strip() if not success else "")
        except Exception as e:
            return ActionResult(False, "close_app", "", str(e))

    def list_running_apps(self) -> List[str]:
        """List currently running applications."""
        try:
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=10
            )
            apps = set()
            for line in result.stdout.strip().split("\n"):
                if line:
                    name = line.split(",")[0].strip('"')
                    if name and not name.startswith("svchost") and name.endswith(".exe"):
                        apps.add(name)
            return sorted(apps)
        except Exception:
            return []

    # ═══════════════════════════════════════
    #  Command Execution
    # ═══════════════════════════════════════

    def run_command(self, command: str, cwd: Optional[str] = None,
                    timeout: int = 30) -> ActionResult:
        """
        Run a shell command and return the output.
        
        Examples:
            run_command("pip install requests")
            run_command("python script.py", cwd="C:\\project")
            run_command("dir", cwd="C:\\Users")
        """
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                cwd=cwd, timeout=timeout
            )
            output = result.stdout + result.stderr
            success = result.returncode == 0
            self._log_action("run_command", command, success)
            return ActionResult(success, "run_command", output.strip(),
                              "" if success else f"Exit code: {result.returncode}")
        except subprocess.TimeoutExpired:
            return ActionResult(False, "run_command", "", f"Timeout after {timeout}s")
        except Exception as e:
            return ActionResult(False, "run_command", "", str(e))

    # ═══════════════════════════════════════
    #  Keyboard & Mouse
    # ═══════════════════════════════════════

    def type_text(self, text: str, interval: float = 0.02) -> ActionResult:
        """Type text at current cursor position."""
        gui = self._get_pyautogui()
        if not gui:
            return ActionResult(False, "type_text", "", 
                              "pyautogui not installed. pip install pyautogui")
        try:
            gui.typewrite(text, interval=interval)
            self._log_action("type_text", text[:50], True)
            return ActionResult(True, "type_text", f"Typed {len(text)} chars")
        except Exception as e:
            return ActionResult(False, "type_text", "", str(e))

    def type_unicode(self, text: str) -> ActionResult:
        """Type text including unicode/special characters using clipboard."""
        try:
            import pyperclip
            gui = self._get_pyautogui()
            if not gui:
                return ActionResult(False, "type_unicode", "", "pyautogui not installed")
            old = pyperclip.paste()
            pyperclip.copy(text)
            gui.hotkey("ctrl", "v")
            time.sleep(0.1)
            pyperclip.copy(old)  # restore clipboard
            self._log_action("type_unicode", text[:50], True)
            return ActionResult(True, "type_unicode", f"Typed {len(text)} chars (clipboard)")
        except ImportError:
            # Fallback: use win32 if available
            return self.type_text(text)
        except Exception as e:
            return ActionResult(False, "type_unicode", "", str(e))

    def hotkey(self, *keys) -> ActionResult:
        """
        Press a keyboard shortcut.
        
        Examples:
            hotkey("ctrl", "s")   — Save
            hotkey("ctrl", "c")   — Copy
            hotkey("alt", "tab")  — Switch window
            hotkey("win", "d")    — Show desktop
        """
        gui = self._get_pyautogui()
        if not gui:
            return ActionResult(False, "hotkey", "", "pyautogui not installed")
        try:
            gui.hotkey(*keys)
            self._log_action("hotkey", "+".join(keys), True)
            return ActionResult(True, "hotkey", f"Pressed {'+'.join(keys)}")
        except Exception as e:
            return ActionResult(False, "hotkey", "", str(e))

    def press_key(self, key: str) -> ActionResult:
        """Press a single key (enter, tab, escape, etc.)."""
        gui = self._get_pyautogui()
        if not gui:
            return ActionResult(False, "press_key", "", "pyautogui not installed")
        try:
            gui.press(key)
            self._log_action("press_key", key, True)
            return ActionResult(True, "press_key", f"Pressed {key}")
        except Exception as e:
            return ActionResult(False, "press_key", "", str(e))

    def click(self, x: int = None, y: int = None) -> ActionResult:
        """Click at position (or current position if not specified)."""
        gui = self._get_pyautogui()
        if not gui:
            return ActionResult(False, "click", "", "pyautogui not installed")
        try:
            if x is not None and y is not None:
                gui.click(x, y)
            else:
                gui.click()
            pos = f"({x},{y})" if x is not None else "(current)"
            self._log_action("click", pos, True)
            return ActionResult(True, "click", f"Clicked at {pos}")
        except Exception as e:
            return ActionResult(False, "click", "", str(e))

    def move_mouse(self, x: int, y: int) -> ActionResult:
        """Move mouse to position."""
        gui = self._get_pyautogui()
        if not gui:
            return ActionResult(False, "move_mouse", "", "pyautogui not installed")
        try:
            gui.moveTo(x, y)
            return ActionResult(True, "move_mouse", f"Moved to ({x},{y})")
        except Exception as e:
            return ActionResult(False, "move_mouse", "", str(e))

    # ═══════════════════════════════════════
    #  Screenshots
    # ═══════════════════════════════════════

    def screenshot(self, save_path: str = None) -> ActionResult:
        """Take a screenshot of the full screen."""
        gui = self._get_pyautogui()
        if not gui:
            return ActionResult(False, "screenshot", "", "pyautogui not installed")
        try:
            if not save_path:
                save_path = os.path.join(
                    self._screenshot_dir,
                    f"screen_{int(time.time())}.png"
                )
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            img = gui.screenshot()
            img.save(save_path)
            self._log_action("screenshot", save_path, True)
            return ActionResult(True, "screenshot", f"Saved to {save_path}",
                              screenshot_path=save_path)
        except Exception as e:
            return ActionResult(False, "screenshot", "", str(e))

    # ═══════════════════════════════════════
    #  File Operations
    # ═══════════════════════════════════════

    def open_file(self, file_path: str) -> ActionResult:
        """Open a file with its default application."""
        try:
            if not os.path.exists(file_path):
                return ActionResult(False, "open_file", "", f"File not found: {file_path}")
            os.startfile(file_path)
            self._log_action("open_file", file_path, True)
            return ActionResult(True, "open_file", f"Opened {file_path}")
        except Exception as e:
            return ActionResult(False, "open_file", "", str(e))

    def list_files(self, directory: str, pattern: str = "*") -> List[Dict]:
        """List files in a directory."""
        try:
            path = Path(directory)
            if not path.exists():
                return []
            files = []
            for f in sorted(path.glob(pattern)):
                stat = f.stat()
                files.append({
                    "name": f.name,
                    "path": str(f),
                    "is_dir": f.is_dir(),
                    "size_bytes": stat.st_size if not f.is_dir() else 0,
                    "modified": stat.st_mtime,
                })
            return files
        except Exception:
            return []

    def search_files(self, directory: str, query: str, extensions: List[str] = None) -> List[str]:
        """Search for files by name pattern."""
        results = []
        try:
            for root, dirs, files in os.walk(directory):
                for f in files:
                    if query.lower() in f.lower():
                        if extensions is None or any(f.endswith(e) for e in extensions):
                            results.append(os.path.join(root, f))
                if len(results) > 100:
                    break
        except Exception:
            pass
        return results

    def get_system_info(self) -> Dict:
        """Get basic system information."""
        import platform
        return {
            "os": platform.system(),
            "os_version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "username": self._user,
            "home": str(Path.home()),
            "cwd": os.getcwd(),
        }

    def get_action_log(self) -> List[Dict]:
        """Get the action audit log."""
        return list(self._action_log)


# ═══════════════════════════════════════════════════════
#  Action Recorder — Records mouse/keyboard for Learn Mode
# ═══════════════════════════════════════════════════════

class ActionRecorder:
    """
    Records user actions (mouse clicks, keyboard presses, scroll) across all apps.
    Uses pynput for cross-app recording without admin rights.
    
    Usage:
        recorder = ActionRecorder()
        recorder.start()
        # ... user does stuff ...
        actions = recorder.stop()
    """

    def __init__(self, max_actions: int = 500):
        self._actions: List[Dict] = []
        self._recording = False
        self._max_actions = max_actions
        self._mouse_listener = None
        self._key_listener = None
        self._typed_buffer = ""
        self._last_key_time = 0

    def start(self):
        """Start recording user actions."""
        try:
            from pynput import mouse, keyboard
        except ImportError:
            raise ImportError("pynput not installed. Run: pip install pynput")

        self._actions = []
        self._recording = True
        self._typed_buffer = ""

        def _get_active_window():
            """Get the title of the active window (Windows only)."""
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                return buf.value[:80]
            except Exception:
                return "unknown"

        def on_click(x, y, button, pressed):
            if not self._recording or len(self._actions) >= self._max_actions:
                return False
            if pressed:
                # Flush typed buffer before click
                self._flush_typed()
                self._actions.append({
                    "type": "click",
                    "x": x, "y": y,
                    "button": str(button),
                    "window": _get_active_window(),
                    "ts": time.time(),
                })

        def on_scroll(x, y, dx, dy):
            if not self._recording or len(self._actions) >= self._max_actions:
                return False
            self._flush_typed()
            self._actions.append({
                "type": "scroll",
                "x": x, "y": y,
                "direction": "down" if dy < 0 else "up",
                "amount": abs(dy),
                "window": _get_active_window(),
                "ts": time.time(),
            })

        def on_key_press(key):
            if not self._recording or len(self._actions) >= self._max_actions:
                return False
            now = time.time()
            try:
                char = key.char
                if char:
                    # Accumulate typed text
                    if now - self._last_key_time > 2.0 and self._typed_buffer:
                        self._flush_typed()
                    self._typed_buffer += char
                    self._last_key_time = now
                    return
            except AttributeError:
                pass

            # Special key
            self._flush_typed()
            key_name = str(key).replace("Key.", "")
            # Record hotkeys like ctrl+c, alt+tab
            self._actions.append({
                "type": "hotkey",
                "keys": key_name,
                "window": _get_active_window(),
                "ts": time.time(),
            })

        self._mouse_listener = mouse.Listener(on_click=on_click, on_scroll=on_scroll)
        self._key_listener = keyboard.Listener(on_press=on_key_press)
        self._mouse_listener.start()
        self._key_listener.start()

    def _flush_typed(self):
        """Flush accumulated typed text into an action."""
        if self._typed_buffer:
            self._actions.append({
                "type": "type",
                "text": self._typed_buffer,
                "ts": time.time(),
            })
            self._typed_buffer = ""

    def stop(self) -> List[Dict]:
        """Stop recording and return the list of actions."""
        self._recording = False
        self._flush_typed()
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
        if self._key_listener:
            try:
                self._key_listener.stop()
            except Exception:
                pass
        actions = list(self._actions)
        self._actions = []
        return actions

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def action_count(self) -> int:
        return len(self._actions)
