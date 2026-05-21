"""
screen_intelligence.py — Agent's Eyes for Desktop.
OCR + Layout + Change Detection + Gaming HUD Analysis.
Pure perception. Zero write access.
"""
import os, time, hashlib, re
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False
try:
    import easyocr
    HAS_EASYOCR = True
except ImportError:
    HAS_EASYOCR = False


class ScreenIntelligence:
    """Screen capture, OCR, and UI layout analysis (read-only)."""
    
    name = "screen_vision"
    description = "Screen capture, OCR, and UI layout analysis (read-only)"
    
    def __init__(self, screenshot_dir: str = None):
        self._dir = screenshot_dir or os.path.join(os.path.expanduser("~"), "agent_screenshots")
        os.makedirs(self._dir, exist_ok=True)
        self._last_screenshot = None
        self._last_hash = ""
        self._ocr_reader = None
        if HAS_TESSERACT:
            self._ocr_method = "tesseract"
        elif HAS_EASYOCR:
            self._ocr_method = "easyocr"
        else:
            self._ocr_method = "none"
    
    def run(self, action: str, **kwargs) -> Any:
        dispatch = {
            "capture": lambda: self._capture(kwargs.get("region")),
            "read_text": lambda: self._read_text(kwargs.get("region")),
            "analyze_screen": lambda: self._analyze_screen(kwargs.get("region")),
            "detect_changes": self._detect_changes,
            "read_region": lambda: self._read_text(
                {"x": kwargs.get("x",0), "y": kwargs.get("y",0),
                 "width": kwargs.get("width",200), "height": kwargs.get("height",200)}
            ),
            "find_text_on_screen": lambda: self._find_text(kwargs.get("text","")),
            "get_color_at": lambda: self._get_color(kwargs.get("x",0), kwargs.get("y",0)),
            "analyze_game_hud": lambda: self._analyze_game_hud(kwargs.get("game","")),
        }
        fn = dispatch.get(action)
        if not fn:
            return {"error": f"Unknown action: {action}"}
        return fn()
    
    def _capture(self, region: Dict = None) -> Dict:
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui required"}
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self._dir, f"screen_{ts}.png")
        try:
            if region:
                shot = pyautogui.screenshot(region=(region["x"], region["y"], region["width"], region["height"]))
            else:
                shot = pyautogui.screenshot()
            shot.save(path)
            self._last_screenshot = shot
            self._last_hash = hashlib.md5(shot.tobytes()[:10000]).hexdigest()
            return {"success": True, "path": path, "size": {"width": shot.width, "height": shot.height}, "hash": self._last_hash}
        except Exception as e:
            return {"error": str(e)}
    
    def _do_ocr(self, image) -> Dict:
        if self._ocr_method == "tesseract":
            try:
                text = pytesseract.image_to_string(image)
                data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
                blocks = [
                    {"text": data["text"][i], "x": data["left"][i], "y": data["top"][i],
                     "width": data["width"][i], "height": data["height"][i],
                     "confidence": round(float(data["conf"][i])/100, 2)}
                    for i in range(len(data["text"])) if data["text"][i].strip()
                ]
                return {"text": text.strip(), "blocks": blocks, "method": "tesseract"}
            except Exception as e:
                return {"error": str(e)}
        elif self._ocr_method == "easyocr":
            try:
                if not self._ocr_reader:
                    self._ocr_reader = easyocr.Reader(['en'], gpu=False)
                import numpy as np
                results = self._ocr_reader.readtext(np.array(image))
                blocks = []
                texts = []
                for bbox, text, conf in results:
                    x = int(min(p[0] for p in bbox))
                    y = int(min(p[1] for p in bbox))
                    blocks.append({"text": text, "x": x, "y": y,
                                   "width": int(max(p[0] for p in bbox)) - x,
                                   "height": int(max(p[1] for p in bbox)) - y,
                                   "confidence": round(conf, 2)})
                    texts.append(text)
                return {"text": " ".join(texts), "blocks": blocks, "method": "easyocr"}
            except Exception as e:
                return {"error": str(e)}
        return {"error": "No OCR engine. Install pytesseract or easyocr."}
    
    def _read_text(self, region: Dict = None) -> Dict:
        cap = self._capture(region)
        if "error" in cap:
            return cap
        if self._ocr_method == "none":
            return {"error": "No OCR engine available", "screenshot": cap["path"]}
        return self._do_ocr(self._last_screenshot)
    
    def _analyze_screen(self, region: Dict = None) -> Dict:
        cap = self._capture(region)
        if "error" in cap:
            return cap
        result = {"screenshot": cap["path"], "size": cap["size"], "hash": cap["hash"]}
        if self._ocr_method != "none":
            ocr = self._do_ocr(self._last_screenshot)
            result["text"] = ocr.get("text", "")
            result["text_blocks"] = ocr.get("blocks", [])
        else:
            result["text"] = "(OCR not available)"
        return result
    
    def _detect_changes(self) -> Dict:
        old_hash = self._last_hash
        cap = self._capture()
        if "error" in cap:
            return cap
        return {"changed": old_hash != cap["hash"], "old_hash": old_hash, "new_hash": cap["hash"]}
    
    def _find_text(self, text: str) -> Dict:
        read = self._read_text()
        if "error" in read:
            return read
        text_lower = text.lower()
        found = [
            {"text": b["text"], "x": b["x"], "y": b["y"],
             "center_x": b["x"] + b.get("width",0)//2, "center_y": b["y"] + b.get("height",0)//2}
            for b in read.get("blocks", []) if text_lower in b["text"].lower()
        ]
        return {"found": len(found) > 0, "matches": found, "count": len(found)}
    
    def _get_color(self, x: int, y: int) -> Dict:
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui required"}
        try:
            p = pyautogui.pixel(x, y)
            return {"x": x, "y": y, "r": p[0], "g": p[1], "b": p[2], "hex": f"#{p[0]:02x}{p[1]:02x}{p[2]:02x}"}
        except Exception as e:
            return {"error": str(e)}
    
    def _analyze_game_hud(self, game: str = "") -> Dict:
        cap = self._capture()
        if "error" in cap or not self._last_screenshot or not HAS_PIL:
            return cap if "error" in (cap or {}) else {"error": "PIL required"}
        w, h = self._last_screenshot.width, self._last_screenshot.height
        hud = {"screenshot": cap["path"], "screen_size": {"width": w, "height": h}}
        
        # Health zone analysis (top-left quadrant)
        red, green = 0, 0
        for xs in range(0, w//4, 5):
            for ys in range(0, h//10, 5):
                try:
                    r, g, b = self._last_screenshot.getpixel((xs, ys))[:3]
                    if r > 150 and g < 100 and b < 100: red += 1
                    if g > 150 and r < 100 and b < 100: green += 1
                except: pass
        hud["health_indicators"] = {"red_pixels": red, "green_pixels": green, "health_warning": red > green and red > 10}
        
        if self._ocr_method != "none":
            top = self._last_screenshot.crop((0, 0, w, h//10))
            ocr = self._do_ocr(top)
            hud["hud_text"] = ocr.get("text", "")
            hud["detected_numbers"] = [int(n) for n in re.findall(r'\d+', ocr.get("text",""))[:10]]
        return hud
