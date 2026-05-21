"""
browser.py

The 'Digital Body' of the Agent.
Provides `BrowserControlTool` via Playwright.
Phase R.2: General Digital Action Layer + Perception.

Actions:
  Session:    start, close
  Navigation: open_url, back, refresh
  Action:     click, type, hover, find_and_click, find_and_type
  Perception: extract_text, screenshot, scan_page, find_element
"""
from typing import Dict, Any, Optional, List
from ..tool import Tool
from ..perception.dom_scanner import DOMScanner, PageModel
from ..perception.element_finder import ElementFinder

try:
    from playwright.sync_api import sync_playwright, Playwright, Browser, Page
except ImportError:
    sync_playwright = None


class BrowserControlTool(Tool):
    name = "browser_control"
    description = (
        "Control a web browser with perception. "
        "Actions: open_url, click, type, extract_text, screenshot, close, "
        "scan_page, find_element, find_and_click, find_and_type."
    )
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._context_manager = None
        
        # Perception
        self._scanner = DOMScanner()
        self._finder = ElementFinder()
        self._last_page_model: Optional[PageModel] = None

    def run(self, action: str, **kwargs) -> Any:
        """Execute browser action."""
        if sync_playwright is None:
            return {"error": "Playwright not installed."}

        # Lazy init
        if not self._playwright and action != "close":
            self._start_browser()

        try:
            # ──── SESSION ────
            if action == "close":
                self._close_browser()
                return {"status": "closed"}

            # ──── NAVIGATION ────
            elif action == "open_url":
                url = kwargs.get("url")
                if not url:
                    return {"error": "Missing 'url'"}
                self._page.goto(url, wait_until="domcontentloaded")
                self._last_page_model = None  # Invalidate cache
                return {
                    "status": "opened",
                    "url": self._page.url,
                    "title": self._page.title()
                }

            elif action == "back":
                self._page.go_back()
                self._last_page_model = None
                return {"status": "navigated_back", "url": self._page.url}

            elif action == "refresh":
                self._page.reload()
                self._last_page_model = None
                return {"status": "reloaded"}

            # ──── BASIC ACTIONS ────
            elif action == "click":
                selector = kwargs.get("selector")
                if not selector:
                    return {"error": "Missing 'selector'"}
                self._page.click(selector, timeout=5000)
                self._last_page_model = None
                return {"status": "clicked", "selector": selector}

            elif action == "type":
                selector = kwargs.get("selector")
                text = kwargs.get("text")
                if not selector or text is None:
                    return {"error": "Missing 'selector' or 'text'"}
                self._page.fill(selector, text)
                return {"status": "typed", "selector": selector}

            elif action == "hover":
                selector = kwargs.get("selector")
                if not selector:
                    return {"error": "Missing 'selector'"}
                self._page.hover(selector, timeout=5000)
                return {"status": "hovered", "selector": selector}

            elif action == "extract_text":
                selector = kwargs.get("selector", "body")
                text = self._page.inner_text(selector)
                return {"text": text[:2000] + "..." if len(text) > 2000 else text}

            elif action == "screenshot":
                filename = kwargs.get("filename", "screenshot.png")
                path = f"./logs/{filename}"
                self._page.screenshot(path=path)
                return {"status": "captured", "path": path}

            # ──── PERCEPTION ────
            elif action == "scan_page":
                model = self._scan()
                return {
                    "page_type": model.page_type,
                    "title": model.title,
                    "url": model.url,
                    "buttons": len(model.buttons),
                    "links": len(model.links),
                    "inputs": len(model.inputs),
                    "forms": len(model.forms),
                    "headings": model.headings[:5],
                    "alerts": model.alerts,
                    "element_count": model.element_count,
                    "summary": model.visible_text_summary
                }

            elif action == "find_element":
                description = kwargs.get("description")
                if not description:
                    return {"error": "Missing 'description'"}
                model = self._scan()
                element = self._finder.find(description, model)
                if not element:
                    return {"found": False, "description": description}
                return {
                    "found": True,
                    "selector": element.selector,
                    "text": element.text,
                    "element_type": element.element_type,
                    "tag": element.tag
                }

            # ──── SMART ACTIONS (PERCEPTION + ACTION) ────
            elif action == "find_and_click":
                description = kwargs.get("description")
                if not description:
                    return {"error": "Missing 'description'"}
                model = self._scan()
                element = self._finder.find(description, model)
                if not element:
                    return {"error": f"Could not find element matching '{description}'"}
                self._page.click(element.selector, timeout=5000)
                self._last_page_model = None
                return {
                    "status": "clicked",
                    "matched": element.text or element.selector,
                    "selector": element.selector
                }

            elif action == "find_and_type":
                description = kwargs.get("description")
                text = kwargs.get("text")
                if not description or text is None:
                    return {"error": "Missing 'description' or 'text'"}
                model = self._scan()
                element = self._finder.find(description, model)
                if not element:
                    return {"error": f"Could not find input matching '{description}'"}
                self._page.fill(element.selector, text)
                return {
                    "status": "typed",
                    "matched": element.name or element.placeholder or element.selector,
                    "selector": element.selector
                }

            # ──── PAGE MODEL (RAW) ────
            elif action == "get_page_model":
                model = self._scan()
                # Return structured data for the Planner/Brain
                return {
                    "page_type": model.page_type,
                    "title": model.title,
                    "url": model.url,
                    "buttons": [
                        {"text": b.text, "selector": b.selector}
                        for b in model.buttons[:20]
                    ],
                    "links": [
                        {"text": l.text[:50], "href": l.href, "selector": l.selector}
                        for l in model.links[:30]
                    ],
                    "inputs": [
                        {"name": i.name, "type": i.input_type,
                         "placeholder": i.placeholder, "selector": i.selector}
                        for i in model.inputs[:20]
                    ],
                    "forms": [
                        {
                            "id": f.form_id, "action": f.action,
                            "fields": len(f.fields),
                            "submit": f.submit_button.text if f.submit_button else None
                        }
                        for f in model.forms[:10]
                    ]
                }

            else:
                return {"error": f"Unknown action '{action}'"}

        except Exception as e:
            return {"error": f"Browser Error: {str(e)}"}

    def _scan(self) -> PageModel:
        """Scan the current page (cached per navigation)."""
        if self._last_page_model is None:
            self._last_page_model = self._scanner.scan(self._page)
        return self._last_page_model

    def _start_browser(self):
        if self._playwright:
            return
        self._context_manager = sync_playwright()
        self._playwright = self._context_manager.start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._page = self._browser.new_page()

    def _close_browser(self):
        if self._browser:
            self._browser.close()
            self._browser = None
            self._page = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
        self._context_manager = None
        self._last_page_model = None

    def __del__(self):
        try:
            self._close_browser()
        except Exception:
            pass
