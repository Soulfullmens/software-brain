"""
dom_scanner.py

The 'Eyes' of the Agent.
Scans any web page and produces a structured PageModel.
Phase R.2 Step 2: Perception Layer.

This module enables the agent to UNDERSTAND what it sees,
not just blindly click selectors.
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class UIElement:
    """A single interactive element on the page."""
    tag: str                      # button, input, a, select, textarea
    element_type: str             # "button", "link", "text_input", "dropdown", etc.
    selector: str                 # CSS selector to target this element
    text: str = ""                # Visible text / label
    name: str = ""                # name attribute
    aria_label: str = ""          # accessibility label
    placeholder: str = ""         # input placeholder
    href: str = ""                # link destination
    input_type: str = ""          # text, password, email, submit, etc.
    is_visible: bool = True
    index: int = 0                # Position index for disambiguation


@dataclass 
class FormGroup:
    """A detected form on the page."""
    form_id: str = ""
    action: str = ""
    method: str = ""
    fields: List[UIElement] = field(default_factory=list)
    submit_button: Optional[UIElement] = None


@dataclass
class PageModel:
    """
    Complete structured representation of a web page.
    This is what the agent 'sees'.
    """
    url: str = ""
    title: str = ""
    page_type: str = "unknown"    # login, search, form, article, dashboard, error, etc.
    
    # Interactive elements
    buttons: List[UIElement] = field(default_factory=list)
    links: List[UIElement] = field(default_factory=list)
    inputs: List[UIElement] = field(default_factory=list)
    dropdowns: List[UIElement] = field(default_factory=list)
    
    # Grouped
    forms: List[FormGroup] = field(default_factory=list)
    
    # Content
    headings: List[str] = field(default_factory=list)
    visible_text_summary: str = ""
    alerts: List[str] = field(default_factory=list)
    
    # Meta
    element_count: int = 0
    

# JavaScript injected into the page to extract structure
_SCAN_JS = """
() => {
    const results = {
        buttons: [],
        links: [],
        inputs: [],
        dropdowns: [],
        forms: [],
        headings: [],
        alerts: [],
        title: document.title,
        url: window.location.href
    };
    
    // Helper: get visible text
    function getVisibleText(el) {
        return (el.innerText || el.textContent || '').trim().substring(0, 200);
    }
    
    // Helper: build a robust CSS selector
    function buildSelector(el, index, tag) {
        if (el.id) return '#' + CSS.escape(el.id);
        if (el.name) return tag + '[name="' + el.name + '"]';
        if (el.getAttribute('aria-label')) return tag + '[aria-label="' + el.getAttribute('aria-label') + '"]';
        if (el.className && typeof el.className === 'string' && el.className.trim()) {
            const cls = el.className.trim().split(/\\s+/)[0];
            return tag + '.' + CSS.escape(cls);
        }
        // Fallback: nth-of-type
        return tag + ':nth-of-type(' + (index + 1) + ')';
    }
    
    // Helper: check visibility
    function isVisible(el) {
        const style = window.getComputedStyle(el);
        return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
    }

    // ---- BUTTONS ----
    const btns = document.querySelectorAll('button, [role="button"], input[type="submit"], input[type="button"]');
    btns.forEach((el, i) => {
        if (!isVisible(el)) return;
        results.buttons.push({
            tag: el.tagName.toLowerCase(),
            element_type: 'button',
            selector: buildSelector(el, i, el.tagName.toLowerCase()),
            text: getVisibleText(el) || el.value || '',
            name: el.name || '',
            aria_label: el.getAttribute('aria-label') || '',
            is_visible: true,
            index: i
        });
    });
    
    // ---- LINKS ----
    const anchors = document.querySelectorAll('a[href]');
    anchors.forEach((el, i) => {
        if (!isVisible(el)) return;
        results.links.push({
            tag: 'a',
            element_type: 'link',
            selector: buildSelector(el, i, 'a'),
            text: getVisibleText(el),
            href: el.href || '',
            aria_label: el.getAttribute('aria-label') || '',
            is_visible: true,
            index: i
        });
    });
    
    // ---- INPUTS ----
    const inputs = document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]), textarea');
    inputs.forEach((el, i) => {
        if (!isVisible(el)) return;
        const inputType = el.type || 'text';
        let elementType = 'text_input';
        if (inputType === 'password') elementType = 'password_input';
        else if (inputType === 'email') elementType = 'email_input';
        else if (inputType === 'checkbox') elementType = 'checkbox';
        else if (inputType === 'radio') elementType = 'radio';
        else if (inputType === 'file') elementType = 'file_upload';
        else if (el.tagName.toLowerCase() === 'textarea') elementType = 'textarea';
        
        results.inputs.push({
            tag: el.tagName.toLowerCase(),
            element_type: elementType,
            selector: buildSelector(el, i, el.tagName.toLowerCase()),
            text: '',
            name: el.name || '',
            aria_label: el.getAttribute('aria-label') || '',
            placeholder: el.placeholder || '',
            input_type: inputType,
            is_visible: true,
            index: i
        });
    });
    
    // ---- DROPDOWNS ----
    const selects = document.querySelectorAll('select');
    selects.forEach((el, i) => {
        if (!isVisible(el)) return;
        results.dropdowns.push({
            tag: 'select',
            element_type: 'dropdown',
            selector: buildSelector(el, i, 'select'),
            text: '',
            name: el.name || '',
            aria_label: el.getAttribute('aria-label') || '',
            is_visible: true,
            index: i
        });
    });
    
    // ---- FORMS ----
    const formEls = document.querySelectorAll('form');
    formEls.forEach((form, fi) => {
        const formData = {
            form_id: form.id || '',
            action: form.action || '',
            method: (form.method || 'GET').toUpperCase(),
            fields: [],
            submit_button: null
        };
        // Fields inside this form
        form.querySelectorAll('input:not([type="hidden"]), textarea, select').forEach((field, j) => {
            formData.fields.push({
                tag: field.tagName.toLowerCase(),
                name: field.name || '',
                input_type: field.type || '',
                placeholder: field.placeholder || '',
                aria_label: field.getAttribute('aria-label') || '',
                selector: buildSelector(field, j, field.tagName.toLowerCase())
            });
        });
        // Submit button
        const submitBtn = form.querySelector('button[type="submit"], input[type="submit"], button:not([type])');
        if (submitBtn) {
            formData.submit_button = {
                selector: buildSelector(submitBtn, 0, submitBtn.tagName.toLowerCase()),
                text: getVisibleText(submitBtn) || submitBtn.value || 'Submit'
            };
        }
        results.forms.push(formData);
    });
    
    // ---- HEADINGS ----
    document.querySelectorAll('h1, h2, h3').forEach(el => {
        const t = getVisibleText(el);
        if (t) results.headings.push(t);
    });
    
    // ---- ALERTS / ERRORS ----
    document.querySelectorAll('[role="alert"], .alert, .error, .warning, .notification').forEach(el => {
        const t = getVisibleText(el);
        if (t) results.alerts.push(t);
    });
    
    return results;
}
"""


class DOMScanner:
    """
    Scans a Playwright page and produces a structured PageModel.
    This is the agent's primary perception mechanism for web pages.
    """
    
    def scan(self, page) -> PageModel:
        """
        Execute the DOM scan on a Playwright page object.
        Returns a fully populated PageModel.
        """
        try:
            raw = page.evaluate(_SCAN_JS)
        except Exception as e:
            return PageModel(
                url=page.url if page else "",
                title="SCAN_FAILED",
                alerts=[f"DOM scan error: {str(e)}"]
            )
        
        model = PageModel(
            url=raw.get("url", ""),
            title=raw.get("title", ""),
        )
        
        # Parse buttons
        for b in raw.get("buttons", []):
            model.buttons.append(UIElement(
                tag=b.get("tag", ""), element_type="button",
                selector=b.get("selector", ""), text=b.get("text", ""),
                name=b.get("name", ""), aria_label=b.get("aria_label", ""),
                index=b.get("index", 0)
            ))
        
        # Parse links
        for l in raw.get("links", []):
            model.links.append(UIElement(
                tag="a", element_type="link",
                selector=l.get("selector", ""), text=l.get("text", ""),
                href=l.get("href", ""), aria_label=l.get("aria_label", ""),
                index=l.get("index", 0)
            ))
            
        # Parse inputs
        for inp in raw.get("inputs", []):
            model.inputs.append(UIElement(
                tag=inp.get("tag", ""), element_type=inp.get("element_type", "text_input"),
                selector=inp.get("selector", ""), name=inp.get("name", ""),
                aria_label=inp.get("aria_label", ""), placeholder=inp.get("placeholder", ""),
                input_type=inp.get("input_type", ""), index=inp.get("index", 0)
            ))
            
        # Parse dropdowns
        for d in raw.get("dropdowns", []):
            model.dropdowns.append(UIElement(
                tag="select", element_type="dropdown",
                selector=d.get("selector", ""), name=d.get("name", ""),
                aria_label=d.get("aria_label", ""), index=d.get("index", 0)
            ))
        
        # Parse forms
        for f in raw.get("forms", []):
            fg = FormGroup(
                form_id=f.get("form_id", ""),
                action=f.get("action", ""),
                method=f.get("method", "")
            )
            for fld in f.get("fields", []):
                fg.fields.append(UIElement(
                    tag=fld.get("tag", ""), element_type=fld.get("input_type", "text_input"),
                    selector=fld.get("selector", ""), name=fld.get("name", ""),
                    placeholder=fld.get("placeholder", ""),
                    aria_label=fld.get("aria_label", "")
                ))
            sb = f.get("submit_button")
            if sb:
                fg.submit_button = UIElement(
                    tag="button", element_type="submit",
                    selector=sb.get("selector", ""), text=sb.get("text", "Submit")
                )
            model.forms.append(fg)
        
        # Headings & Alerts
        model.headings = raw.get("headings", [])
        model.alerts = raw.get("alerts", [])
        
        # Classify page type
        model.page_type = self._classify_page(model)
        
        # Count
        model.element_count = (
            len(model.buttons) + len(model.links) + 
            len(model.inputs) + len(model.dropdowns)
        )
        
        # Text summary
        model.visible_text_summary = "; ".join(model.headings[:5]) if model.headings else model.title
        
        return model
    
    def _classify_page(self, model: PageModel) -> str:
        """Heuristic page type classification."""
        title_lower = model.title.lower()
        headings_lower = " ".join(model.headings).lower()
        combined = title_lower + " " + headings_lower
        
        # Login page
        has_password = any(i.input_type == "password" for i in model.inputs)
        has_email_or_user = any(
            i.input_type in ("email", "text") and 
            any(k in (i.name + i.placeholder + i.aria_label).lower() 
                for k in ("email", "user", "login", "username"))
            for i in model.inputs
        )
        if has_password and has_email_or_user:
            return "login"
        if has_password:
            return "login"
        
        # Search page
        if "search" in combined or "results" in combined:
            return "search_results"
        has_search_input = any(
            "search" in (i.name + i.placeholder + i.aria_label).lower()
            for i in model.inputs
        )
        if has_search_input and len(model.inputs) <= 3:
            return "search"
        
        # Error page
        if any(k in combined for k in ("404", "not found", "error", "forbidden", "500")):
            return "error"
        if model.alerts:
            return "alert"
        
        # Form page
        if len(model.forms) > 0 and len(model.inputs) > 3:
            return "form"
        
        # Dashboard
        if any(k in combined for k in ("dashboard", "admin", "panel", "overview")):
            return "dashboard"
        
        # Article / content
        if len(model.links) > 10 and len(model.inputs) <= 2:
            return "content"
        
        return "general"
