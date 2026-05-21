"""
browser_tool.py — Advanced Screen Control Tool for NOMAD Agent

This tool gives the agent REAL control over the user's screen and browser.
Like Antigravity, the agent can:
  - Connect to the user's RUNNING Chrome browser (not a new headless one)
  - Execute JavaScript in any tab (like Chrome DevTools Console)
  - Inject CSS overrides (force fullscreen, resize elements, change colors)
  - Force video elements to fullscreen
  - Click, type, scroll on the user's visible screen
  - Take screenshots of what the user sees
  - Modify DOM elements live

Architecture:
  1. Launch Chrome with --remote-debugging-port if not already running
  2. Connect via Playwright's connect_over_cdp()
  3. Execute commands on the user's ACTUAL browser tabs
"""
import sys
import os
import json
import time
import base64
import subprocess
import socket
from typing import Dict, Any, Optional, List

# ─── Configuration ────────────────────────────────
CDP_PORT = 9222
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def _find_chrome() -> Optional[str]:
    """Find Chrome executable on the system."""
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path
    # Try 'where' on Windows or 'which' on Linux/Mac
    try:
        cmd = "where chrome" if sys.platform == "win32" else "which google-chrome"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split('\n')[0]
    except Exception:
        pass
    return None


def _is_cdp_running(port: int = CDP_PORT) -> bool:
    """Check if Chrome DevTools Protocol is already listening."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(('127.0.0.1', port))
        s.close()
        return result == 0
    except Exception:
        return False


def _launch_chrome_debug(port: int = CDP_PORT) -> bool:
    """Launch Chrome with remote debugging enabled."""
    chrome = _find_chrome()
    if not chrome:
        return False
    try:
        subprocess.Popen(
            [chrome, f"--remote-debugging-port={port}", "--no-first-run", "--no-default-browser-check"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        # Wait for CDP to become available
        for _ in range(10):
            time.sleep(0.5)
            if _is_cdp_running(port):
                return True
        return False
    except Exception:
        return False


def _get_playwright_browser(port: int = CDP_PORT):
    """Connect to the user's running Chrome via CDP."""
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        return pw, browser
    except Exception as e:
        raise RuntimeError(f"Cannot connect to Chrome CDP on port {port}: {e}")


# ═══════════════════════════════════════════════════════
# MAIN TOOL: execute_browser
# ═══════════════════════════════════════════════════════

def execute_browser(params: Dict[str, Any]) -> str:
    """
    Multi-action browser control tool.
    
    Actions:
      navigate     - Open a URL in the browser
      screenshot   - Take a screenshot of the current page
      run_js       - Execute JavaScript in the current page (like Chrome Console)
      inject_css   - Inject CSS into the current page
      fullscreen_video - Force any <video> element to fullscreen
      click        - Click at specific coordinates or CSS selector
      type_text    - Type text into an element
      get_page_info - Get title, URL, and DOM summary of current page
      list_tabs    - List all open tabs
      switch_tab   - Switch to a specific tab by index
    """
    action = params.get('action', 'navigate')
    url = params.get('url', '')
    js_code = params.get('js_code', params.get('code', ''))
    css_code = params.get('css_code', params.get('css', ''))
    selector = params.get('selector', '')
    text = params.get('text', '')
    tab_index = params.get('tab_index', 0)
    
    # ── Ensure Chrome is running with CDP ──
    if not _is_cdp_running():
        launched = _launch_chrome_debug()
        if not launched:
            # Fallback: just open in default browser
            if action == 'navigate' and url:
                import webbrowser
                webbrowser.open(url)
                return f"Opened {url} in default browser (Chrome CDP not available)"
            return "Error: Chrome is not running with remote debugging. Launch Chrome with: chrome --remote-debugging-port=9222"
    
    pw = None
    try:
        pw, browser = _get_playwright_browser()
        contexts = browser.contexts
        
        if not contexts or not contexts[0].pages:
            return "Error: No browser tabs found. Open a tab in Chrome first."
        
        # Get the target page
        pages = contexts[0].pages
        if tab_index >= len(pages):
            tab_index = 0
        page = pages[tab_index]
        
        # ════════════ ACTION DISPATCH ════════════
        
        if action == 'navigate':
            if not url:
                return "Error: 'url' parameter required for navigate action"
            page.goto(url, wait_until='domcontentloaded', timeout=15000)
            title = page.title()
            return f"✅ Navigated to: {url}\nPage title: {title}"
        
        elif action == 'screenshot':
            timestamp = int(time.time())
            path = os.path.join(SCREENSHOT_DIR, f"screen_{timestamp}.png")
            page.screenshot(path=path, full_page=False)
            # Also return base64 for embedding
            with open(path, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode()
            return f"✅ Screenshot saved to: {path}\nBase64 length: {len(b64)} chars\nPage: {page.url}"
        
        elif action == 'run_js':
            if not js_code:
                return "Error: 'js_code' parameter required for run_js action"
            try:
                result = page.evaluate(js_code)
                result_str = json.dumps(result, indent=2, default=str) if result is not None else "undefined"
                return f"✅ JavaScript executed successfully on {page.url}\nResult: {result_str}"
            except Exception as e:
                return f"❌ JavaScript error: {str(e)}"
        
        elif action == 'inject_css':
            if not css_code:
                return "Error: 'css_code' parameter required for inject_css action"
            # Inject CSS via JavaScript
            escaped_css = css_code.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n')
            inject_script = f"""
            (() => {{
                const existingStyle = document.getElementById('nomad-injected-css');
                if (existingStyle) existingStyle.remove();
                const style = document.createElement('style');
                style.id = 'nomad-injected-css';
                style.textContent = '{escaped_css}';
                document.head.appendChild(style);
                return 'CSS injected successfully with ' + style.textContent.length + ' chars';
            }})()
            """
            result = page.evaluate(inject_script)
            return f"✅ CSS injected into {page.url}\n{result}"
        
        elif action == 'fullscreen_video':
            # The nuclear option for video fullscreen
            fullscreen_script = """
            (() => {
                const video = document.querySelector('video');
                if (!video) return 'No <video> element found on page';
                
                // Method 1: Try standard fullscreen API
                try {
                    if (video.requestFullscreen) {
                        video.requestFullscreen();
                        return 'Requested fullscreen via standard API';
                    }
                    if (video.webkitRequestFullscreen) {
                        video.webkitRequestFullscreen();
                        return 'Requested fullscreen via webkit API';
                    }
                } catch(e) { /* continue to CSS method */ }
                
                // Method 2: CSS fullscreen override (works when API is blocked)
                const player = video.closest('div') || video.parentElement;
                if (player) {
                    player.style.cssText = `
                        position: fixed !important;
                        top: 0 !important;
                        left: 0 !important;
                        width: 100vw !important;
                        height: 100vh !important;
                        z-index: 999999 !important;
                        background: black !important;
                    `;
                }
                video.style.cssText = `
                    position: fixed !important;
                    top: 0 !important;
                    left: 0 !important;
                    width: 100vw !important;
                    height: 100vh !important;
                    z-index: 999999 !important;
                    object-fit: contain !important;
                    background: black !important;
                `;
                
                // Method 3: Check if video is in an iframe, add allowfullscreen
                const iframes = document.querySelectorAll('iframe');
                iframes.forEach(iframe => {
                    if (!iframe.getAttribute('allowfullscreen')) {
                        iframe.setAttribute('allowfullscreen', '');
                        iframe.setAttribute('allow', 'fullscreen');
                    }
                });
                
                // Method 4: Remove any overlay elements blocking the video
                document.querySelectorAll('[class*="overlay"], [class*="popup"], [class*="modal"], [class*="ad"]').forEach(el => {
                    if (el !== player && el !== video) {
                        el.style.display = 'none';
                    }
                });
                
                return 'Forced fullscreen via CSS override. Press Escape or F11 to exit.';
            })()
            """
            result = page.evaluate(fullscreen_script)
            return f"✅ Video fullscreen action on {page.url}\n{result}"
        
        elif action == 'click':
            if selector:
                try:
                    page.click(selector, timeout=5000)
                    return f"✅ Clicked element: {selector}"
                except Exception as e:
                    return f"❌ Failed to click '{selector}': {e}"
            else:
                x = params.get('x', 500)
                y = params.get('y', 500)
                page.mouse.click(x, y)
                return f"✅ Clicked at coordinates ({x}, {y})"
        
        elif action == 'type_text':
            if not text:
                return "Error: 'text' parameter required for type_text action"
            if selector:
                page.fill(selector, text, timeout=5000)
                return f"✅ Typed '{text[:50]}...' into {selector}"
            else:
                page.keyboard.type(text)
                return f"✅ Typed '{text[:50]}...' at current focus"
        
        elif action == 'get_page_info':
            info = page.evaluate("""
            () => ({
                title: document.title,
                url: window.location.href,
                hasVideo: !!document.querySelector('video'),
                videoCount: document.querySelectorAll('video').length,
                iframeCount: document.querySelectorAll('iframe').length,
                bodyText: document.body ? document.body.innerText.substring(0, 500) : '',
                links: document.querySelectorAll('a').length,
                images: document.querySelectorAll('img').length,
                forms: document.querySelectorAll('form').length,
            })
            """)
            return f"✅ Page Info:\n{json.dumps(info, indent=2)}"
        
        elif action == 'list_tabs':
            tab_list = []
            for i, p in enumerate(pages):
                tab_list.append(f"  [{i}] {p.title()} — {p.url}")
            return f"✅ Open tabs ({len(pages)}):\n" + "\n".join(tab_list)
        
        elif action == 'switch_tab':
            target = pages[min(tab_index, len(pages) - 1)]
            target.bring_to_front()
            return f"✅ Switched to tab [{tab_index}]: {target.title()}"
        
        elif action == 'remove_ads':
            ad_script = """
            (() => {
                const selectors = [
                    '[class*="ad-"]', '[class*="Ad-"]', '[class*="advertisement"]',
                    '[id*="ad-"]', '[id*="Ad-"]', '[class*="popup"]',
                    '[class*="overlay"]', '[class*="modal"]', 'iframe[src*="ad"]',
                    '[class*="banner"]', '[data-ad]', '.adsbygoogle'
                ];
                let removed = 0;
                selectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        el.remove();
                        removed++;
                    });
                });
                return 'Removed ' + removed + ' ad/overlay elements';
            })()
            """
            result = page.evaluate(ad_script)
            return f"✅ Ad removal on {page.url}: {result}"
        
        elif action == 'dark_mode':
            dark_css = """
            html { filter: invert(0.9) hue-rotate(180deg) !important; }
            img, video, canvas { filter: invert(1) hue-rotate(-180deg) !important; }
            """
            escaped = dark_css.replace("'", "\\'").replace('\n', '\\n')
            page.evaluate(f"""
            (() => {{
                const s = document.createElement('style');
                s.id = 'nomad-dark-mode';
                s.textContent = '{escaped}';
                document.head.appendChild(s);
            }})()
            """)
            return f"✅ Dark mode applied to {page.url}"
        
        elif action == 'scroll':
            direction = params.get('direction', 'down')
            amount = params.get('amount', 500)
            if direction == 'up':
                amount = -amount
            page.evaluate(f"window.scrollBy(0, {amount})")
            return f"✅ Scrolled {direction} by {abs(amount)}px"
        
        else:
            return f"❌ Unknown action: '{action}'. Supported: navigate, screenshot, run_js, inject_css, fullscreen_video, click, type_text, get_page_info, list_tabs, switch_tab, remove_ads, dark_mode, scroll"
    
    except Exception as e:
        return f"❌ Browser control error: {str(e)}"
    finally:
        if pw:
            try:
                pw.stop()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════
# SCREEN CONTROL (PyAutoGUI — physical mouse/keyboard)
# ═══════════════════════════════════════════════════════

def execute_screen_control(params: Dict[str, Any]) -> str:
    """
    Physical screen control using PyAutoGUI.
    For when the agent needs to interact with things OUTSIDE the browser
    (e.g., opening apps, clicking system UI, taking full-screen screenshots).
    
    Actions:
      screenshot    - Full screen capture
      click         - Click at (x, y) coordinates
      type_text     - Type text at current cursor position
      press_key     - Press a keyboard shortcut (e.g., 'f11', 'ctrl+shift+i')
      move_mouse    - Move mouse to coordinates
      locate_image  - Find an image on screen and click it
    """
    action = params.get('action', 'screenshot')
    
    try:
        import pyautogui
        pyautogui.FAILSAFE = True  # Move mouse to corner to abort
        
        if action == 'screenshot':
            timestamp = int(time.time())
            path = os.path.join(SCREENSHOT_DIR, f"fullscreen_{timestamp}.png")
            img = pyautogui.screenshot()
            img.save(path)
            return f"✅ Full screen screenshot saved to: {path}"
        
        elif action == 'click':
            x = params.get('x', 500)
            y = params.get('y', 500)
            pyautogui.click(x, y)
            return f"✅ Clicked at ({x}, {y})"
        
        elif action == 'type_text':
            text = params.get('text', '')
            pyautogui.typewrite(text, interval=0.02) if text.isascii() else pyautogui.write(text)
            return f"✅ Typed: {text[:50]}"
        
        elif action == 'press_key':
            key = params.get('key', 'enter')
            keys = key.split('+')
            if len(keys) > 1:
                pyautogui.hotkey(*keys)
            else:
                pyautogui.press(key)
            return f"✅ Pressed: {key}"
        
        elif action == 'move_mouse':
            x = params.get('x', 500)
            y = params.get('y', 500)
            pyautogui.moveTo(x, y, duration=0.3)
            return f"✅ Mouse moved to ({x}, {y})"
        
        elif action == 'open_devtools':
            pyautogui.hotkey('ctrl', 'shift', 'i')
            time.sleep(1)
            return "✅ Chrome DevTools opened (Ctrl+Shift+I)"
        
        elif action == 'toggle_fullscreen':
            pyautogui.press('f11')
            return "✅ Toggled browser fullscreen (F11)"
        
        else:
            return f"❌ Unknown screen action: {action}"
    
    except ImportError:
        return "❌ pyautogui not installed. Run: pip install pyautogui"
    except Exception as e:
        return f"❌ Screen control error: {str(e)}"
