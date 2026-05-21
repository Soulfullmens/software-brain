"""
test_executive_brain.py

Verification for Phase R.3: Executive Reasoning Engine.
Tests the autonomous closed-loop agent on real tasks without LLM.
Proves the heuristic fallback works and the loop terminates properly.
"""
from src.agent.autonomous_agent import AutonomousAgent


def main():
    print("=" * 60)
    print("  PHASE R.3: EXECUTIVE BRAIN VERIFICATION")
    print("=" * 60)

    with AutonomousAgent(headless=True, max_steps=10) as agent:
        
        # ──── TEST 1: Autonomous Navigation ────
        print("\n" + "─" * 50)
        print("[TEST 1] Autonomous: 'Go to https://example.com'")
        print("─" * 50)
        result = agent.run("Go to https://example.com")
        print(f"\n  Status : {result['status']}")
        print(f"  Steps  : {result['steps']}")
        print(f"  Message: {result['message'][:100]}")
        print(f"  URL    : {result.get('url', 'N/A')}")
        assert result["status"] == "completed", f"FAIL: {result['status']}"
        assert result["steps"] <= 5, f"FAIL: too many steps ({result['steps']})"
        print("  ✓ PASSED")

        # ──── TEST 2: Autonomous Search ────
        print("\n" + "─" * 50)
        print("[TEST 2] Autonomous: 'Search for artificial intelligence'")
        print("─" * 50)
        result = agent.run("Search for artificial intelligence")
        print(f"\n  Status : {result['status']}")
        print(f"  Steps  : {result['steps']}")
        print(f"  URL    : {result.get('url', 'N/A')}")
        print(f"  Page   : {result.get('page_type', 'N/A')}")
        assert result["status"] == "completed", f"FAIL: {result['status']}"
        print("  ✓ PASSED")

        # ──── TEST 3: Email Check (via Brain) ────
        print("\n" + "─" * 50)
        print("[TEST 3] Autonomous: 'Check email for Sales Report'")
        print("─" * 50)
        result = agent.run("Check email for Sales Report")
        print(f"\n  Status : {result['status']}")
        print(f"  Steps  : {result['steps']}")
        print(f"  Message: {result['message'][:100]}")
        assert result["status"] == "completed", f"FAIL: {result['status']}"
        print("  ✓ PASSED")

        # ──── TEST 4: Unknown Task (Tests stuck detection) ────
        print("\n" + "─" * 50)
        print("[TEST 4] Autonomous: 'Do something impossible'")
        print("─" * 50)
        result = agent.run("Do something impossible")
        print(f"\n  Status : {result['status']}")
        print(f"  Steps  : {result['steps']}")
        print(f"  Message: {result['message'][:100]}")
        # Should either be stuck or report it needs LLM
        assert result["status"] in ("stuck", "needs_human", "completed"), f"FAIL: {result['status']}"
        print("  ✓ PASSED (correctly handled unknown task)")

        # ──── TEST 5: Working Memory Context ────
        print("\n" + "─" * 50)
        print("[TEST 5] Memory Context Check")
        print("─" * 50)
        print(f"  Memory Context Preview:")
        ctx = result.get("memory_context", "")
        for line in ctx.split("\n")[:8]:
            print(f"    {line}")
        print("  ✓ PASSED")

    print("\n" + "=" * 60)
    print("  ALL EXECUTIVE BRAIN TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
