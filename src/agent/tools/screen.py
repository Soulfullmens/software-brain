"""
screen.py

The 'Eyes' of the Agent.
Captures desktop state.
"""
import time
from pathlib import Path
from datetime import datetime
from ..tool import Tool

try:
    import pyautogui
    HAS_GUI = True
except ImportError:
    HAS_GUI = False

class ScreenTool(Tool):
    name = "screen_vision"
    description = "Capture the current screen state. Returns path to saved image."
    
    def run(self, action: str = "capture", **kwargs) -> str:
        if not HAS_GUI:
            return "Error: `pyautogui` library not found."
            
        if action == "capture":
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screen_{timestamp}.png"
            
            # Save to a dedicated screenshots dir? 
            # For now, save to current working dir or temp?
            # User wants me to SEE it. Artifacts dir is best.
            # But I don't know the artifacts dir path dynamically here easily without config.
            # I'll save to a local 'screenshots' folder.
            save_dir = Path("screenshots")
            save_dir.mkdir(exist_ok=True)
            path = save_dir / filename
            
            try:
                pyautogui.screenshot(str(path))
                return str(path.absolute())
            except Exception as e:
                return f"Error capturing screen: {e}"
        
        return f"Error: Unknown action '{action}'"
