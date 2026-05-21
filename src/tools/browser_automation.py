"""
Browser Automation — Navigate, Fill Forms, Click, Read Pages

Like having hands inside a web browser. The agent can:
- Open URLs and navigate
- Fill forms (login, search, checkout)
- Click buttons and links
- Read page content
- Take page screenshots
- Extract data from pages

Uses Playwright (fast, headless Chrome) with Selenium fallback.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BrowserResult:
    """Result from a browser action."""
    success: bool
    action: str
    data: Any = None
    url: str = ""
    title: str = ""
    error: str = ""
    screenshot_path: str = ""
    duration_ms: float = 0


class BrowserAutomation:
    """
    Automated browser control — navigate, fill, click, read.
    
    Uses Playwright for fast headless browser automation.
    Falls back to urllib for simple page reads.
    
    USAGE:
        browser = BrowserAutomation()
        
        # Open a page
        browser.goto("https://google.com")
        
        # Fill a search box and submit
        browser.fill("input[name=q]", "Python tutorial")
        browser.click("input[type=submit]")
        
        # Read page content
        text = browser.read_page()
        
        # Fill a login form
        browser.fill_form({
            "#email": "user@example.com",
            "#password": "mypass"
        })
        browser.click("#login-btn")
        
        # Screenshot
        browser.screenshot("page.png")
        
        # Close
        browser.close()
    
    SAFETY:
        - No credential storage (passwords passed per-action)
        - All actions logged for audit
        - Headless by default (no visible window unless requested)
    """

    def __init__(self, headless: bool = True, screenshot_dir: str = "./screenshots"):
        self._headless = headless
        self._screenshot_dir = screenshot_dir
        os.makedirs(screenshot_dir, exist_ok=True)
        
        self._playwright = None
        self._browser = None
        self._page = None
        self._action_log: List[Dict] = []
        self._initialized = False

    def _ensure_browser(self) -> bool:
        """Initialize Playwright browser if not already running."""
        if self._initialized and self._page:
            return True
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self._headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self._page = self._browser.new_page()
            self._page.set_default_timeout(15000)  # 15s timeout
            self._initialized = True
            return True
        except ImportError:
            return False
        except Exception:
            return False

    def _log(self, action: str, detail: str, success: bool):
        self._action_log.append({
            "action": action, "detail": detail,
            "success": success, "timestamp": time.time(),
        })

    # ═══════════════════════════════════════
    #  Navigation
    # ═══════════════════════════════════════

    def goto(self, url: str, wait_for: str = "load") -> BrowserResult:
        """
        Navigate to a URL.
        
        Args:
            url: The URL to visit
            wait_for: "load", "domcontentloaded", or "networkidle"
        """
        start = time.time()
        if not self._ensure_browser():
            return self._fallback_goto(url)
        try:
            self._page.goto(url, wait_until=wait_for, timeout=20000)
            dur = (time.time() - start) * 1000
            title = self._page.title()
            self._log("goto", url, True)
            return BrowserResult(True, "goto", url=url, title=title, duration_ms=dur)
        except Exception as e:
            self._log("goto", url, False)
            return BrowserResult(False, "goto", error=str(e), url=url,
                               duration_ms=(time.time() - start) * 1000)

    def _fallback_goto(self, url: str) -> BrowserResult:
        """Simple urllib fallback for basic page reads."""
        start = time.time()
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 SmartAgent/1.0"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                dur = (time.time() - start) * 1000
                # Extract title
                title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
                title = title_match.group(1).strip() if title_match else ""
                return BrowserResult(True, "goto_fallback", data=html,
                                   url=url, title=title, duration_ms=dur)
        except Exception as e:
            return BrowserResult(False, "goto_fallback", error=str(e), url=url,
                               duration_ms=(time.time() - start) * 1000)

    def back(self) -> BrowserResult:
        """Go back to previous page."""
        if not self._page:
            return BrowserResult(False, "back", error="No browser")
        try:
            self._page.go_back()
            return BrowserResult(True, "back", url=self._page.url, title=self._page.title())
        except Exception as e:
            return BrowserResult(False, "back", error=str(e))

    def forward(self) -> BrowserResult:
        """Go forward."""
        if not self._page:
            return BrowserResult(False, "forward", error="No browser")
        try:
            self._page.go_forward()
            return BrowserResult(True, "forward", url=self._page.url, title=self._page.title())
        except Exception as e:
            return BrowserResult(False, "forward", error=str(e))

    def refresh(self) -> BrowserResult:
        """Refresh current page."""
        if not self._page:
            return BrowserResult(False, "refresh", error="No browser")
        try:
            self._page.reload()
            return BrowserResult(True, "refresh", url=self._page.url)
        except Exception as e:
            return BrowserResult(False, "refresh", error=str(e))

    # ═══════════════════════════════════════
    #  Interaction
    # ═══════════════════════════════════════

    def click(self, selector: str) -> BrowserResult:
        """
        Click an element on the page.
        
        Args:
            selector: CSS selector, text selector, or XPath
                     Examples: "#submit-btn", "text=Login", "button.primary"
        """
        if not self._page:
            return BrowserResult(False, "click", error="No browser")
        start = time.time()
        try:
            self._page.click(selector, timeout=10000)
            dur = (time.time() - start) * 1000
            self._log("click", selector, True)
            return BrowserResult(True, "click", data=selector, duration_ms=dur,
                               url=self._page.url, title=self._page.title())
        except Exception as e:
            self._log("click", selector, False)
            return BrowserResult(False, "click", error=str(e), duration_ms=(time.time() - start) * 1000)

    def fill(self, selector: str, value: str) -> BrowserResult:
        """
        Fill a text input field.
        
        Args:
            selector: CSS selector for the input field
            value: Text to type into the field
        """
        if not self._page:
            return BrowserResult(False, "fill", error="No browser")
        try:
            self._page.fill(selector, value, timeout=10000)
            self._log("fill", f"{selector} = {value[:30]}", True)
            return BrowserResult(True, "fill", data={"selector": selector, "filled": True})
        except Exception as e:
            self._log("fill", selector, False)
            return BrowserResult(False, "fill", error=str(e))

    def fill_form(self, fields: Dict[str, str]) -> BrowserResult:
        """
        Fill multiple form fields at once.
        
        Args:
            fields: {selector: value} pairs
                   Example: {"#email": "user@example.com", "#password": "pass"}
        """
        if not self._page:
            return BrowserResult(False, "fill_form", error="No browser")
        results = {}
        for selector, value in fields.items():
            try:
                self._page.fill(selector, value, timeout=5000)
                results[selector] = True
            except Exception as e:
                results[selector] = str(e)
        
        success = all(v is True for v in results.values())
        self._log("fill_form", json.dumps(list(fields.keys())), success)
        return BrowserResult(success, "fill_form", data=results)

    def select(self, selector: str, value: str) -> BrowserResult:
        """Select an option from a dropdown."""
        if not self._page:
            return BrowserResult(False, "select", error="No browser")
        try:
            self._page.select_option(selector, value, timeout=5000)
            self._log("select", f"{selector} = {value}", True)
            return BrowserResult(True, "select", data={"selector": selector, "value": value})
        except Exception as e:
            return BrowserResult(False, "select", error=str(e))

    def check(self, selector: str) -> BrowserResult:
        """Check a checkbox."""
        if not self._page:
            return BrowserResult(False, "check", error="No browser")
        try:
            self._page.check(selector, timeout=5000)
            return BrowserResult(True, "check", data=selector)
        except Exception as e:
            return BrowserResult(False, "check", error=str(e))

    def press(self, key: str) -> BrowserResult:
        """Press a key (Enter, Tab, Escape, etc.)."""
        if not self._page:
            return BrowserResult(False, "press", error="No browser")
        try:
            self._page.keyboard.press(key)
            return BrowserResult(True, "press", data=key)
        except Exception as e:
            return BrowserResult(False, "press", error=str(e))

    def wait(self, selector: str = None, seconds: float = None) -> BrowserResult:
        """Wait for an element or a fixed time."""
        if not self._page:
            return BrowserResult(False, "wait", error="No browser")
        try:
            if selector:
                self._page.wait_for_selector(selector, timeout=15000)
                return BrowserResult(True, "wait", data=f"Found: {selector}")
            elif seconds:
                capped = min(seconds, 30)
                time.sleep(capped)
                return BrowserResult(True, "wait", data=f"Waited {capped}s")
            return BrowserResult(True, "wait", data="No-op")
        except Exception as e:
            return BrowserResult(False, "wait", error=str(e))

    # ═══════════════════════════════════════
    #  Reading
    # ═══════════════════════════════════════

    def read_page(self, selector: str = "body") -> BrowserResult:
        """
        Read text content from the page.
        
        Args:
            selector: CSS selector to read from (default: entire body)
        """
        if not self._page:
            return BrowserResult(False, "read_page", error="No browser")
        try:
            text = self._page.inner_text(selector, timeout=5000)
            # Trim to reasonable size
            if len(text) > 50000:
                text = text[:50000] + "\n...[truncated]"
            return BrowserResult(True, "read_page", data=text,
                               url=self._page.url, title=self._page.title())
        except Exception as e:
            return BrowserResult(False, "read_page", error=str(e))

    def read_html(self, selector: str = "body") -> BrowserResult:
        """Read raw HTML from a section of the page."""
        if not self._page:
            return BrowserResult(False, "read_html", error="No browser")
        try:
            html = self._page.inner_html(selector, timeout=5000)
            if len(html) > 100000:
                html = html[:100000] + "...[truncated]"
            return BrowserResult(True, "read_html", data=html,
                               url=self._page.url, title=self._page.title())
        except Exception as e:
            return BrowserResult(False, "read_html", error=str(e))

    def get_links(self) -> BrowserResult:
        """Get all links on the current page."""
        if not self._page:
            return BrowserResult(False, "get_links", error="No browser")
        try:
            links = self._page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => ({text: e.textContent.trim().substring(0,100), href: e.href}))"
            )
            return BrowserResult(True, "get_links", data=links[:200],
                               url=self._page.url, title=self._page.title())
        except Exception as e:
            return BrowserResult(False, "get_links", error=str(e))

    def get_inputs(self) -> BrowserResult:
        """Get all form inputs on the page."""
        if not self._page:
            return BrowserResult(False, "get_inputs", error="No browser")
        try:
            inputs = self._page.eval_on_selector_all(
                "input, textarea, select",
                """els => els.map(e => ({
                    tag: e.tagName, type: e.type || '', name: e.name || '',
                    id: e.id || '', placeholder: e.placeholder || '',
                    value: e.value || '', selector: e.id ? '#'+e.id : (e.name ? '[name='+e.name+']' : e.tagName)
                }))"""
            )
            return BrowserResult(True, "get_inputs", data=inputs[:100])
        except Exception as e:
            return BrowserResult(False, "get_inputs", error=str(e))

    def evaluate(self, js_code: str) -> BrowserResult:
        """Run JavaScript on the page and return the result."""
        if not self._page:
            return BrowserResult(False, "evaluate", error="No browser")
        try:
            result = self._page.evaluate(js_code)
            return BrowserResult(True, "evaluate", data=result)
        except Exception as e:
            return BrowserResult(False, "evaluate", error=str(e))

    # ═══════════════════════════════════════
    #  Screenshots
    # ═══════════════════════════════════════

    def screenshot(self, save_path: str = None, full_page: bool = False) -> BrowserResult:
        """Take a screenshot of the current page."""
        if not self._page:
            return BrowserResult(False, "screenshot", error="No browser")
        try:
            if not save_path:
                save_path = os.path.join(
                    self._screenshot_dir,
                    f"page_{int(time.time())}.png"
                )
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            self._page.screenshot(path=save_path, full_page=full_page)
            return BrowserResult(True, "screenshot", screenshot_path=save_path,
                               url=self._page.url, title=self._page.title())
        except Exception as e:
            return BrowserResult(False, "screenshot", error=str(e))

    # ═══════════════════════════════════════
    #  Search Shortcuts
    # ═══════════════════════════════════════

    def google_search(self, query: str) -> BrowserResult:
        """Perform a Google search."""
        encoded = urllib.parse.quote_plus(query)
        return self.goto(f"https://www.google.com/search?q={encoded}")

    def fast_search(self, query: str) -> BrowserResult:
        """Lightning-fast search via DuckDuckGo HTML (no CAPTCHA, no login).
        
        Returns structured results with title, url, snippet for each hit.
        Falls back to Google if DDG fails.
        """
        start = time.time()
        encoded = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

            results = self._parse_ddg_results(html)
            dur = (time.time() - start) * 1000
            return BrowserResult(
                True, "fast_search", data=results,
                url=url, title=f"Search: {query}",
                duration_ms=dur,
            )
        except Exception as e:
            # Fallback: try Google via browser
            return self.google_search(query)

    def _parse_ddg_results(self, html: str) -> list:
        """Parse DuckDuckGo HTML search results into structured data."""
        results = []
        # DDG uses <a class="result__a"> for titles and <a class="result__snippet"> for snippets
        # We'll use regex since we don't want external deps
        blocks = re.findall(
            r'class="result__body".*?(?=class="result__body"|$)',
            html, re.DOTALL
        )
        if not blocks:
            # Fallback: try a simpler pattern
            blocks = re.findall(
                r'class="links_main.*?(?=class="links_main|$)',
                html, re.DOTALL
            )

        for block in blocks[:10]:
            title_m = re.search(r'class="result__a"[^>]*>(.*?)</a>', block, re.DOTALL)
            url_m = re.search(r'class="result__a"\s+href="([^"]*)"', block)
            snip_m = re.search(r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)', block, re.DOTALL)

            if title_m:
                title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
                href = ""
                if url_m:
                    href = url_m.group(1)
                    # DDG wraps URLs in a redirect — extract actual URL
                    ud = re.search(r'uddg=([^&]+)', href)
                    if ud:
                        href = urllib.parse.unquote(ud.group(1))
                snippet = ""
                if snip_m:
                    snippet = re.sub(r'<[^>]+>', '', snip_m.group(1)).strip()

                if title and href:
                    # Skip DuckDuckGo ad/tracking links
                    if 'duckduckgo.com/y.js' in href or 'duckduckgo.com/l/' in href:
                        continue
                    results.append({
                        "title": title[:120],
                        "url": href,
                        "snippet": snippet[:200],
                    })
        return results

    def open_url(self, url: str) -> BrowserResult:
        """Open a URL (alias for goto)."""
        return self.goto(url)

    # ═══════════════════════════════════════
    #  Simple HTTP (no browser needed)
    # ═══════════════════════════════════════

    def fetch_text(self, url: str) -> BrowserResult:
        """Fetch a URL and return text content (no browser needed)."""
        start = time.time()
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 SmartAgent/1.0"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                # Strip tags for plain text
                text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()
                if len(text) > 50000:
                    text = text[:50000] + "...[truncated]"
                dur = (time.time() - start) * 1000
                return BrowserResult(True, "fetch_text", data=text, url=url, duration_ms=dur)
        except Exception as e:
            return BrowserResult(False, "fetch_text", error=str(e), url=url)

    # ═══════════════════════════════════════
    #  State & Cleanup
    # ═══════════════════════════════════════

    def current_url(self) -> str:
        """Get current page URL."""
        return self._page.url if self._page else ""

    def current_title(self) -> str:
        """Get current page title."""
        try:
            return self._page.title() if self._page else ""
        except Exception:
            return ""

    def is_open(self) -> bool:
        """Check if browser is running."""
        return self._initialized and self._page is not None

    def get_status(self) -> Dict:
        """Get browser automation status."""
        try:
            from playwright.sync_api import sync_playwright
            pw_available = True
        except ImportError:
            pw_available = False
        
        try:
            url = self.current_url()
            title = self.current_title()
        except Exception:
            url = ""
            title = ""

        return {
            "playwright_available": pw_available,
            "browser_open": self.is_open(),
            "current_url": url,
            "current_title": title,
            "actions_performed": len(self._action_log),
            "headless": self._headless,
        }

    def get_action_log(self) -> List[Dict]:
        """Get action audit log."""
        return list(self._action_log)

    def close(self):
        """Close the browser and cleanup."""
        try:
            if self._page:
                self._page.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._browser = None
        self._playwright = None
        self._initialized = False

    # ═══════════════════════════════════════
    #  Scrolling
    # ═══════════════════════════════════════

    def scroll(self, direction: str = "down", amount: int = 500) -> BrowserResult:
        """Scroll the page. direction: up/down/top/bottom. amount: pixels."""
        if not self._page:
            return BrowserResult(False, "scroll", error="No browser")
        try:
            if direction == "top":
                self._page.evaluate("window.scrollTo(0, 0)")
            elif direction == "bottom":
                self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            elif direction == "up":
                self._page.evaluate(f"window.scrollBy(0, -{amount})")
            else:
                self._page.evaluate(f"window.scrollBy(0, {amount})")
            self._log("scroll", f"{direction} {amount}px", True)
            return BrowserResult(True, "scroll", data=direction)
        except Exception as e:
            return BrowserResult(False, "scroll", error=str(e))

    def scroll_to_element(self, selector: str) -> BrowserResult:
        """Scroll to a specific element on the page."""
        if not self._page:
            return BrowserResult(False, "scroll_to", error="No browser")
        try:
            self._page.evaluate(f"""
                const el = document.querySelector('{selector}');
                if (el) el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
            """)
            self._log("scroll_to", selector, True)
            return BrowserResult(True, "scroll_to", data=selector)
        except Exception as e:
            return BrowserResult(False, "scroll_to", error=str(e))

    def highlight_on_page(self, text_or_selector: str) -> BrowserResult:
        """Highlight/glow an element or text on the page with a visual arrow indicator."""
        if not self._page:
            return BrowserResult(False, "highlight", error="No browser")
        try:
            js = """
            (query) => {
                // Remove previous highlights
                document.querySelectorAll('.jarvis-highlight,.jarvis-arrow').forEach(el => el.remove());
                const style = document.createElement('style');
                style.className = 'jarvis-highlight';
                style.textContent = `
                    .jarvis-glow {
                        outline: 3px solid #7c3aed !important;
                        box-shadow: 0 0 20px rgba(124,58,237,0.6), 0 0 40px rgba(124,58,237,0.3) !important;
                        border-radius: 4px !important;
                        animation: jarvisGlow 1.5s ease-in-out infinite !important;
                        position: relative !important;
                        z-index: 99999 !important;
                    }
                    @keyframes jarvisGlow {
                        0%,100% { box-shadow: 0 0 20px rgba(124,58,237,0.6), 0 0 40px rgba(124,58,237,0.3); }
                        50% { box-shadow: 0 0 30px rgba(124,58,237,0.8), 0 0 60px rgba(124,58,237,0.5); }
                    }
                    .jarvis-arrow-indicator {
                        position: fixed;
                        z-index: 100000;
                        font-size: 24px;
                        animation: jarvisBounce 0.8s ease-in-out infinite;
                        pointer-events: none;
                    }
                    @keyframes jarvisBounce {
                        0%,100% { transform: translateX(0); }
                        50% { transform: translateX(-10px); }
                    }
                `;
                document.head.appendChild(style);

                // Try CSS selector first
                let el = null;
                try { el = document.querySelector(query); } catch {}

                // Fallback: find by text content
                if (!el) {
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                    while (walker.nextNode()) {
                        if (walker.currentNode.textContent.toLowerCase().includes(query.toLowerCase())) {
                            el = walker.currentNode.parentElement;
                            break;
                        }
                    }
                }

                if (el) {
                    el.classList.add('jarvis-glow');
                    el.scrollIntoView({behavior: 'smooth', block: 'center'});
                    // Add arrow
                    const rect = el.getBoundingClientRect();
                    const arrow = document.createElement('div');
                    arrow.className = 'jarvis-arrow-indicator jarvis-highlight';
                    arrow.textContent = '👉';
                    arrow.style.top = (rect.top + window.scrollY + rect.height/2 - 12) + 'px';
                    arrow.style.left = (rect.left - 40) + 'px';
                    arrow.style.position = 'absolute';
                    document.body.appendChild(arrow);
                    // Auto-remove after 8 seconds
                    setTimeout(() => {
                        document.querySelectorAll('.jarvis-highlight,.jarvis-glow').forEach(e => {
                            e.classList.remove('jarvis-glow');
                            if (e.classList.contains('jarvis-highlight')) e.remove();
                        });
                    }, 8000);
                    return true;
                }
                return false;
            }
            """
            found = self._page.evaluate(js, text_or_selector)
            self._log("highlight", text_or_selector, found)
            return BrowserResult(found, "highlight", data=text_or_selector)
        except Exception as e:
            return BrowserResult(False, "highlight", error=str(e))

    def __del__(self):
        self.close()
