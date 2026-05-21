"""
test_v2_1.py — Tests for V2.1 upgrades: traceback parser, recency, server protocol.

Tests:
  1. Traceback Parser — standard, syntax, simple, multi-error, pytest
  2. 3-Level Classification — exact → type → cause
  3. Recency Weighting — recent vs old errors
  4. Server Protocol — JSON-RPC message handling
  5. Integration — parse + record + check_risks loop
"""
import os, sys, time, unittest, tempfile, shutil, json, math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_v2.traceback_parser import (
    parse_terminal_output, has_python_error, ParsedError,
    extract_exit_code, _resolve_cause
)
from jarvis_v2.error_memory import ErrorMemory, ErrorEntry
from jarvis_v2.jarvis_dev import JarvisDev


# ═══════════════════════════════════════════════════════
# 1. TRACEBACK PARSER
# ═══════════════════════════════════════════════════════

class TestTracebackParser(unittest.TestCase):
    
    STANDARD_TB = '''Traceback (most recent call last):
  File "/home/user/app.py", line 14, in main
    name = data["username"]
  File "/home/user/utils.py", line 7, in get_user
    return db.find(key)
KeyError: 'username'
'''
    
    IMPORT_TB = '''Traceback (most recent call last):
  File "main.py", line 1, in <module>
    import flask
ModuleNotFoundError: No module named 'flask'
'''
    
    TYPE_TB = '''Traceback (most recent call last):
  File "calc.py", line 5, in <module>
    result = count + "items"
TypeError: unsupported operand type(s) for +: 'int' and 'str'
'''
    
    SYNTAX_TB = '''  File "broken.py", line 3
    if x = 5:
         ^
SyntaxError: invalid syntax
'''
    
    NONE_TB = '''Traceback (most recent call last):
  File "app.py", line 10, in process
    result = response.json()
AttributeError: 'NoneType' object has no attribute 'json'
'''
    
    FILE_TB = '''Traceback (most recent call last):
  File "loader.py", line 5, in load_config
    with open("config.json") as f:
FileNotFoundError: [Errno 2] No such file or directory: 'config.json'
'''
    
    ENCODING_TB = '''Traceback (most recent call last):
  File "reader.py", line 3, in <module>
    data = open("file.csv").read()
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0
'''

    def test_parse_standard_traceback(self):
        errors = parse_terminal_output(self.STANDARD_TB)
        self.assertEqual(len(errors), 1)
        err = errors[0]
        self.assertEqual(err.error_type, "KeyError")
        self.assertEqual(err.exact_error, "KeyError: 'username'")
        self.assertEqual(err.pattern_cause, "unsafe_dict_access")
        self.assertIn("utils.py", err.file_path)
        self.assertEqual(err.line_number, 7)
    
    def test_parse_import_error(self):
        errors = parse_terminal_output(self.IMPORT_TB)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].error_type, "ModuleNotFoundError")
        self.assertEqual(errors[0].pattern_cause, "missing_import")
    
    def test_parse_type_error(self):
        errors = parse_terminal_output(self.TYPE_TB)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].pattern_cause, "type_mismatch")
    
    def test_parse_syntax_error(self):
        errors = parse_terminal_output(self.SYNTAX_TB)
        self.assertEqual(len(errors), 1)
        err = errors[0]
        self.assertEqual(err.error_type, "SyntaxError")
        self.assertEqual(err.pattern_cause, "syntax_error")
        self.assertTrue(err.is_syntax_error)
        self.assertIn("broken.py", err.file_path)
        self.assertEqual(err.line_number, 3)
    
    def test_parse_none_reference(self):
        errors = parse_terminal_output(self.NONE_TB)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].pattern_cause, "none_reference")
    
    def test_parse_file_not_found(self):
        errors = parse_terminal_output(self.FILE_TB)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].pattern_cause, "bad_file_path")
    
    def test_parse_encoding_error(self):
        errors = parse_terminal_output(self.ENCODING_TB)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].pattern_cause, "encoding_mismatch")
    
    def test_has_python_error_true(self):
        self.assertTrue(has_python_error(self.STANDARD_TB))
        self.assertTrue(has_python_error(self.IMPORT_TB))
    
    def test_has_python_error_false(self):
        self.assertFalse(has_python_error("All tests passed. 42 collected."))
        self.assertFalse(has_python_error("Hello, world!"))
    
    def test_clean_output_no_errors(self):
        errors = parse_terminal_output("Everything is fine. No errors here.")
        self.assertEqual(len(errors), 0)
    
    def test_3_level_classification(self):
        """Every parsed error has all 3 levels."""
        for tb in [self.STANDARD_TB, self.IMPORT_TB, self.TYPE_TB, self.NONE_TB]:
            errors = parse_terminal_output(tb)
            for err in errors:
                self.assertTrue(err.exact_error, "Missing exact_error")
                self.assertTrue(err.error_type, "Missing error_type")
                self.assertTrue(err.pattern_cause, "Missing pattern_cause")
    
    def test_skips_stdlib_files(self):
        tb = '''Traceback (most recent call last):
  File "/usr/lib/python3.10/site-packages/flask/app.py", line 100, in run
    something()
  File "/home/user/myapp.py", line 42, in handler
    data["key"]
KeyError: 'key'
'''
        errors = parse_terminal_output(tb)
        self.assertEqual(len(errors), 1)
        self.assertIn("myapp.py", errors[0].file_path)
        self.assertEqual(errors[0].line_number, 42)
    
    def test_extract_exit_code_pytest(self):
        output = "FAILED tests/test_main.py::test_foo - AssertionError\n1 failed, 5 passed"
        self.assertEqual(extract_exit_code(output), 1)
    
    def test_extract_exit_code_clean(self):
        output = "5 passed in 0.5s"
        self.assertIsNone(extract_exit_code(output))
    
    def test_pytest_output(self):
        pytest_output = '''======= FAILURES =======
_____ test_login _____

    def test_login():
>       result = login("admin", "wrong")
E       AssertionError: assert False

test_auth.py:15: AssertionError
======= 1 failed =======

Traceback (most recent call last):
  File "test_auth.py", line 15, in test_login
    assert login("admin", "wrong")
AssertionError: assert False
'''
        errors = parse_terminal_output(pytest_output)
        # Should find the assertion error
        self.assertGreater(len(errors), 0)


# ═══════════════════════════════════════════════════════
# 2. CAUSE RESOLUTION
# ═══════════════════════════════════════════════════════

class TestCauseResolution(unittest.TestCase):
    
    def test_key_error(self):
        self.assertEqual(_resolve_cause("KeyError", "'name'"), "unsafe_dict_access")
    
    def test_import_error(self):
        self.assertEqual(
            _resolve_cause("ModuleNotFoundError", "No module named 'x'"),
            "missing_import"
        )
    
    def test_circular_import(self):
        self.assertEqual(
            _resolve_cause("ImportError", "cannot import name 'X'"),
            "circular_import"
        )
    
    def test_none_type_attr(self):
        self.assertEqual(
            _resolve_cause("AttributeError", "'NoneType' object has no attribute"),
            "none_reference"
        )
    
    def test_unsupported_operand(self):
        self.assertEqual(
            _resolve_cause("TypeError", "unsupported operand type(s)"),
            "type_mismatch"
        )
    
    def test_file_not_found(self):
        self.assertEqual(
            _resolve_cause("FileNotFoundError", "[Errno 2]"),
            "bad_file_path"
        )
    
    def test_json_decode(self):
        self.assertEqual(
            _resolve_cause("JSONDecodeError", "Expecting value"),
            "invalid_json"
        )
    
    def test_unknown_error(self):
        self.assertEqual(
            _resolve_cause("SomeWeirdError", "never seen this"),
            "unknown_error"
        )


# ═══════════════════════════════════════════════════════
# 3. RECENCY WEIGHTING
# ═══════════════════════════════════════════════════════

class TestRecencyWeighting(unittest.TestCase):
    
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.mem = ErrorMemory(memory_file=os.path.join(self.tmp, "errors.jsonl"))
    
    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
    
    def test_recency_weight_recent(self):
        # Just happened
        entries = [ErrorEntry(
            error_class="x", traceback="", file_path="", code_snippet="",
            fix_applied="", command="", timestamp=time.time()
        )]
        weight = ErrorMemory._recency_weight(entries)
        self.assertGreater(weight, 0.9)
    
    def test_recency_weight_old(self):
        # 30 days ago
        entries = [ErrorEntry(
            error_class="x", traceback="", file_path="", code_snippet="",
            fix_applied="", command="", timestamp=time.time() - 30 * 86400
        )]
        weight = ErrorMemory._recency_weight(entries)
        self.assertLess(weight, 0.01)
    
    def test_recency_weight_yesterday(self):
        # 24 hours ago
        entries = [ErrorEntry(
            error_class="x", traceback="", file_path="", code_snippet="",
            fix_applied="", command="", timestamp=time.time() - 86400
        )]
        weight = ErrorMemory._recency_weight(entries)
        self.assertGreater(weight, 0.5)
        self.assertLess(weight, 0.9)
    
    def test_recency_weight_empty(self):
        self.assertEqual(ErrorMemory._recency_weight([]), 0.0)
    
    def test_time_ago_minutes(self):
        self.assertIn("min", ErrorMemory._time_ago(time.time() - 300))
    
    def test_time_ago_hours(self):
        self.assertIn("h", ErrorMemory._time_ago(time.time() - 7200))
    
    def test_time_ago_days(self):
        self.assertIn("d", ErrorMemory._time_ago(time.time() - 172800))
    
    def test_time_ago_weeks(self):
        self.assertIn("w", ErrorMemory._time_ago(time.time() - 1209600))
    
    def test_history_first_warnings(self):
        """History-based warnings should include time ago and use humility for cross-file."""
        self.mem.record("KeyError: 'name'", file_path="app.py")
        
        code = 'name = data["name"]\n'
        risks = self.mem.check_risks(code, file_path="app.py")
        
        key_risks = [r for r in risks if r["error_class"] == "key_error"]
        if key_risks:
            # Should say "This exact failure happened before"
            self.assertIn("happened before", key_risks[0]["message"])
            self.assertTrue(key_risks[0].get("is_history", False))
    
    def test_cross_file_humility(self):
        """Cross-file warnings should use 'This may fail' language."""
        self.mem.record("KeyError: 'x'", file_path="other.py")
        
        code = 'name = data["x"]\n'
        risks = self.mem.check_risks(code, file_path="different.py")
        
        key_risks = [r for r in risks if r["error_class"] == "key_error"]
        if key_risks:
            self.assertIn("may fail", key_risks[0]["message"])


# ═══════════════════════════════════════════════════════
# 4. SERVER PROTOCOL
# ═══════════════════════════════════════════════════════

class TestServerProtocol(unittest.TestCase):
    """Test the JSON-RPC server message handling (without spawning process)."""
    
    def setUp(self):
        from jarvis_v2.jarvis_server import JarvisServer
        self.tmp = tempfile.mkdtemp()
        self.server = JarvisServer.__new__(JarvisServer)
        self.server.pilot = JarvisDev(
            memory_file=os.path.join(self.tmp, "errors.jsonl"),
            experiment_file=os.path.join(self.tmp, "experiment.jsonl"),
        )
        self.server._methods = {
            "check_risks": self.server._check_risks,
            "record_error": self.server._record_error,
            "record_success": self.server._record_success,
            "record_edit": self.server._record_edit,
            "parse_output": self.server._parse_output,
            "get_status": self.server._get_status,
            "dismiss": self.server._dismiss,
            "accept": self.server._accept,
            "ping": self.server._ping,
        }
    
    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
    
    def test_ping(self):
        result = self.server._ping({})
        self.assertTrue(result["pong"])
        self.assertEqual(result["version"], "2.1")
    
    def test_check_risks(self):
        result = self.server._check_risks({
            "file_path": "test.py",
            "code_text": 'data = open("file.csv").read()\n',
        })
        self.assertIn("warnings", result)
    
    def test_record_error(self):
        result = self.server._record_error({
            "traceback_text": "ModuleNotFoundError: No module named 'flask'",
            "file_path": "app.py",
        })
        self.assertEqual(result["error_class"], "missing_import")
    
    def test_parse_output_with_error(self):
        result = self.server._parse_output({
            "raw_output": TestTracebackParser.STANDARD_TB,
        })
        self.assertTrue(result["has_error"])
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["pattern_cause"], "unsafe_dict_access")
    
    def test_parse_output_clean(self):
        result = self.server._parse_output({
            "raw_output": "All tests passed.",
        })
        self.assertFalse(result["has_error"])
    
    def test_get_status(self):
        result = self.server._get_status({})
        self.assertIn("session", result)
        self.assertIn("memory", result)
    
    def test_dismiss_accept(self):
        self.server._dismiss({})
        self.server._accept({})
        # Should not crash
        stats = self.server.pilot.policy.get_stats()
        self.assertEqual(stats["dismissed"], 1)
        self.assertEqual(stats["accepted"], 1)


# ═══════════════════════════════════════════════════════
# 5. INTEGRATION: THE FULL LOOP
# ═══════════════════════════════════════════════════════

class TestFullLoop(unittest.TestCase):
    """
    THE MINIMAL LOOP:
    Save → Run → Fail → Learn → Warn next run
    """
    
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pilot = JarvisDev(
            memory_file=os.path.join(self.tmp, "errors.jsonl"),
            experiment_file=os.path.join(self.tmp, "experiment.jsonl"),
        )
    
    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
    
    def test_full_loop_save_run_fail_learn_warn(self):
        """
        Simulate: user saves app.py with dict["key"], runs it, gets KeyError,
        Jarvis records it, next time user saves the same file → warning appears.
        """
        code = 'name = data["username"]\nage = data["age"]\n'
        file_path = os.path.join(self.tmp, "app.py")
        
        # Step 1: Save (first time) → scan → may or may not warn
        warnings_first = self.pilot.check_before_run("python app.py", file_path, code)
        # First time: pattern match only, no history
        
        # Step 2: Run → Fail 
        self.pilot.record_error(
            "KeyError: 'username'",
            file_path=file_path,
            command="python app.py",
        )
        
        # Step 3: Edit (fix attempt)
        self.pilot.record_edit(file_path)
        
        # Step 4: Save again → scan → NOW should warn strongly
        warnings_second = self.pilot.check_before_run("python app.py", file_path, code)
        
        # THE KEY ASSERTION: second time has boosted warnings
        key_warnings = [w for w in warnings_second if w.get("error_class") == "key_error"]
        self.assertGreater(len(key_warnings), 0, "Should warn about key_error after it happened before")
        
        # And the warning should mention history
        if key_warnings:
            self.assertGreater(
                key_warnings[0]["confidence"], 0.8,
                "Confidence should be high after same error in same file"
            )
    
    def test_auto_capture_from_terminal(self):
        """Simulate: terminal output with traceback → auto-recorded."""
        from jarvis_v2.traceback_parser import parse_terminal_output
        
        raw = '''Traceback (most recent call last):
  File "app.py", line 14, in main
    name = data["username"]
KeyError: 'username'
'''
        # Parse terminal output
        parsed = parse_terminal_output(raw)
        self.assertEqual(len(parsed), 1)
        
        # Auto-record
        for err in parsed:
            self.pilot.record_error(
                err.full_traceback,
                file_path=err.file_path,
                code_snippet=err.code_context,
            )
        
        # Memory should have it
        self.assertEqual(self.pilot.memory.count(), 1)
        
        # Future check should warn
        code = 'name = data["username"]\n'
        warnings = self.pilot.check_before_run("python app.py", "app.py", code)
        key_w = [w for w in warnings if w.get("error_class") == "key_error"]
        self.assertGreater(len(key_w), 0)
    
    def test_stuck_loop_still_works(self):
        """3x same error class → stuck detection."""
        for _ in range(3):
            result = self.pilot.record_error("ModuleNotFoundError: No module named 'x'")
        self.assertTrue(result["stuck"])


if __name__ == '__main__':
    print("═" * 50)
    print("  JARVIS V2.1 — INTEGRATION VERIFICATION")
    print("═" * 50)
    unittest.main(verbosity=2)
