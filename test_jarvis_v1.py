"""
test_jarvis_v1.py — Verification for Jarvis V1.5 product.

Tests:
  1. Context Memory (save/load/prune/frequent)
  2. Confusion Detector (rapid switches, new windows, errors, cursor hesitation,
                        scroll loops, repeated actions, undo-redo loops)
  3. Session Intelligence (record, predict, workflow detection, summary)
  4. Insight Pipeline (analysis → explanation → suggestions + confidence + recall + prediction)
  5. Risk Labels (🟢🟡🔴 on every suggestion)
  6. Confidence Scoring (High/Medium/Low with reasons)
  7. WHY Transparency (every suggestion explains itself)
  8. Guide Mode (visual-first: highlight → label → step)
  9. Assist Mode (safety gating)
  10. Failure Logging (structured log + summary)
  11. Authority Integration
  12. CLI argument parsing
"""
import os, sys, time, unittest, tempfile, shutil, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from agent.context_memory import ContextMemory
from agent.jarvis import (
    JarvisV1, InsightResult, Suggestion, RiskLevel, Confidence,
    ConfusionDetector, SessionIntelligence, VisualOverlay,
    RISK_ICONS, CONFIDENCE_ICONS
)
from agent.security.security_kernel import AuthorityLevel, ActionVerdict


# ═══════════════════════════════════════════════════════
# 1. CONTEXT MEMORY
# ═══════════════════════════════════════════════════════

class TestContextMemory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.mem = ContextMemory(memory_dir=self.tmp)
    
    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
    
    def test_remember_and_recall(self):
        self.mem.remember("chrome", "tabs", "google.com")
        self.mem.remember("chrome", "tabs", "github.com")
        result = self.mem.recall("chrome", "tabs", last_n=2)
        self.assertEqual(result, ["google.com", "github.com"])
    
    def test_recall_latest(self):
        self.mem.remember("vscode", "file", "main.py")
        self.mem.remember("vscode", "file", "test.py")
        self.assertEqual(self.mem.recall_latest("vscode", "file"), "test.py")
    
    def test_recall_empty(self):
        result = self.mem.recall("unknown", "key")
        self.assertEqual(result, [])
        self.assertIsNone(self.mem.recall_latest("unknown", "key"))
    
    def test_app_profile(self):
        self.mem.remember("notepad", "action", "save")
        self.mem.remember("notepad", "action", "copy")
        profile = self.mem.get_app_profile("notepad")
        self.assertIn("action", profile)
        self.assertEqual(profile["action"]["count"], 2)
        self.assertEqual(profile["action"]["latest"], "copy")
    
    def test_frequent_values(self):
        for _ in range(5):
            self.mem.remember("chrome", "sites", "google.com")
        for _ in range(3):
            self.mem.remember("chrome", "sites", "github.com")
        self.mem.remember("chrome", "sites", "rare.com")
        
        freq = self.mem.get_frequent("chrome", "sites", top_n=2)
        self.assertEqual(freq[0]["value"], "google.com")
        self.assertEqual(freq[0]["count"], 5)
    
    def test_list_apps(self):
        self.mem.remember("chrome", "x", 1)
        self.mem.remember("vscode", "x", 1)
        apps = self.mem.list_apps()
        self.assertIn("chrome", apps)
        self.assertIn("vscode", apps)
    
    def test_clear_app(self):
        self.mem.remember("notepad", "x", 1)
        self.mem.clear_app("notepad")
        self.assertEqual(self.mem.recall("notepad", "x"), [])
    
    def test_sanitize_names(self):
        self.mem.remember("My App (v2.0)", "key", "val")
        apps = self.mem.list_apps()
        self.assertTrue(any("my_app" in a for a in apps))
    
    def test_prune_old_entries(self):
        self.mem.remember("old_app", "key", "val")
        data = self.mem._load("old_app")
        data["key"][0]["ts"] = time.time() - (60 * 86400)
        self.mem._save("old_app", data)
        self.mem.prune("old_app")
        result = self.mem.recall("old_app", "key")
        self.assertEqual(result, [])
    
    def test_persistence(self):
        self.mem.remember("persist", "val", 42)
        mem2 = ContextMemory(memory_dir=self.tmp)
        self.assertEqual(mem2.recall_latest("persist", "val"), 42)


# ═══════════════════════════════════════════════════════
# 2. CONFUSION DETECTOR (expanded with repeated actions)
# ═══════════════════════════════════════════════════════

class TestConfusionDetector(unittest.TestCase):
    def setUp(self):
        self.detector = ConfusionDetector()
    
    def test_rapid_switching(self):
        results = []
        for title in ["App A", "App B", "App C", "App D"]:
            r = self.detector.observe(title)
            if r:
                results.append(r)
        self.assertIn("rapid_switching", results)
    
    def test_new_window(self):
        self.detector.observe("First Window")
        result = self.detector.observe("Totally New Window")
        self.assertEqual(result, "new_window")
    
    def test_error_detection(self):
        result = self.detector.observe("Some App", has_error_dialog=True)
        self.assertEqual(result, "error_detected")
    
    def test_no_confusion_normal_use(self):
        self.detector.observe("My App")
        result = self.detector.observe("My App")
        self.assertIsNone(result)
    
    def test_nudge_messages(self):
        msg = self.detector.get_nudge_message("rapid_switching")
        self.assertIn("Press J", msg)
        msg = self.detector.get_nudge_message("error_detected")
        self.assertIn("guidance", msg)
    
    def test_reset(self):
        self.detector.observe("A")
        self.detector.observe("B")
        self.detector.reset()
        result = self.detector.observe("C")
        self.assertIsNone(result)
    
    # Cursor hesitation tests
    def test_cursor_hover_detection(self):
        self.detector._last_mouse_pos = (100, 100)
        self.detector._hover_start = time.time() - 6
        result = self.detector.observe("App", mouse_pos=(105, 105))
        self.assertEqual(result, "cursor_hesitation")
    
    def test_repeated_hover(self):
        self.detector._last_mouse_pos = (150, 150)
        self.detector._hover_start = time.time()
        self.detector._hover_region_hits = 4
        result = self.detector.observe("App", mouse_pos=(160, 160))
        self.assertEqual(result, "repeated_hover")
    
    def test_scroll_loop_detection(self):
        result = None
        for d in ["up", "down", "up", "down", "up", "down", "up", "down"]:
            r = self.detector.observe_scroll(d)
            if r:
                result = r
        self.assertEqual(result, "scroll_loop")
    
    def test_no_scroll_loop_on_normal(self):
        for d in ["down", "down", "down"]:
            result = self.detector.observe_scroll(d)
        self.assertIsNone(result)
    
    def test_hesitation_nudge_messages(self):
        for reason in ["cursor_hesitation", "repeated_hover", "scroll_loop"]:
            msg = self.detector.get_nudge_message(reason)
            self.assertIn("Press J", msg)
    
    # NEW: Repeated failed action detection
    def test_repeated_action_detection(self):
        """Same action 3 times = struggle."""
        result = None
        for _ in range(3):
            r = self.detector.observe_repeated_action("click_save_button")
            if r:
                result = r
        self.assertEqual(result, "repeated_action")
    
    def test_undo_redo_loop(self):
        """Alternating actions = undo-redo loop."""
        result = None
        for action in ["undo", "redo", "undo", "redo"]:
            r = self.detector.observe_repeated_action(action)
            if r:
                result = r
        self.assertEqual(result, "undo_redo_loop")
    
    def test_no_repeated_action_on_varied(self):
        """Varied actions shouldn't trigger."""
        for action in ["open_file", "save_file", "close_tab"]:
            result = self.detector.observe_repeated_action(action)
        self.assertIsNone(result)
    
    def test_repeated_action_nudge_messages(self):
        for reason in ["repeated_action", "undo_redo_loop"]:
            msg = self.detector.get_nudge_message(reason)
            self.assertIn("Press J", msg)
    
    def test_reset_clears_action_history(self):
        self.detector.observe_repeated_action("click")
        self.detector.observe_repeated_action("click")
        self.detector.reset()
        # After reset, third "click" should NOT trigger (history cleared)
        result = self.detector.observe_repeated_action("click")
        self.assertIsNone(result)


# ═══════════════════════════════════════════════════════
# 3. SESSION INTELLIGENCE (NEW)
# ═══════════════════════════════════════════════════════

class TestSessionIntelligence(unittest.TestCase):
    def setUp(self):
        self.session = SessionIntelligence()
    
    def test_record_action(self):
        self.session.record("VSCode", "development", "Writing/editing code")
        self.assertEqual(len(self.session._chain), 1)
        self.assertEqual(self.session._chain[0]["app"], "VSCode")
    
    def test_chain_limit(self):
        for i in range(60):
            self.session.record(f"App{i}", "unknown", "stuff")
        self.assertEqual(len(self.session._chain), 50)
    
    def test_workflow_pattern_prediction(self):
        """After coding, predict 'Run tests'."""
        self.session.record("VSCode", "development", "Writing/editing code")
        pred = self.session.predict_next("VSCode", "development", "Writing/editing code")
        self.assertIsNotNone(pred)
        self.assertEqual(pred["source"], "workflow_pattern")
        self.assertIn("Run tests", pred["action"])
    
    def test_cross_app_prediction(self):
        """After debugging in IDE, predict 'Search error message' in browser."""
        self.session.record("VSCode", "development", "Debugging code")
        pred = self.session.predict_next("Chrome", "browser", "Debugging code")
        # This pattern is dev→browser for debugging
        # The key is (development, browser) for debugging
        # Actually predict_next uses current_intent which is "Debugging code"
        # but the pattern key uses prev category → current category
        # So it looks up (development, browser) → "Debugging code" → ["Search error message", ...]
        self.assertIsNotNone(pred)
        self.assertIn("Search", pred["action"])
    
    def test_session_flow_prediction(self):
        """If you did A→B before, predict B after A again."""
        self.session.record("VSCode", "development", "Writing/editing code")
        self.session.record("Chrome", "browser", "Searching for information")
        # Now record another coding session
        self.session.record("VSCode", "development", "Writing/editing code")
        pred = self.session.predict_next("VSCode", "development", "Writing/editing code")
        self.assertIsNotNone(pred)
        # Should find the session_flow or workflow_pattern
        self.assertIn(pred["source"], ["session_flow", "workflow_pattern"])
    
    def test_no_prediction_on_first_use(self):
        """No chain = no prediction."""
        pred = self.session.predict_next("NewApp", "unknown", "General use")
        self.assertIsNone(pred)
    
    def test_workflow_summary_empty(self):
        self.assertEqual(self.session.get_workflow_summary(), "No activity recorded yet.")
    
    def test_workflow_summary(self):
        self.session.record("VSCode", "development", "Writing/editing code")
        self.session.record("Chrome", "browser", "Searching for information")
        summary = self.session.get_workflow_summary()
        self.assertIn("VSCode", summary)
        self.assertIn("Chrome", summary)
        self.assertIn("→", summary)
    
    def test_detect_code_test_cycle(self):
        self.session.record("VSCode", "development", "Writing/editing code")
        self.session.record("Terminal", "development", "Running/writing tests")
        self.session.record("VSCode", "development", "Debugging code")
        workflow = self.session.detect_workflow()
        self.assertIn("code-test", workflow)
    
    def test_detect_research_workflow(self):
        self.session.record("VSCode", "development", "Writing code")
        self.session.record("Chrome", "browser", "Searching")
        self.session.record("Chrome", "browser", "Reading docs")
        workflow = self.session.detect_workflow()
        self.assertEqual(workflow, "research-and-implement")
    
    def test_no_workflow_too_few_actions(self):
        self.session.record("VSCode", "development", "code")
        self.assertIsNone(self.session.detect_workflow())
    
    def test_reset(self):
        self.session.record("A", "x", "y")
        self.session.reset()
        self.assertEqual(len(self.session._chain), 0)
    
    def test_habit_prediction_priority(self):
        """Habit predictions should outrank workflow patterns."""
        self.session.record("VSCode", "development", "Writing/editing code")
        # Mock memory with frequent intents
        class MockMemory:
            def get_frequent(self, app, key, top_n=5):
                return [
                    {"value": "Writing/editing code", "count": 10},
                    {"value": "Debugging code", "count": 6}
                ]
        
        pred = self.session.predict_next(
            "VSCode", "development", "Writing/editing code",
            memory=MockMemory()
        )
        self.assertIsNotNone(pred)
        self.assertEqual(pred["source"], "habit")
        self.assertIn("Debugging code", pred["action"])


# ═══════════════════════════════════════════════════════
# 4. CONFIDENCE SCORING
# ═══════════════════════════════════════════════════════

class TestConfidenceScoring(unittest.TestCase):
    def test_confidence_levels_exist(self):
        levels = [Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW]
        self.assertEqual(len(levels), 3)
    
    def test_all_levels_have_icons(self):
        for level in Confidence:
            self.assertIn(level, CONFIDENCE_ICONS)
    
    def test_high_confidence(self):
        j = JarvisV1()
        result = InsightResult(
            app_name="Chrome", app_category="browser",
            screen_text="a" * 50, window_title="Google - Chrome"
        )
        conf, reasons = j._compute_confidence(result)
        self.assertEqual(conf, Confidence.HIGH)
        self.assertTrue(any("Known" in r for r in reasons))
    
    def test_low_confidence(self):
        j = JarvisV1()
        result = InsightResult(
            app_name="Unknown", app_category="unknown",
            screen_text="", window_title=""
        )
        conf, reasons = j._compute_confidence(result)
        self.assertEqual(conf, Confidence.LOW)
    
    def test_confidence_in_display(self):
        result = InsightResult(
            app_name="Test", confidence=Confidence.LOW,
            confidence_reasons=["Unknown application", "No OCR text"],
            context_summary="test"
        )
        display = result.display()
        self.assertIn("CONFIDENCE", display)
        self.assertIn("LOW", display)
        self.assertIn("may be wrong", display)
    
    def test_high_confidence_no_warning(self):
        result = InsightResult(
            app_name="Chrome", confidence=Confidence.HIGH,
            confidence_reasons=["Known application"],
            context_summary="browsing"
        )
        display = result.display()
        self.assertNotIn("may be wrong", display)


# ═══════════════════════════════════════════════════════
# 5. WHY TRANSPARENCY (NEW)
# ═══════════════════════════════════════════════════════

class TestWHYTransparency(unittest.TestCase):
    def test_suggestion_has_why_field(self):
        s = Suggestion("Save file", RiskLevel.SAFE, "shortcut", why="Unsaved changes detected")
        self.assertEqual(s.why, "Unsaved changes detected")
    
    def test_why_in_display(self):
        s = Suggestion("Save file", RiskLevel.SAFE, "shortcut", why="Unsaved changes detected")
        display = s.display(1)
        self.assertIn("WHY:", display)
        self.assertIn("Unsaved changes detected", display)
    
    def test_no_why_no_line(self):
        s = Suggestion("Open tab", RiskLevel.SAFE, "shortcut")
        display = s.display(1)
        self.assertNotIn("WHY:", display)
    
    def test_why_on_browser_suggestion(self):
        """Browser suggestions should have WHY."""
        j = JarvisV1()
        j._last_insight = InsightResult(
            app_name="Chrome", app_category="browser", screen_text="test"
        )
        suggestions = j._generate_suggestions(j._last_insight)
        for s in suggestions:
            if s.action_type != "guide" or s.why:
                self.assertTrue(len(s.why) > 0, f"Missing WHY on: {s.text}")
    
    def test_why_on_error_suggestion(self):
        """Error-triggered suggestions should explain why."""
        j = JarvisV1()
        result = InsightResult(
            app_name="VSCode", app_category="development",
            screen_text="error: module not found"
        )
        suggestions = j._generate_suggestions(result)
        error_suggestions = [s for s in suggestions if "error" in s.text.lower() or "Error" in s.why]
        self.assertTrue(len(error_suggestions) > 0)
        self.assertIn("Error", error_suggestions[0].why)


# ═══════════════════════════════════════════════════════
# 6. MEMORY RECALL PROMPTS
# ═══════════════════════════════════════════════════════

class TestMemoryRecall(unittest.TestCase):
    def test_recall_prompt_empty_first_use(self):
        j = JarvisV1()
        result = InsightResult(app_name="NewApp_test_unique_xyz")
        recall = j._generate_recall(result)
        self.assertEqual(recall, "")
    
    def test_recall_prompt_after_memory(self):
        j = JarvisV1()
        j.memory.remember("TestRecallApp", "intents", "Debugging code")
        result = InsightResult(app_name="TestRecallApp", likely_intent="Writing tests")
        recall = j._generate_recall(result)
        self.assertIn("Debugging code", recall)
    
    def test_recall_in_display(self):
        result = InsightResult(
            app_name="Test", recall_prompt="Last time: writing code",
            context_summary="test"
        )
        display = result.display()
        self.assertIn("Last time: writing code", display)


# ═══════════════════════════════════════════════════════
# 7. RISK LABELS
# ═══════════════════════════════════════════════════════

class TestRiskLabels(unittest.TestCase):
    def test_all_risk_levels_have_icons(self):
        for level in RiskLevel:
            self.assertIn(level, RISK_ICONS)
    
    def test_risk_ordering(self):
        self.assertEqual(RISK_ICONS[RiskLevel.SAFE], "🟢")
        self.assertEqual(RISK_ICONS[RiskLevel.MODIFIES], "🟡")
        self.assertEqual(RISK_ICONS[RiskLevel.RISKY], "🔴")
    
    def test_suggestion_carries_risk(self):
        s = Suggestion("Open file", RiskLevel.SAFE, "navigate")
        self.assertEqual(s.risk, RiskLevel.SAFE)


# ═══════════════════════════════════════════════════════
# 8. GUIDE MODE (VISUAL-FIRST)
# ═══════════════════════════════════════════════════════

class TestGuideMode(unittest.TestCase):
    def test_guide_without_insight(self):
        j = JarvisV1()
        result = j.guide(1)
        self.assertIn("error", result)
    
    def test_guide_generates_steps(self):
        j = JarvisV1()
        j._last_insight = InsightResult(
            app_name="Chrome",
            suggestions=[
                Suggestion("Open new tab", RiskLevel.SAFE, "shortcut", {"key": "ctrl+t"})
            ]
        )
        result = j.guide(1)
        self.assertIn("steps", result)
        self.assertGreater(len(result["steps"]), 0)
        self.assertIn("CTRL", result["steps"][1])
    
    def test_guide_has_visual_hints(self):
        j = JarvisV1()
        j._last_insight = InsightResult(
            app_name="Chrome",
            suggestions=[
                Suggestion("Open tab", RiskLevel.SAFE, "shortcut", {"key": "ctrl+t"})
            ]
        )
        result = j.guide(1)
        self.assertIn("visual_hints", result)
        self.assertGreater(len(result["visual_hints"]), 0)
        self.assertEqual(result["visual_hints"][0]["type"], "keyboard")
    
    def test_guide_navigate_has_visual_hint(self):
        j = JarvisV1()
        j._last_insight = InsightResult(
            app_name="Chrome",
            suggestions=[
                Suggestion("Go to settings", RiskLevel.SAFE, "navigate", {"path": "Settings"})
            ]
        )
        result = j.guide(1)
        self.assertIn("visual_hints", result)
        self.assertTrue(any(h["type"] == "screen_region" for h in result["visual_hints"]))
    
    def test_guide_invalid_index(self):
        j = JarvisV1()
        j._last_insight = InsightResult(suggestions=[])
        result = j.guide(5)
        self.assertIn("error", result)


# ═══════════════════════════════════════════════════════
# 9. ASSIST MODE
# ═══════════════════════════════════════════════════════

class TestAssistMode(unittest.TestCase):
    def test_assist_without_insight(self):
        j = JarvisV1()
        result = j.assist(1)
        self.assertIn("error", result)
    
    def test_risky_action_refused(self):
        j = JarvisV1()
        j._last_insight = InsightResult(
            app_name="Test",
            suggestions=[
                Suggestion("Dangerous thing", RiskLevel.RISKY, "execute")
            ]
        )
        result = j.assist(1)
        self.assertIn("steps", result)  # Should fall back to guide


# ═══════════════════════════════════════════════════════
# 10. FAILURE LOGGING
# ═══════════════════════════════════════════════════════

class TestFailureLogging(unittest.TestCase):
    def setUp(self):
        self.j = JarvisV1()
        self.tmp = tempfile.mkdtemp()
        self.j._failure_log_path = os.path.join(self.tmp, "failures.jsonl")
    
    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
    
    def test_log_failure(self):
        result = self.j.log_failure("Chrome", "settings", "help with privacy", "generic tips", "didn't recognize settings page")
        self.assertTrue(result["logged"])
        self.assertEqual(result["total"], 1)
    
    def test_failure_count(self):
        self.j.log_failure("A", "t", "e", "a", "r1")
        self.j.log_failure("B", "t", "e", "a", "r2")
        self.assertEqual(self.j.failure_count(), 2)
    
    def test_failure_summary(self):
        for _ in range(3):
            self.j.log_failure("Chrome", "settings", "e", "a", "bad OCR")
        self.j.log_failure("VSCode", "editor", "e", "a", "wrong suggestion")
        
        summary = self.j.failure_summary()
        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["worst_apps"][0]["app"], "Chrome")
        self.assertEqual(summary["worst_apps"][0]["failures"], 3)
    
    def test_failure_stores_insight_context(self):
        self.j._last_insight = InsightResult(
            app_name="Chrome", confidence=Confidence.LOW,
            context_summary="browsing"
        )
        self.j.log_failure("Chrome", "t", "e", "a", "reason")
        with open(self.j._failure_log_path) as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["last_insight"]["confidence"], "low")
    
    def test_empty_failure_summary(self):
        summary = self.j.failure_summary()
        self.assertEqual(summary["total"], 0)


# ═══════════════════════════════════════════════════════
# 11. NEXT LIKELY ACTION IN DISPLAY
# ═══════════════════════════════════════════════════════

class TestNextLikelyActionDisplay(unittest.TestCase):
    def test_prediction_in_display(self):
        """Display should show prediction when available."""
        result = InsightResult(
            app_name="VSCode", context_summary="coding"
        )
        result._prediction = {
            "action": "Run tests",
            "confidence": "medium",
            "source": "workflow_pattern"
        }
        display = result.display()
        self.assertIn("NEXT:", display)
        self.assertIn("Run tests", display)
        self.assertIn("workflow_pattern", display)
    
    def test_no_prediction_no_display(self):
        """Display should NOT show prediction section when None."""
        result = InsightResult(app_name="Test", context_summary="test")
        display = result.display()
        self.assertNotIn("NEXT:", display)
    
    def test_high_confidence_icon(self):
        """High confidence predictions get green icon."""
        result = InsightResult(app_name="Test", context_summary="test")
        result._prediction = {
            "action": "Debug code",
            "confidence": "high",
            "source": "habit"
        }
        display = result.display()
        self.assertIn("🟩", display)


# ═══════════════════════════════════════════════════════
# 12. JARVIS CORE
# ═══════════════════════════════════════════════════════

class TestJarvisCore(unittest.TestCase):
    def test_creates_with_default_authority(self):
        j = JarvisV1()
        self.assertEqual(j.authority, AuthorityLevel.SAFE)
    
    def test_creates_with_custom_authority(self):
        j = JarvisV1(authority=AuthorityLevel.EXPERT)
        self.assertEqual(j.authority, AuthorityLevel.EXPERT)
    
    def test_has_all_modules(self):
        j = JarvisV1()
        self.assertIsNotNone(j.screen)
        self.assertIsNotNone(j.apps)
        self.assertIsNotNone(j.desktop)
        self.assertIsNotNone(j.fs)
        self.assertIsNotNone(j.security)
        self.assertIsNotNone(j.confusion)
        self.assertIsNotNone(j.memory)
        self.assertIsNotNone(j.session)  # V1.5
    
    def test_session_logging(self):
        j = JarvisV1()
        j._log("test", "detail")
        self.assertEqual(len(j._session_log), 1)
    
    def test_has_prediction_state(self):
        j = JarvisV1()
        self.assertIsNone(j._last_prediction)


# ═══════════════════════════════════════════════════════
# 13. CLI PARSING
# ═══════════════════════════════════════════════════════

class TestCLI(unittest.TestCase):
    def test_import_cli(self):
        sys.path.insert(0, os.path.dirname(__file__))
        import jarvis_cli
        self.assertTrue(hasattr(jarvis_cli, 'main'))


if __name__ == '__main__':
    print("═" * 50)
    print("  JARVIS V1.5 — PRODUCT VERIFICATION")
    print("═" * 50)
    unittest.main(verbosity=2)
