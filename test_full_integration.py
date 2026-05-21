"""
test_full_integration.py

Full system integration test.
Tests the complete Agent pipeline: Interpreter -> Planner -> Executor -> Evaluator
for BROWSE_WEB, existing intents, and perception.
"""
from src.agent.core import Agent
from src.agent.planner import RuleBasedPlanner


def main():
    print("=" * 60)
    print("  FULL SYSTEM INTEGRATION TEST")
    print("=" * 60)

    planner = RuleBasedPlanner()
    agent = Agent(planner)

    # Verify all tools are registered
    print(f"\n[Registry] Tools: {list(agent.tools.keys())}")
    assert "browser_control" in agent.tools, "FAIL: BrowserControlTool not registered"
    assert "email_communication" in agent.tools, "FAIL: EmailTool not registered"
    assert "excel_processing" in agent.tools, "FAIL: ExcelTool not registered"
    print("  ✓ All tools registered")

    # ──── TEST 1: Browse Web (via Agent pipeline) ────
    print("\n" + "=" * 40)
    print("[TEST 1] Agent: 'Go to example.com'")
    results = agent.run("Go to example.com")
    print(f"  Steps: {len(results)}")
    for r in results:
        action = r.get("action")
        if action:
            print(f"  Action: {action.tool_name}.{action.command}")
        result = r.get("result", {})
        if isinstance(result, dict):
            print(f"  Result: {dict(list(result.items())[:3])}")
        evaluation = r.get("evaluation")
        if evaluation:
            print(f"  Eval: success={evaluation.success}")
    assert len(results) > 0, "FAIL: No results"
    print("  ✓ PASSED")

    # ──── TEST 2: Search Google (via Agent pipeline) ────
    print("\n" + "=" * 40)
    print("[TEST 2] Agent: 'Search Google for AI agents'")
    results = agent.run("Search Google for AI agents")
    print(f"  Steps: {len(results)}")
    for r in results:
        action = r.get("action")
        if action:
            print(f"  Action: {action.tool_name}.{action.command}")
        result = r.get("result", {})
        if isinstance(result, dict) and result.get("page_type"):
            print(f"  Page Type: {result.get('page_type')}")
            print(f"  Elements: {result.get('element_count')}")
    assert len(results) > 0, "FAIL: No results"
    print("  ✓ PASSED")

    # ──── TEST 3: Revenue Workflow (unchanged) ────
    print("\n" + "=" * 40)
    print("[TEST 3] Agent: 'Check email for Sales Report'")
    results = agent.run("Check email for Sales Report")
    print(f"  Steps: {len(results)}")
    assert len(results) > 0, "FAIL: Revenue workflow broken"
    print("  ✓ PASSED")

    # ──── CLEANUP: Close browser ────
    browser = agent.tools.get("browser_control")
    if browser and browser._page:
        browser.run("close")

    print("\n" + "=" * 60)
    print("  ALL INTEGRATION TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
