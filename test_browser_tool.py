"""
test_browser_tool.py

Verification for Phase R.2 (BrowserControlTool v0).
Uses Playwright to navigate 'example.com'.
"""
import time
from src.agent.tools.browser import BrowserControlTool

def main():
    print("=== Testing BrowserControlTool (Playwright) ===")
    
    # 0. Instantiate (Headless=True usually, but False for debug if needed)
    # kept headless=True to ensure it works in background.
    browser = BrowserControlTool(headless=True)
    
    # 1. Open URL
    print("\n[Action] Opening example.com...")
    result = browser.run("open_url", url="https://example.com")
    print(f"Result: {result}")
    
    if result.get("error"):
        print("FAIL: Could not open URL.")
        return

    # 2. Extract Text
    print("\n[Action] Extracting H1...")
    result = browser.run("extract_text", selector="h1")
    print(f"Result: {result}")
    
    # 3. Screenshot
    print("\n[Action] Taking Screenshot...")
    result = browser.run("screenshot", filename="test_browser_R2.png")
    print(f"Result: {result}")
    
    # 4. Click Link
    print("\n[Action] Clicking 'More information'...")
    # example.com has a link <a href="...">More information...</a>
    result = browser.run("click", selector="a")
    print(f"Result: {result}")
    
    # Wait for nav
    time.sleep(2)
    
    # 5. Check URL
    # We can inspect internal state via private access or just check page title/url via a new action?
    # R.2 v0 didn't have "get_url" explicit action, but open_url returned it.
    # Let's add "get_info" or rely on another open_url (which acts as goto)?
    # Or just use the object since we are in a test script.
    if browser._page:
        print(f"Current URL: {browser._page.url}")
        print(f"Current Title: {browser._page.title()}")
        
    # 6. Close
    print("\n[Action] Closing...")
    browser.run("close")
    print("Closed.")

if __name__ == "__main__":
    main()
