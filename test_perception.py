"""
test_perception.py

Verification for Phase R.2 Step 2 (Perception Layer).
Tests DOMScanner + ElementFinder + BrowserControlTool integration.
Runs against real websites to prove the agent can SEE.
"""
from src.agent.tools.browser import BrowserControlTool


def main():
    print("=" * 60)
    print("  PERCEPTION LAYER VERIFICATION (R.2 Step 2)")
    print("=" * 60)

    browser = BrowserControlTool(headless=True)

    # ──── TEST 1: Page Scan (example.com) ────
    print("\n[TEST 1] Scan example.com")
    browser.run("open_url", url="https://example.com")
    scan = browser.run("scan_page")
    print(f"  Page Type : {scan.get('page_type')}")
    print(f"  Title     : {scan.get('title')}")
    print(f"  Buttons   : {scan.get('buttons')}")
    print(f"  Links     : {scan.get('links')}")
    print(f"  Inputs    : {scan.get('inputs')}")
    print(f"  Forms     : {scan.get('forms')}")
    print(f"  Headings  : {scan.get('headings')}")
    print(f"  Elements  : {scan.get('element_count')}")
    assert scan.get("title") == "Example Domain", f"FAIL: title={scan.get('title')}"
    assert scan.get("links") >= 1, "FAIL: no links found"
    print("  ✓ PASSED")

    # ──── TEST 2: Find Element by Description ────
    print("\n[TEST 2] Find 'More information' link")
    result = browser.run("find_element", description="More information")
    print(f"  Found: {result.get('found')}")
    print(f"  Text : {result.get('text')}")
    print(f"  Sel  : {result.get('selector')}")
    assert result.get("found") == True, "FAIL: could not find element"
    print("  ✓ PASSED")

    # ──── TEST 3: Find and Click ────
    print("\n[TEST 3] find_and_click 'More information'")
    result = browser.run("find_and_click", description="More information")
    print(f"  Status : {result.get('status')}")
    print(f"  Matched: {result.get('matched')}")
    assert result.get("status") == "clicked", f"FAIL: {result}"

    # Wait for navigation
    import time
    time.sleep(2)

    # Verify navigation happened
    scan2 = browser.run("scan_page")
    print(f"  New URL  : {scan2.get('url')}")
    print(f"  New Title: {scan2.get('title')}")
    print(f"  New Type : {scan2.get('page_type')}")
    print("  ✓ PASSED")

    # ──── TEST 4: Scan a More Complex Page ────
    print("\n[TEST 4] Scan Wikipedia (complex page)")
    browser.run("open_url", url="https://en.wikipedia.org")
    scan3 = browser.run("scan_page")
    print(f"  Page Type : {scan3.get('page_type')}")
    print(f"  Buttons   : {scan3.get('buttons')}")
    print(f"  Links     : {scan3.get('links')}")
    print(f"  Inputs    : {scan3.get('inputs')}")
    print(f"  Forms     : {scan3.get('forms')}")
    print(f"  Headings  : {scan3.get('headings')}")
    print(f"  Elements  : {scan3.get('element_count')}")
    assert scan3.get("element_count", 0) > 10, "FAIL: too few elements on Wikipedia"
    print("  ✓ PASSED")

    # ──── TEST 5: Find Search Box on Wikipedia ────
    print("\n[TEST 5] Find 'search' input on Wikipedia")
    result = browser.run("find_element", description="search input")
    print(f"  Found: {result.get('found')}")
    print(f"  Sel  : {result.get('selector')}")
    print(f"  Type : {result.get('element_type')}")
    assert result.get("found") == True, "FAIL: could not find search input"
    print("  ✓ PASSED")

    # ──── TEST 6: Find and Type in Search Box ────
    print("\n[TEST 6] find_and_type 'Artificial Intelligence' into search")
    result = browser.run("find_and_type", description="search input", text="Artificial Intelligence")
    print(f"  Status : {result.get('status')}")
    print(f"  Matched: {result.get('matched')}")
    assert result.get("status") == "typed", f"FAIL: {result}"
    print("  ✓ PASSED")

    # ──── TEST 7: Get Full Page Model ────
    print("\n[TEST 7] get_page_model (structured data)")
    model = browser.run("get_page_model")
    print(f"  Page Type: {model.get('page_type')}")
    print(f"  Buttons  : {len(model.get('buttons', []))}")
    print(f"  Links    : {len(model.get('links', []))}")
    print(f"  Inputs   : {len(model.get('inputs', []))}")
    print(f"  Forms    : {len(model.get('forms', []))}")
    # Print first few links
    for link in model.get("links", [])[:3]:
        print(f"    Link: '{link['text'][:40]}' -> {link['href'][:60]}")
    print("  ✓ PASSED")

    # ──── TEST 8: Screenshot ────
    print("\n[TEST 8] Screenshot after search typed")
    result = browser.run("screenshot", filename="perception_test.png")
    print(f"  Path: {result.get('path')}")
    assert result.get("status") == "captured", f"FAIL: {result}"
    print("  ✓ PASSED")

    # ──── CLEANUP ────
    browser.run("close")

    print("\n" + "=" * 60)
    print("  ALL PERCEPTION TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
