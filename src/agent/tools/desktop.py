"""
desktop.py

The 'Hands' of the Agent.
Wraps pyautogui to provide desktop interaction primitives.
"""
import time
from typing import Any, Dict, Optional
from ..tool import Tool

try:
    import pyautogui
    # Safety: Fail-safe corner (move mouse to 0,0 to abort)
    pyautogui.FAILSAFE = True
    HAS_GUI = True
except ImportError:
    HAS_GUI = False

class DesktopTool(Tool):
    name = "desktop_control"
    description = "Control mouse and keyboard. Actions: click, double_click, right_click, type, key_press, move, scroll."
    
    def run(self, action: str, **kwargs) -> str:
        """
        Execute a desktop action.
        
        Args:
            action: One of [click, double_click, right_click, type, key_press, move, scroll]
            x, y: Coordinates (for mouse actions)
            text: Text to type (for type action)
            key: Key to press (for key_press action)
            amount: Scroll amount (for scroll action)
            duration: Animation duration in seconds (default 0.0)
        """
        if not HAS_GUI:
            return "Error: `pyautogui` library not found. Please install it."
            
        try:
            if action == "move":
                x = kwargs.get("x")
                y = kwargs.get("y")
                duration = kwargs.get("duration", 0.0)
                if x is not None and y is not None:
                    pyautogui.moveTo(x, y, duration=duration)
                    return f"Moved mouse to ({x}, {y})"
                return "Error: Missing x or y for move"

            elif action == "click":
                x = kwargs.get("x")
                y = kwargs.get("y")
                clicks = kwargs.get("clicks", 1)
                button = kwargs.get("button", "left")
                if x is not None and y is not None:
                    pyautogui.click(x, y, clicks=clicks, button=button)
                    return f"Clicked {button} at ({x}, {y})"
                else:
                    pyautogui.click(clicks=clicks, button=button)
                    return f"Clicked {button} at current position"

            elif action == "type":
                text = kwargs.get("text")
                interval = kwargs.get("interval", 0.0)
                if text:
                    pyautogui.write(text, interval=interval)
                    return f"Typed: '{text}'"
                return "Error: Missing text for type"

            elif action == "key_press":
                key = kwargs.get("key")
                keys = kwargs.get("keys") # Support multiple keys
                if keys:
                     pyautogui.hotkey(*keys)
                     return f"Pressed keys: {keys}"
                if key:
                    pyautogui.press(key)
                    return f"Pressed key: {key}"
                return "Error: Missing key for key_press"
                
            elif action == "scroll":
                amount = kwargs.get("amount", 0)
                pyautogui.scroll(amount)
                return f"Scrolled {amount}"
            
            else:
                return f"Error: Unknown action '{action}'"
                
        except Exception as e:
            return f"Error executing desktop action: {e}"
