"""
test_v21_integration.py — Verify all V2.1 audit fixes and upgrades.

Tests:
  1. ToolResult dataclass works
  2. VerificationLoop init/check/validate cycle
  3. ExpertRouter loads all 7 experts and routes correctly
  4. Expert prompt files all exist and are non-empty
  5. ClaudeAgent wiring (import-only — no LLM calls)
"""
import os
import sys
import unittest

# Ensure project root is on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


# ═══════════════════════════════════════════════════════
# 1. TOOL RESULT
# ═══════════════════════════════════════════════════════

class TestToolResult(unittest.TestCase):

    def test_import(self):
        from src.agent.tool import Tool, ToolResult
        # Dataclass fields live in __dataclass_fields__, not as class attrs
        fields = ToolResult.__dataclass_fields__
        self.assertIn("success", fields)
        self.assertIn("output", fields)
        self.assertIn("error", fields)
        self.assertIn("metadata", fields)

    def test_create_success(self):
        from src.agent.tool import ToolResult
        r = ToolResult(success=True, output="done")
        self.assertTrue(r.success)
        self.assertEqual(r.output, "done")
        self.assertIsNone(r.error)
        self.assertEqual(r.metadata, {})

    def test_create_failure(self):
        from src.agent.tool import ToolResult
        r = ToolResult(success=False, error="broken")
        self.assertFalse(r.success)
        self.assertEqual(r.error, "broken")

    def test_tool_init(self):
        from src.agent.tool import Tool
        class DummyTool(Tool):
            def run(self, action, **kw):
                return None
        t = DummyTool(name="test_tool", description="A test tool.")
        self.assertEqual(t.name, "test_tool")
        self.assertEqual(t.description, "A test tool.")


# ═══════════════════════════════════════════════════════
# 2. VERIFICATION LOOP
# ═══════════════════════════════════════════════════════

class TestVerificationLoop(unittest.TestCase):

    def setUp(self):
        from src.agent.tools.verification import VerificationLoop
        self.vl = VerificationLoop()

    def test_init_action(self):
        result = self.vl.run("init", goal="Test Suite")
        self.assertTrue(result.success)
        self.assertIn("Test Suite", result.output)
        self.assertIn("session_id", result.metadata)

    def test_check_without_init_fails(self):
        vl = self.__class__.__new__(self.__class__)
        from src.agent.tools.verification import VerificationLoop
        vl2 = VerificationLoop()
        result = vl2.run("check", command="echo hi")
        self.assertFalse(result.success)
        self.assertIn("No active session", result.error)

    def test_check_passing_command(self):
        self.vl.run("init", goal="Echo Test")
        result = self.vl.run("check", command="echo hello")
        self.assertTrue(result.success)
        self.assertIn("PASSED", result.output)

    def test_check_failing_command(self):
        self.vl.run("init", goal="Fail Test")
        # Use a command that will fail
        result = self.vl.run("check", command="python -c \"raise ValueError('boom')\"")
        self.assertFalse(result.success)
        self.assertIn("FAILED", result.output)

    def test_validate_pass(self):
        self.vl.run("init", goal="All Pass")
        self.vl.run("check", command="echo ok")
        result = self.vl.run("validate")
        self.assertTrue(result.success)
        self.assertIn("PASS", result.output)
        self.assertIn("CERTIFICATE", result.output)

    def test_validate_fail(self):
        self.vl.run("init", goal="Has Failures")
        self.vl.run("check", command="python -c \"exit(1)\"")
        result = self.vl.run("validate")
        self.assertFalse(result.success)
        self.assertIn("FAIL", result.output)

    def test_status_no_session(self):
        from src.agent.tools.verification import VerificationLoop
        fresh = VerificationLoop()
        result = fresh.run("status")
        self.assertTrue(result.success)
        self.assertIn("No active", result.output)

    def test_unknown_action(self):
        result = self.vl.run("explode")
        self.assertFalse(result.success)
        self.assertIn("Unknown action", result.error)

    def test_no_command_error(self):
        self.vl.run("init", goal="No Cmd")
        result = self.vl.run("check")
        self.assertFalse(result.success)
        self.assertIn("command", result.error.lower())

    def test_schema(self):
        schema = self.vl.get_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("action", schema["properties"])


# ═══════════════════════════════════════════════════════
# 3. EXPERT ROUTER
# ═══════════════════════════════════════════════════════

class TestExpertRouter(unittest.TestCase):

    def setUp(self):
        from src.agent.expert_router import ExpertRouter
        self.router = ExpertRouter()

    def test_loads_all_experts(self):
        experts = self.router.available_experts
        expected = [
            "coding_expert", "creative_expert", "engineering_architect",
            "engineering_expert", "medical_expert", "security_expert",
            "strategic_planner",
        ]
        for exp in expected:
            self.assertIn(exp, experts, f"Missing expert: {exp}")
        self.assertEqual(len(experts), 7)

    def test_security_routing(self):
        name = self.router.select_expert_name("review this code for SQL injection vulnerabilities")
        self.assertEqual(name, "security_expert")

    def test_coding_routing(self):
        name = self.router.select_expert_name("debug this python function with a list comprehension bug")
        self.assertEqual(name, "coding_expert")

    def test_medical_routing(self):
        name = self.router.select_expert_name("explain the pharmacology of metformin and its clinical use")
        self.assertEqual(name, "medical_expert")

    def test_engineering_routing(self):
        name = self.router.select_expert_name("design a drone flight controller with IMU sensor fusion")
        self.assertEqual(name, "engineering_expert")

    def test_architect_routing(self):
        name = self.router.select_expert_name("design a microservice architecture for a distributed payment system")
        self.assertEqual(name, "engineering_architect")

    def test_creative_routing(self):
        name = self.router.select_expert_name("create a brand strategy and visual marketing campaign")
        self.assertEqual(name, "creative_expert")

    def test_planner_routing(self):
        name = self.router.select_expert_name("create a roadmap with milestones and risk matrix for this project")
        self.assertEqual(name, "strategic_planner")

    def test_no_match_returns_none(self):
        name = self.router.select_expert_name("hello, how are you today?")
        self.assertIsNone(name)

    def test_build_system_prompt_with_expert(self):
        base = "You are a helpful assistant."
        prompt = self.router.build_system_prompt(
            "audit this for XSS vulnerabilities", base
        )
        self.assertIn(base, prompt)
        self.assertIn("EXPERT MODE", prompt)
        self.assertIn("SECURITY", prompt)

    def test_build_system_prompt_no_match(self):
        base = "You are a helpful assistant."
        prompt = self.router.build_system_prompt("how's the weather?", base)
        self.assertEqual(prompt, base)

    def test_get_prompt_by_name(self):
        content = self.router.get_prompt("medical_expert")
        self.assertIsNotNone(content)
        self.assertIn("Medical", content)

    def test_score_query_returns_all_experts(self):
        scores = self.router.score_query("build a rocket with embedded sensors")
        self.assertIsInstance(scores, dict)
        self.assertGreater(len(scores), 0)


# ═══════════════════════════════════════════════════════
# 4. EXPERT PROMPT FILES
# ═══════════════════════════════════════════════════════

class TestExpertFiles(unittest.TestCase):

    EXPERTS_DIR = os.path.join(ROOT, "src", "agent", "prompts", "experts")
    EXPECTED_FILES = [
        "coding_expert.md", "creative_expert.md", "engineering_architect.md",
        "engineering_expert.md", "medical_expert.md", "security_expert.md",
        "strategic_planner.md",
    ]

    def test_all_files_exist(self):
        for fname in self.EXPECTED_FILES:
            path = os.path.join(self.EXPERTS_DIR, fname)
            self.assertTrue(os.path.exists(path), f"Missing: {fname}")

    def test_all_files_nonempty(self):
        for fname in self.EXPECTED_FILES:
            path = os.path.join(self.EXPERTS_DIR, fname)
            size = os.path.getsize(path)
            self.assertGreater(size, 500, f"{fname} is too small ({size} bytes)")

    def test_all_files_have_protocol_header(self):
        for fname in self.EXPECTED_FILES:
            path = os.path.join(self.EXPERTS_DIR, fname)
            with open(path, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
            self.assertTrue(first_line.startswith("#"), f"{fname} missing # header")


# ═══════════════════════════════════════════════════════
# 5. HOOKS DIRECTORY
# ═══════════════════════════════════════════════════════

class TestHooksExist(unittest.TestCase):

    HOOKS_DIR = os.path.join(ROOT, "src", "agent", "hooks")

    def test_hooks_directory_exists(self):
        self.assertTrue(os.path.isdir(self.HOOKS_DIR))

    def test_refresh_brain_exists(self):
        self.assertTrue(os.path.exists(os.path.join(self.HOOKS_DIR, "refresh_brain.sh")))

    def test_session_learn_exists(self):
        self.assertTrue(os.path.exists(os.path.join(self.HOOKS_DIR, "session_learn.js")))

    def test_token_budget_tracker_exists(self):
        self.assertTrue(os.path.exists(os.path.join(self.HOOKS_DIR, "token_budget_tracker.js")))


# ═══════════════════════════════════════════════════════
# 6. ENV FILE
# ═══════════════════════════════════════════════════════

class TestEnvFile(unittest.TestCase):

    ENV_PATH = os.path.join(ROOT, ".env")

    def test_env_has_storage_path(self):
        with open(self.ENV_PATH, "r") as f:
            content = f.read()
        self.assertIn("AGENT_STORAGE_PATH", content)

    def test_env_has_ollama_models(self):
        with open(self.ENV_PATH, "r") as f:
            content = f.read()
        self.assertIn("OLLAMA_MODELS", content)


if __name__ == "__main__":
    print("═" * 55)
    print("  V2.1 INTEGRATION AUDIT — VERIFICATION SUITE")
    print("═" * 55)
    unittest.main(verbosity=2)
