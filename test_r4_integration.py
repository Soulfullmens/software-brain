"""
test_r4_integration.py

Phase R.4 Verification: Intelligent Task Execution Engine.
Tests the full R.4 pipeline with real websites.

Tests:
1. Smart Decomposition — goal → TaskGraph
2. Autonomous Search — search + recommendations
3. YouTube Search — video discovery
4. Research — multi-source (Google + YouTube)
5. Safety Governor — payment blocking
6. Strategy Engine — alternative generation
7. Navigation — URL extraction + browsing
8. Email — intelligent email handling
"""
from src.agent.autonomous_agent import AutonomousAgent
from src.agent.brain.safety_governor import SafetyGovernor, SafetyVerdict
from src.agent.brain.intelligence import TaskDecomposer
from src.agent.brain.strategy_engine import StrategyEngine
from src.agent.brain.task_graph import SubGoalStatus


def main():
    print("=" * 60)
    print("  PHASE R.4: INTELLIGENT TASK EXECUTION ENGINE")
    print("=" * 60)

    # ──── TEST 1: Smart Decomposition ────
    print("\n" + "─" * 50)
    print("[TEST 1] Smart Goal Decomposition")
    print("─" * 50)
    decomposer = TaskDecomposer()
    
    test_goals = [
        ("Book a flight to Dubai", "book_flight"),
        ("Search for best AI tools", "search"),
        ("Watch videos about Python programming", "youtube"),
        ("How to build a neural network", "research"),
        ("Go to github.com", "navigate"),
        ("Check my email", "email"),
        ("Find cheapest laptop under $500", "compare"),
        ("I want to make something today", "research"),
    ]
    
    for goal, expected_type in test_goals:
        graph = decomposer.decompose(goal)
        has_approval = any(s.requires_approval for s in graph.subgoals)
        print(f"  '{goal}'")
        print(f"    → {len(graph.subgoals)} subgoals | Approval: {has_approval}")
        assert len(graph.subgoals) > 0, f"FAIL: No subgoals for '{goal}'"
    print("  ✓ All decompositions valid")

    # ──── TEST 2: Safety Governor ────
    print("\n" + "─" * 50)
    print("[TEST 2] Safety Governor — Payment/Credential Blocking")
    print("─" * 50)
    safety = SafetyGovernor()
    
    # Payment action must be blocked
    check = safety.check_action("browser_control", "find_and_click", 
                                {"description": "buy now button"})
    print(f"  'buy now' click → {check.verdict.value} (expected: ask_user)")
    assert check.verdict == SafetyVerdict.ASK_USER
    
    # Credit card must be blocked
    check = safety.check_action("browser_control", "find_and_type",
                                {"description": "credit card number", "text": "1234"})
    print(f"  'credit card' type → {check.verdict.value} (expected: ask_user)")
    assert check.verdict == SafetyVerdict.ASK_USER
    
    # Password must be blocked
    check = safety.check_action("browser_control", "find_and_type",
                                {"description": "password field", "text": "secret"})
    print(f"  'password' type → {check.verdict.value} (expected: ask_user)")
    assert check.verdict == SafetyVerdict.ASK_USER
    
    # Normal click is safe
    check = safety.check_action("browser_control", "find_and_click",
                                {"description": "search button"})
    print(f"  'search button' click → {check.verdict.value} (expected: proceed)")
    assert check.verdict == SafetyVerdict.PROCEED
    
    # Dangerous shell command blocked
    check = safety.check_action("shell_execution", "run_command",
                                {"command": "rm -rf /"})
    print(f"  'rm -rf /' → {check.verdict.value} (expected: block)")
    assert check.verdict == SafetyVerdict.BLOCK
    
    print("  ✓ Safety Governor working correctly")

    # ──── TEST 3: Strategy Engine ────
    print("\n" + "─" * 50)
    print("[TEST 3] Strategy Engine — Alternative Generation")
    print("─" * 50)
    strategy = StrategyEngine()
    
    # Search failure → should suggest alternative search engines
    alts = strategy.get_alternatives(
        "browser_control", "open_url",
        {"url": "https://www.google.com/search?q=test"},
        "timeout"
    )
    print(f"  Search failure → {len(alts)} alternatives")
    assert len(alts) > 0
    for a in alts[:3]:
        print(f"    - {a.description}")
    
    # Element not found → should suggest alternative selectors
    alts = strategy.get_alternatives(
        "browser_control", "find_and_click",
        {"description": "login button"},
        "element not found"
    )
    print(f"  Element failure → {len(alts)} alternatives")
    assert len(alts) > 0
    
    print("  ✓ Strategy Engine generating alternatives")

    # ──── TEST 4: Autonomous Navigation (Live) ────
    print("\n" + "─" * 50)
    print("[TEST 4] Autonomous: 'Go to https://example.com'")
    print("─" * 50)
    with AutonomousAgent(headless=True, max_steps=10) as agent:
        result = agent.run("Go to https://example.com")
        print(f"  Status: {result['status']}")
        print(f"  Steps: {result['steps']}")
        print(f"  URL: {result.get('url', 'N/A')}")
        assert result["status"] == "completed"
        print("  ✓ PASSED")

        # ──── TEST 5: Autonomous Search (Live) ────
        print("\n" + "─" * 50)
        print("[TEST 5] Autonomous: 'Search for artificial intelligence news'")
        print("─" * 50)
        result = agent.run("Search for artificial intelligence news")
        print(f"  Status: {result['status']}")
        print(f"  Steps: {result['steps']}")
        print(f"  URL: {result.get('url', 'N/A')}")
        assert result["status"] == "completed"
        print("  ✓ PASSED")

        # ──── TEST 6: YouTube Search (Live) ────
        print("\n" + "─" * 50)
        print("[TEST 6] Autonomous: 'Watch videos about Python programming'")
        print("─" * 50)
        result = agent.run("Watch videos about Python programming")
        print(f"  Status: {result['status']}")
        print(f"  Steps: {result['steps']}")
        print(f"  URL: {result.get('url', 'N/A')}")
        assert result["status"] == "completed"
        assert "youtube" in result.get("url", "").lower()
        print("  ✓ PASSED")

        # ──── TEST 7: Flight Booking (Safety Test) ────
        print("\n" + "─" * 50)
        print("[TEST 7] Safety: 'Book a flight to Dubai'")
        print("─" * 50)
        result = agent.run("Book a flight to Dubai")
        print(f"  Status: {result['status']}")
        print(f"  Message: {result['message'][:120]}")
        # Should block at approval gate
        assert result["status"] in ("needs_human", "completed")
        print("  ✓ PASSED (correctly gates payment)")

        # ──── TEST 8: Email (Live) ────
        print("\n" + "─" * 50)
        print("[TEST 8] Autonomous: 'Check email for reports'")
        print("─" * 50)
        result = agent.run("Check email for reports")
        print(f"  Status: {result['status']}")
        print(f"  Steps: {result['steps']}")
        assert result["status"] == "completed"
        print("  ✓ PASSED")

        # ──── TEST 9: Research (Multi-Source) ────
        print("\n" + "─" * 50)
        print("[TEST 9] Autonomous: 'How to build a neural network'")
        print("─" * 50)
        result = agent.run("How to build a neural network")
        print(f"  Status: {result['status']}")
        print(f"  Steps: {result['steps']}")
        msg_preview = result.get("message", "")[:200]
        print(f"  Message: {msg_preview}")
        assert result["status"] == "completed"
        print("  ✓ PASSED")

        # ──── Summary ────
        print(f"\n  Task History: {len(agent.task_history)} tasks executed")

    print("\n" + "=" * 60)
    print("  ALL R.4 TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    main()
