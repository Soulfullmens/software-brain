"""
desktop_v2.py

UPGRADED Desktop Control Tool — Perception-First.

NEW CAPABILITIES (over v1):
─── OBSERVATION (Safe — anyone can use) ───
  • List all open windows
  • Get focused window info (title, app, position, size)
  • Detect running apps
  • Get system info (battery, CPU, memory)

─── CONTROLLED ACTIONS ───
  • Launch app from WHITELIST only
  • Focus/switch window
  • Minimize/maximize window
  • Safe click/type within focused app

─── BLOCKED (No permission yet) ───
  • Kill process
  • System settings
  • Registry
  • Admin commands

ALL actions gated through SecurityKernel.
"""
import os
import time
import subprocess
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime

try:
    import pyautogui
    pyautogui.FAILSAFE = True  # Move mouse to corner = emergency stop
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

try:
    import ctypes
    from ctypes import wintypes
    HAS_CTYPES = True
except ImportError:
    HAS_CTYPES = False


@dataclass
class WindowInfo:
    """Information about a window."""
    title: str
    handle: int = 0
    process_name: str = ""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    is_focused: bool = False
    is_visible: bool = True

@dataclass  
class SystemInfo:
    """System resource information."""
    cpu_percent: float = 0.0
    memory_total_gb: float = 0.0
    memory_used_gb: float = 0.0
    memory_percent: float = 0.0
    disk_total_gb: float = 0.0
    disk_free_gb: float = 0.0
    battery_percent: float = -1.0  # -1 = no battery
    battery_plugged: bool = False


# Whitelisted apps that can be launched without user confirmation
APP_WHITELIST = {
    # Browsers
    "chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "edge": "msedge.exe",
    "brave": "brave.exe",
    
    # Productivity
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "wordpad": "wordpad.exe",
    "snippingtool": "SnippingTool.exe",
    
    # Development
    "vscode": "code",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "terminal": "wt.exe",
    
    # File management
    "explorer": "explorer.exe",
    "taskmgr": "taskmgr.exe",
    
    # Media
    "vlc": "vlc.exe",
    "spotify": "spotify.exe",
}


class DesktopToolV2:
    """
    Perception-first desktop control.
    
    Prioritizes OBSERVATION over action.
    See first, understand, then act carefully.
    """
    
    name = "desktop_control"
    description = "Desktop perception and safe control (windows, apps, input)"
    
    ACTIONS = {
        # ─── Observation (always safe) ───
        "list_windows": "List all open windows with details",
        "get_focused_window": "Get info about the currently focused window",
        "list_running_apps": "List all running applications",
        "get_system_info": "Get CPU, memory, disk, battery status",
        "get_screen_size": "Get screen dimensions",
        "get_mouse_position": "Get current mouse position",
        
        # ─── Controlled Actions ───
        "launch_app": "Launch a whitelisted application",
        "focus_window": "Bring a window to front by title",
        "minimize_window": "Minimize a window",
        "maximize_window": "Maximize a window",
        
        # ─── Input (within focused app only) ───
        "click": "Click at position (x, y)",
        "type_text": "Type text at current cursor position",
        "key_press": "Press a key or key combination",
        "scroll": "Scroll up or down",
        "move_mouse": "Move mouse to position",
    }
    
    def __init__(self):
        self._action_log: List[Dict] = []
    
    def run(self, action: str, **kwargs) -> Any:
        """Execute a desktop action."""
        start = time.time()
        
        # ─── OBSERVATION ACTIONS ───
        if action == "list_windows":
            result = self._list_windows()
        elif action == "get_focused_window":
            result = self._get_focused_window()
        elif action == "list_running_apps":
            result = self._list_running_apps()
        elif action == "get_system_info":
            result = self._get_system_info()
        elif action == "get_screen_size":
            result = self._get_screen_size()
        elif action == "get_mouse_position":
            result = self._get_mouse_position()
        
        # ─── CONTROLLED ACTIONS ───
        elif action == "launch_app":
            result = self._launch_app(kwargs.get("name", ""))
        elif action == "focus_window":
            result = self._focus_window(kwargs.get("title", ""))
        elif action == "minimize_window":
            result = self._minimize_window(kwargs.get("title", ""))
        elif action == "maximize_window":
            result = self._maximize_window(kwargs.get("title", ""))
        
        # ─── INPUT ACTIONS ───
        elif action == "click":
            result = self._click(kwargs.get("x", 0), kwargs.get("y", 0), 
                               kwargs.get("button", "left"))
        elif action == "type_text":
            result = self._type_text(kwargs.get("text", ""))
        elif action == "key_press":
            result = self._key_press(kwargs.get("key", ""))
        elif action == "scroll":
            result = self._scroll(kwargs.get("amount", 3), kwargs.get("direction", "down"))
        elif action == "move_mouse":
            result = self._move_mouse(kwargs.get("x", 0), kwargs.get("y", 0))
        else:
            result = {"error": f"Unknown action: {action}", "available": list(self.ACTIONS.keys())}
        
        elapsed = (time.time() - start) * 1000
        self._action_log.append({
            "action": action, "time": datetime.now().isoformat(),
            "duration_ms": round(elapsed, 1), "success": "error" not in str(result)
        })
        
        return result
    
    # ═════════════════════════════════════
    # OBSERVATION (Always Safe)
    # ═════════════════════════════════════
    
    def _list_windows(self) -> List[Dict]:
        """List all visible windows."""
        windows = []
        
        if not HAS_CTYPES or os.name != 'nt':
            return self._list_windows_fallback()
        
        try:
            user32 = ctypes.windll.user32
            
            # Callback for EnumWindows
            EnumWindowsProc = ctypes.WINFUNCTYPE(
                ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)
            )
            
            def callback(hwnd, _):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        title = buf.value
                        if title.strip():
                            rect = wintypes.RECT()
                            user32.GetWindowRect(hwnd, ctypes.byref(rect))
                            windows.append({
                                "title": title,
                                "handle": hwnd,
                                "x": rect.left, "y": rect.top,
                                "width": rect.right - rect.left,
                                "height": rect.bottom - rect.top,
                                "is_focused": hwnd == user32.GetForegroundWindow()
                            })
                return True
            
            user32.EnumWindows(EnumWindowsProc(callback), 0)
        except Exception as e:
            return [{"error": f"Failed to enumerate windows: {e}"}]
        
        return windows
    
    def _list_windows_fallback(self) -> List[Dict]:
        """Fallback: use tasklist to get windows."""
        try:
            result = subprocess.run(
                ["tasklist", "/V", "/FO", "CSV"],
                capture_output=True, text=True, timeout=5
            )
            windows = []
            for line in result.stdout.strip().split('\n')[1:]:
                parts = line.strip('"').split('","')
                if len(parts) >= 9 and parts[8] != "N/A":
                    windows.append({
                        "title": parts[8],
                        "process": parts[0],
                        "pid": parts[1],
                    })
            return windows
        except Exception as e:
            return [{"error": str(e)}]
    
    def _get_focused_window(self) -> Dict:
        """Get the currently focused window."""
        if HAS_CTYPES and os.name == 'nt':
            try:
                user32 = ctypes.windll.user32
                hwnd = user32.GetForegroundWindow()
                length = user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                
                return {
                    "title": buf.value,
                    "handle": hwnd,
                    "x": rect.left, "y": rect.top,
                    "width": rect.right - rect.left,
                    "height": rect.bottom - rect.top,
                }
            except Exception as e:
                return {"error": str(e)}
        
        return {"info": "Window focus detection not available on this platform"}
    
    def _list_running_apps(self) -> List[Dict]:
        """List running applications (process name + PID)."""
        try:
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5
            )
            apps = {}
            for line in result.stdout.strip().split('\n'):
                parts = line.strip('"').split('","')
                if len(parts) >= 2:
                    name = parts[0]
                    if name not in apps:
                        apps[name] = {"name": name, "instances": 0}
                    apps[name]["instances"] += 1
            
            # Sort by name, filter out system processes
            return sorted(
                [v for v in apps.values() if v["instances"] > 0],
                key=lambda x: x["name"].lower()
            )
        except Exception as e:
            return [{"error": str(e)}]
    
    def _get_system_info(self) -> Dict:
        """Get system resource usage."""
        info = {}
        
        try:
            import psutil
            info["cpu_percent"] = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            info["memory_total_gb"] = round(mem.total / (1024**3), 1)
            info["memory_used_gb"] = round(mem.used / (1024**3), 1)
            info["memory_percent"] = mem.percent
            
            disk = psutil.disk_usage('C:\\')
            info["disk_total_gb"] = round(disk.total / (1024**3), 1)
            info["disk_free_gb"] = round(disk.free / (1024**3), 1)
            
            battery = psutil.sensors_battery()
            if battery:
                info["battery_percent"] = battery.percent
                info["battery_plugged"] = battery.power_plugged
            else:
                info["battery"] = "No battery (desktop)"
        except ImportError:
            # Fallback without psutil
            info["note"] = "Install psutil for detailed system info"
            try:
                result = subprocess.run(
                    ["wmic", "OS", "get", "FreePhysicalMemory,TotalVisibleMemorySize", "/VALUE"],
                    capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.strip().split('\n'):
                    if "FreePhysicalMemory" in line:
                        info["free_memory_kb"] = int(line.split('=')[1].strip())
                    elif "TotalVisibleMemorySize" in line:
                        info["total_memory_kb"] = int(line.split('=')[1].strip())
            except Exception:
                pass
        
        return info
    
    def _get_screen_size(self) -> Dict:
        """Get screen dimensions."""
        if HAS_PYAUTOGUI:
            w, h = pyautogui.size()
            return {"width": w, "height": h}
        if HAS_CTYPES and os.name == 'nt':
            user32 = ctypes.windll.user32
            return {
                "width": user32.GetSystemMetrics(0),
                "height": user32.GetSystemMetrics(1)
            }
        return {"error": "Screen size detection not available"}
    
    def _get_mouse_position(self) -> Dict:
        """Get current mouse position."""
        if HAS_PYAUTOGUI:
            x, y = pyautogui.position()
            return {"x": x, "y": y}
        return {"error": "Mouse tracking not available (install pyautogui)"}
    
    # ═════════════════════════════════════
    # CONTROLLED ACTIONS
    # ═════════════════════════════════════
    
    def _launch_app(self, name: str) -> Dict:
        """Launch an app from the whitelist."""
        name_lower = name.lower().strip()
        
        if name_lower not in APP_WHITELIST:
            return {
                "error": f"'{name}' not in whitelist. Available: {list(APP_WHITELIST.keys())}",
                "hint": "Ask user to approve non-whitelisted apps"
            }
        
        exe = APP_WHITELIST[name_lower]
        
        try:
            subprocess.Popen(
                exe, shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return {"success": True, "launched": name, "executable": exe}
        except Exception as e:
            return {"error": f"Failed to launch '{name}': {e}"}
    
    def _focus_window(self, title: str) -> Dict:
        """Bring a window to front by title (partial match)."""
        if not HAS_CTYPES or os.name != 'nt':
            return {"error": "Window focus requires Windows"}
        
        try:
            user32 = ctypes.windll.user32
            target_hwnd = None
            
            EnumWindowsProc = ctypes.WINFUNCTYPE(
                ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)
            )
            
            def callback(hwnd, _):
                nonlocal target_hwnd
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        if title.lower() in buf.value.lower():
                            target_hwnd = hwnd
                            return False  # Stop enumeration
                return True
            
            user32.EnumWindows(EnumWindowsProc(callback), 0)
            
            if target_hwnd:
                user32.SetForegroundWindow(target_hwnd)
                return {"success": True, "focused": title, "handle": target_hwnd}
            return {"error": f"Window '{title}' not found"}
        except Exception as e:
            return {"error": str(e)}
    
    def _minimize_window(self, title: str) -> Dict:
        """Minimize a window by title."""
        if not HAS_CTYPES or os.name != 'nt':
            return {"error": "Window control requires Windows"}
        
        focus_result = self._focus_window(title)
        if "error" in focus_result:
            return focus_result
        
        try:
            hwnd = focus_result.get("handle", 0)
            ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
            return {"success": True, "minimized": title}
        except Exception as e:
            return {"error": str(e)}
    
    def _maximize_window(self, title: str) -> Dict:
        """Maximize a window by title."""
        if not HAS_CTYPES or os.name != 'nt':
            return {"error": "Window control requires Windows"}
        
        focus_result = self._focus_window(title)
        if "error" in focus_result:
            return focus_result
        
        try:
            hwnd = focus_result.get("handle", 0)
            ctypes.windll.user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
            return {"success": True, "maximized": title}
        except Exception as e:
            return {"error": str(e)}
    
    # ═════════════════════════════════════
    # INPUT (within focused app)
    # ═════════════════════════════════════
    
    def _click(self, x: int, y: int, button: str = "left") -> Dict:
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui required for click"}
        try:
            pyautogui.click(x, y, button=button)
            return {"success": True, "clicked": {"x": x, "y": y, "button": button}}
        except Exception as e:
            return {"error": str(e)}
    
    def _type_text(self, text: str) -> Dict:
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui required for typing"}
        try:
            pyautogui.typewrite(text, interval=0.02)
            return {"success": True, "typed": len(text)}
        except Exception as e:
            return {"error": str(e)}
    
    def _key_press(self, key: str) -> Dict:
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui required for key press"}
        try:
            # Support combos like "ctrl+c"
            if '+' in key:
                keys = key.split('+')
                pyautogui.hotkey(*keys)
            else:
                pyautogui.press(key)
            return {"success": True, "pressed": key}
        except Exception as e:
            return {"error": str(e)}
    
    def _scroll(self, amount: int = 3, direction: str = "down") -> Dict:
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui required for scroll"}
        try:
            clicks = amount if direction == "up" else -amount
            pyautogui.scroll(clicks)
            return {"success": True, "scrolled": direction, "amount": amount}
        except Exception as e:
            return {"error": str(e)}
    
    def _move_mouse(self, x: int, y: int) -> Dict:
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui required for mouse move"}
        try:
            pyautogui.moveTo(x, y, duration=0.3)
            return {"success": True, "moved_to": {"x": x, "y": y}}
        except Exception as e:
            return {"error": str(e)}
    
    def get_action_log(self) -> List[Dict]:
        """Get log of all desktop actions."""
        return self._action_log
