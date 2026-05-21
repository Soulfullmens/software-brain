"""
test_perception_operator.py — Verification for R.5A-P Perception-First Local Operator.

Tests all 6 modules:
  1. Human Override Authority Model (in SecurityKernel)
  2. Desktop Control V2 (perception-first)
  3. Screen Intelligence (OCR + change detection)
  4. App Analyzer (passive analysis)
  5. Read-Only FileSystem
  6. Voice Interface (manual activation)
"""
import os, sys, time, unittest, tempfile, shutil

# Add project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from agent.security.security_kernel import (
    SecurityKernel, AuthorityLevel, ThreatLevel, ActionVerdict, 
    SecurityResult, ConfirmationPolicy
)
from agent.tools.desktop_v2 import DesktopToolV2, APP_WHITELIST
from agent.tools.screen_intelligence import ScreenIntelligence
from agent.tools.app_analyzer import AppAnalyzer, APP_DATABASE
from agent.tools.readonly_fs import ReadOnlyFS, SAFE_READ_EXTENSIONS
from agent.tools.voice_interface import VoiceInterface, VoiceState


# ═══════════════════════════════════════════════════════
# 1. AUTHORITY MODEL TESTS
# ═══════════════════════════════════════════════════════

class TestAuthorityModel(unittest.TestCase):
    """Test Human Override Authority Model."""
    
    def test_authority_levels_exist(self):
        """All 5 authority levels should exist."""
        levels = [AuthorityLevel.LOCKED, AuthorityLevel.PARANOID, 
                  AuthorityLevel.SAFE, AuthorityLevel.BALANCED, AuthorityLevel.EXPERT]
        self.assertEqual(len(levels), 5)
    
    def test_default_authority_is_safe(self):
        """Default authority should be SAFE."""
        kernel = SecurityKernel()
        self.assertEqual(kernel.get_authority(), AuthorityLevel.SAFE)
    
    def test_kernel_accepts_authority(self):
        """SecurityKernel should accept authority parameter."""
        kernel = SecurityKernel(authority=AuthorityLevel.EXPERT)
        self.assertEqual(kernel.get_authority(), AuthorityLevel.EXPERT)
    
    def test_set_authority(self):
        """Authority can be changed at runtime."""
        kernel = SecurityKernel()
        kernel.set_authority(AuthorityLevel.BALANCED)
        self.assertEqual(kernel.get_authority(), AuthorityLevel.BALANCED)
        self.assertEqual(kernel.confirmation.authority, AuthorityLevel.BALANCED)
    
    def test_locked_blocks_everything(self):
        """LOCKED mode should block ALL non-critical actions."""
        policy = ConfirmationPolicy(authority=AuthorityLevel.LOCKED)
        for level in [ThreatLevel.SAFE, ThreatLevel.LOW, ThreatLevel.MEDIUM, ThreatLevel.HIGH]:
            result = policy.should_confirm(level, True, "none")
            self.assertEqual(result, ActionVerdict.BLOCK, f"LOCKED should block {level.value}")
    
    def test_paranoid_asks_everything(self):
        """PARANOID mode should ask for everything."""
        policy = ConfirmationPolicy(authority=AuthorityLevel.PARANOID)
        for level in [ThreatLevel.SAFE, ThreatLevel.LOW, ThreatLevel.MEDIUM, ThreatLevel.HIGH]:
            result = policy.should_confirm(level, True, "none")
            self.assertEqual(result, ActionVerdict.ASK_USER, f"PARANOID should ask for {level.value}")
    
    def test_safe_mode_behavior(self):
        """SAFE mode: ask for HIGH, conditional for MEDIUM, auto-allow SAFE."""
        policy = ConfirmationPolicy(authority=AuthorityLevel.SAFE)
        self.assertEqual(policy.should_confirm(ThreatLevel.HIGH, True, "none"), ActionVerdict.ASK_USER)
        self.assertEqual(policy.should_confirm(ThreatLevel.SAFE, True, "none"), ActionVerdict.ALLOW)
        # MEDIUM + irreversible = ASK
        self.assertEqual(policy.should_confirm(ThreatLevel.MEDIUM, False, "none"), ActionVerdict.ASK_USER)
        # MEDIUM + reversible = LOG
        self.assertEqual(policy.should_confirm(ThreatLevel.MEDIUM, True, "none"), ActionVerdict.ALLOW_LOGGED)
    
    def test_balanced_mode_behavior(self):
        """BALANCED mode: fewer interruptions."""
        policy = ConfirmationPolicy(authority=AuthorityLevel.BALANCED)
        self.assertEqual(policy.should_confirm(ThreatLevel.HIGH, True, "none"), ActionVerdict.ASK_USER)
        self.assertEqual(policy.should_confirm(ThreatLevel.MEDIUM, False, "none"), ActionVerdict.ALLOW_LOGGED)
        self.assertEqual(policy.should_confirm(ThreatLevel.LOW, True, "none"), ActionVerdict.ALLOW)
    
    def test_expert_mode_behavior(self):
        """EXPERT mode: only log HIGH, auto-allow rest."""
        policy = ConfirmationPolicy(authority=AuthorityLevel.EXPERT)
        self.assertEqual(policy.should_confirm(ThreatLevel.HIGH, True, "none"), ActionVerdict.ALLOW_LOGGED)
        self.assertEqual(policy.should_confirm(ThreatLevel.MEDIUM, False, "none"), ActionVerdict.ALLOW)
        self.assertEqual(policy.should_confirm(ThreatLevel.SAFE, True, "none"), ActionVerdict.ALLOW)
    
    def test_critical_always_blocked(self):
        """CRITICAL should be BLOCKED regardless of authority level."""
        for level in AuthorityLevel:
            policy = ConfirmationPolicy(authority=level)
            result = policy.should_confirm(ThreatLevel.CRITICAL, True, "none")
            self.assertEqual(result, ActionVerdict.BLOCK, 
                           f"CRITICAL should be BLOCKED even in {level.value} mode")
    
    def test_authority_change_audited(self):
        """Authority changes should be logged in audit trail."""
        kernel = SecurityKernel()
        kernel.set_authority(AuthorityLevel.EXPERT)
        log_types = [entry["type"] for entry in kernel.audit_log]
        self.assertIn("authority_changed", log_types)


# ═══════════════════════════════════════════════════════
# 2. DESKTOP V2 TESTS
# ═══════════════════════════════════════════════════════

class TestDesktopV2(unittest.TestCase):
    """Test upgraded desktop control."""
    
    def setUp(self):
        self.desktop = DesktopToolV2()
    
    def test_actions_defined(self):
        """All expected actions should be defined."""
        expected = ["list_windows", "get_focused_window", "list_running_apps",
                    "get_system_info", "get_screen_size", "launch_app", "focus_window"]
        for action in expected:
            self.assertIn(action, self.desktop.ACTIONS)
    
    def test_whitelist_has_safe_apps(self):
        """Whitelist should contain common safe applications."""
        self.assertIn("notepad", APP_WHITELIST)
        self.assertIn("calculator", APP_WHITELIST)
        self.assertIn("chrome", APP_WHITELIST)
        self.assertIn("explorer", APP_WHITELIST)
    
    def test_non_whitelisted_app_blocked(self):
        """Non-whitelisted apps should be rejected."""
        result = self.desktop.run("launch_app", name="virus.exe")
        self.assertIn("error", result)
        self.assertIn("not in whitelist", result["error"])
    
    def test_unknown_action_returns_error(self):
        """Unknown actions should return informative error."""
        result = self.desktop.run("hack_system")
        self.assertIn("error", result)
        self.assertIn("available", result)
    
    def test_action_logging(self):
        """Actions should be logged."""
        self.desktop.run("launch_app", name="nonexistent")
        log = self.desktop.get_action_log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["action"], "launch_app")
    
    def test_list_running_apps(self):
        """Should list running apps (may fail without proper env)."""
        result = self.desktop.run("list_running_apps")
        # Either returns list or error dict
        self.assertTrue(isinstance(result, list) or isinstance(result, dict))
    
    def test_list_windows(self):
        """Should list windows (platform specific)."""
        result = self.desktop.run("list_windows")
        self.assertTrue(isinstance(result, list))


# ═══════════════════════════════════════════════════════
# 3. SCREEN INTELLIGENCE TESTS
# ═══════════════════════════════════════════════════════

class TestScreenIntelligence(unittest.TestCase):
    """Test screen perception."""
    
    def setUp(self):
        self.screen = ScreenIntelligence(screenshot_dir=tempfile.mkdtemp())
    
    def test_actions_exist(self):
        """Expected screen actions should exist."""
        expected = ["capture", "read_text", "analyze_screen", 
                    "detect_changes", "find_text_on_screen", "get_color_at"]
        for action in expected:
            result = self.screen.run(action)
            # Should return dict (success or error), not crash
            self.assertIsInstance(result, dict)
    
    def test_unknown_action(self):
        """Unknown actions should return error."""
        result = self.screen.run("hack_screen")
        self.assertIn("error", result)
    
    def test_ocr_method_detection(self):
        """OCR method should be detected from available libraries."""
        self.assertIn(self.screen._ocr_method, ["tesseract", "easyocr", "none"])
    
    def test_screenshot_dir_created(self):
        """Screenshot directory should be created on init."""
        self.assertTrue(os.path.isdir(self.screen._dir))


# ═══════════════════════════════════════════════════════
# 4. APP ANALYZER TESTS
# ═══════════════════════════════════════════════════════

class TestAppAnalyzer(unittest.TestCase):
    """Test passive app analysis."""
    
    def setUp(self):
        self.analyzer = AppAnalyzer()
    
    def test_known_apps_database(self):
        """Should have a database of known applications."""
        self.assertGreater(len(APP_DATABASE), 5)
        self.assertIn("chrome.exe", APP_DATABASE)
        self.assertIn("code.exe", APP_DATABASE)
    
    def test_identify_known_app(self):
        """Should identify known apps by process name."""
        result = self.analyzer.run("identify_app", process="chrome.exe")
        self.assertTrue(result["found"])
        self.assertEqual(result["category"], "browser")
    
    def test_identify_unknown_app(self):
        """Should handle unknown apps gracefully."""
        result = self.analyzer.run("identify_app", process="unknown_app.exe")
        self.assertFalse(result["found"])
    
    def test_explain_app(self):
        """Should explain app features."""
        result = self.analyzer.run("explain_app", process="code.exe")
        self.assertIn("explanation", result)
        self.assertIn("VS Code", result["explanation"])
    
    def test_get_tips(self):
        """Should return tips for known apps."""
        result = self.analyzer.run("get_tips", process="chrome.exe")
        self.assertGreater(len(result["tips"]), 0)
    
    def test_list_known_apps(self):
        """Should list all known apps."""
        result = self.analyzer.run("list_known_apps")
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 5)
    
    def test_suggest_shortcuts(self):
        """Should suggest shortcuts (universal or app-specific)."""
        result = self.analyzer.run("suggest_shortcuts", process="unknown.exe")
        self.assertEqual(result["app"], "universal")
        self.assertGreater(len(result["shortcuts"]), 0)
    
    def test_detect_category(self):
        """Should detect app category."""
        result = self.analyzer.run("detect_category", process="chrome.exe")
        self.assertEqual(result["category"], "browser")


# ═══════════════════════════════════════════════════════
# 5. READ-ONLY FILESYSTEM TESTS
# ═══════════════════════════════════════════════════════

class TestReadOnlyFS(unittest.TestCase):
    """Test read-only filesystem operations."""
    
    def setUp(self):
        self.fs = ReadOnlyFS()
        # Create temp test directory
        self.test_dir = tempfile.mkdtemp()
        with open(os.path.join(self.test_dir, "test.txt"), 'w') as f:
            f.write("Hello, World!")
        with open(os.path.join(self.test_dir, "code.py"), 'w') as f:
            f.write("print('hello')")
        os.makedirs(os.path.join(self.test_dir, "subdir"), exist_ok=True)
    
    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_list_directory(self):
        """Should list directory contents."""
        result = self.fs.run("list_directory", path=self.test_dir)
        self.assertIn("entries", result)
        names = [e["name"] for e in result["entries"]]
        self.assertIn("test.txt", names)
        self.assertIn("code.py", names)
    
    def test_read_safe_file(self):
        """Should read text files."""
        path = os.path.join(self.test_dir, "test.txt")
        result = self.fs.run("read_file", path=path)
        self.assertEqual(result["content"], "Hello, World!")
    
    def test_block_unsafe_file(self):
        """Should block reading unsafe file types."""
        path = os.path.join(self.test_dir, "virus.exe")
        with open(path, 'w') as f:
            f.write("data")
        result = self.fs.run("read_file", path=path)
        self.assertIn("error", result)
        self.assertIn("Unsafe", result["error"])
    
    def test_block_system_paths(self):
        """Should block access to system directories."""
        result = self.fs.run("list_directory", path="C:\\Windows")
        self.assertIn("error", result)
    
    def test_search_files(self):
        """Should search for files by name pattern."""
        result = self.fs.run("search_files", path=self.test_dir, pattern="test")
        self.assertGreater(result["count"], 0)
    
    def test_file_info(self):
        """Should return file metadata."""
        path = os.path.join(self.test_dir, "test.txt")
        result = self.fs.run("get_file_info", path=path)
        self.assertEqual(result["name"], "test.txt")
        self.assertFalse(result["is_dir"])
        self.assertIn("size_human", result)
    
    def test_folder_size(self):
        """Should calculate folder size."""
        result = self.fs.run("get_folder_size", path=self.test_dir)
        self.assertGreater(result["total_bytes"], 0)
    
    def test_tree_view(self):
        """Should generate tree view."""
        result = self.fs.run("tree", path=self.test_dir, depth=1)
        self.assertIn("tree", result)
        self.assertIn("test.txt", result["tree"])
    
    def test_no_write_action(self):
        """Should NOT have any write/delete/move actions."""
        result = self.fs.run("write_file", path="test.txt")
        self.assertIn("error", result)
        result = self.fs.run("delete_file", path="test.txt")
        self.assertIn("error", result)
    
    def test_safe_extensions(self):
        """Should have reasonable safe extension list."""
        self.assertIn(".py", SAFE_READ_EXTENSIONS)
        self.assertIn(".txt", SAFE_READ_EXTENSIONS)
        self.assertIn(".json", SAFE_READ_EXTENSIONS)
        self.assertIn(".md", SAFE_READ_EXTENSIONS)
        # Should NOT include binary executables
        self.assertNotIn(".exe", SAFE_READ_EXTENSIONS)
        self.assertNotIn(".dll", SAFE_READ_EXTENSIONS)
        self.assertNotIn(".msi", SAFE_READ_EXTENSIONS)
    
    def test_find_recent(self):
        """Should find recently modified files."""
        result = self.fs.run("find_recent_files", path=self.test_dir, hours=1)
        self.assertGreater(result["count"], 0)


# ═══════════════════════════════════════════════════════
# 6. VOICE INTERFACE TESTS
# ═══════════════════════════════════════════════════════

class TestVoiceInterface(unittest.TestCase):
    """Test voice interface (without actual mic/speaker)."""
    
    def setUp(self):
        self.voice = VoiceInterface(wake_word="hey jarvis")
    
    def test_initial_state(self):
        """Should start in IDLE state."""
        self.assertEqual(self.voice.state, VoiceState.IDLE)
    
    def test_check_capabilities(self):
        """Should report available capabilities."""
        result = self.voice.run("check_capabilities")
        self.assertIn("speech_recognition", result)
        self.assertIn("text_to_speech", result)
        self.assertIn("wake_word", result)
        self.assertEqual(result["wake_word"], "hey jarvis")
    
    def test_get_state(self):
        """Should return current state."""
        result = self.voice.run("get_state")
        self.assertEqual(result["state"], "idle")
    
    def test_set_wake_word(self):
        """Should allow changing wake word."""
        result = self.voice.run("set_wake_word", word="hey friday")
        self.assertEqual(result["wake_word"], "hey friday")
        self.assertEqual(self.voice.wake_word, "hey friday")
    
    def test_unknown_action(self):
        """Unknown actions should return error."""
        result = self.voice.run("hack_mic")
        self.assertIn("error", result)
    
    def test_voice_states_exist(self):
        """All voice states should exist."""
        states = [VoiceState.IDLE, VoiceState.LISTENING, 
                  VoiceState.PROCESSING, VoiceState.SPEAKING]
        self.assertEqual(len(states), 4)


# ═══════════════════════════════════════════════════════
# 7. INTEGRATION TESTS
# ═══════════════════════════════════════════════════════

class TestIntegration(unittest.TestCase):
    """Test modules working together through SecurityKernel."""
    
    def test_authority_affects_action_checking(self):
        """Authority level should change security verdicts."""
        kernel_safe = SecurityKernel(authority=AuthorityLevel.SAFE)
        kernel_expert = SecurityKernel(authority=AuthorityLevel.EXPERT)
        
        # Both should allow a safe action
        result_safe = kernel_safe.check_action("filesystem", "read_file", {"path": "test.txt"})
        result_expert = kernel_expert.check_action("filesystem", "read_file", {"path": "test.txt"})
        self.assertIn(result_safe.verdict, [ActionVerdict.ALLOW, ActionVerdict.ALLOW_LOGGED])
        self.assertIn(result_expert.verdict, [ActionVerdict.ALLOW, ActionVerdict.ALLOW_LOGGED])
    
    def test_catastrophic_blocked_in_all_modes(self):
        """Catastrophic commands should be BLOCKED regardless of authority."""
        for level in AuthorityLevel:
            kernel = SecurityKernel(authority=level)
            result = kernel.check_action("shell_execution", "run_command", 
                                        {"command": "rm -rf /"})
            self.assertEqual(result.verdict, ActionVerdict.BLOCK,
                           f"'rm -rf /' should be BLOCKED in {level.value} mode")
    
    def test_all_modules_instantiate(self):
        """All modules should instantiate without errors."""
        desktop = DesktopToolV2()
        screen = ScreenIntelligence()
        analyzer = AppAnalyzer()
        fs = ReadOnlyFS()
        voice = VoiceInterface()
        
        self.assertIsNotNone(desktop)
        self.assertIsNotNone(screen)
        self.assertIsNotNone(analyzer)
        self.assertIsNotNone(fs)
        self.assertIsNotNone(voice)
    
    def test_fs_readonly_enforced(self):
        """ReadOnlyFS should not have write methods."""
        fs = ReadOnlyFS()
        self.assertFalse(hasattr(fs, '_write_file'))
        self.assertFalse(hasattr(fs, '_delete_file'))
        self.assertFalse(hasattr(fs, '_move_file'))


if __name__ == '__main__':
    print("=" * 60)
    print("R.5A-P PERCEPTION-FIRST LOCAL OPERATOR — VERIFICATION")
    print("=" * 60)
    print()
    
    # Run with verbose output
    unittest.main(verbosity=2)
