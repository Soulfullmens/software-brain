"""
traceback_parser.py — Extracts structured errors from raw Python terminal output.

Takes raw stdout/stderr text → returns structured error with 3-level classification:
  Level 1: Exact error    — "KeyError: 'username'"
  Level 2: Error type     — "KeyError"  
  Level 3: Pattern cause  — "unsafe_dict_access" (THIS fires pre-run warnings)

Zero manual input. Zero behavior change. Just reads what the terminal already shows.
"""
import re
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ParsedError:
    """Structured error extracted from raw terminal output."""
    # Level 1: Exact
    exact_error: str        # "KeyError: 'username'"
    
    # Level 2: Type
    error_type: str         # "KeyError"
    
    # Level 3: Cause (for prediction)
    pattern_cause: str      # "unsafe_dict_access"
    
    # Context
    file_path: str          # "/path/to/app.py"
    line_number: int        # 14
    code_context: str       # "name = data['username']"
    full_traceback: str     # The complete traceback text
    
    # Metadata
    is_syntax_error: bool = False
    exit_code: int = 1


# ═══════════════════════════════════════════════════════
# ERROR TYPE → PATTERN CAUSE MAPPING
# ═══════════════════════════════════════════════════════

# Maps (error_type, message_pattern) → pattern_cause
# This is the Level 2 → Level 3 bridge
CAUSE_MAP = [
    # KeyError
    ("KeyError", None, "unsafe_dict_access"),
    
    # ImportError / ModuleNotFoundError  
    ("ModuleNotFoundError", None, "missing_import"),
    ("ImportError", r"cannot import name", "circular_import"),
    ("ImportError", None, "missing_import"),
    
    # TypeError
    ("TypeError", r"unsupported operand", "type_mismatch"),
    ("TypeError", r"not subscriptable", "wrong_type_access"),
    ("TypeError", r"argument", "wrong_argument_type"),
    ("TypeError", r"NoneType", "none_reference"),
    ("TypeError", None, "type_mismatch"),
    
    # AttributeError
    ("AttributeError", r"NoneType", "none_reference"),
    ("AttributeError", None, "wrong_attribute"),
    
    # NameError
    ("NameError", None, "undefined_variable"),
    
    # FileNotFoundError
    ("FileNotFoundError", None, "bad_file_path"),
    
    # ValueError
    ("ValueError", r"invalid literal", "bad_type_conversion"),
    ("ValueError", None, "invalid_value"),
    
    # IndexError
    ("IndexError", None, "index_out_of_range"),
    
    # SyntaxError / IndentationError
    ("SyntaxError", None, "syntax_error"),
    ("IndentationError", None, "indentation_error"),
    
    # OSError variants
    ("PermissionError", None, "permission_denied"),
    ("OSError", r"[Errno 98]|[Errno 48]|10048", "port_in_use"),
    ("OSError", None, "os_error"),
    
    # JSON
    ("JSONDecodeError", None, "invalid_json"),
    ("json.decoder.JSONDecodeError", None, "invalid_json"),
    
    # Encoding
    ("UnicodeDecodeError", None, "encoding_mismatch"),
    ("UnicodeEncodeError", None, "encoding_mismatch"),
    
    # Assertion
    ("AssertionError", None, "assertion_failed"),
    ("AssertionError", None, "assertion_failed"),
    
    # Runtime
    ("RecursionError", None, "infinite_recursion"),
    ("StopIteration", None, "iterator_exhausted"),
    ("RuntimeError", None, "runtime_error"),
    
    # Connection
    ("ConnectionError", None, "connection_failed"),
    ("ConnectionRefusedError", None, "connection_failed"),
    ("TimeoutError", None, "timeout"),
]


def _resolve_cause(error_type: str, error_message: str) -> str:
    """Map error type + message to pattern cause (Level 3)."""
    for etype, pattern, cause in CAUSE_MAP:
        if etype == error_type or error_type.endswith(etype):
            if pattern is None:
                return cause
            if re.search(pattern, error_message, re.IGNORECASE):
                return cause
    return "unknown_error"


# ═══════════════════════════════════════════════════════
# TRACEBACK PARSER
# ═══════════════════════════════════════════════════════

# Regex for standard Python traceback
_TB_START = re.compile(r'Traceback \(most recent call last\)')
_TB_FILE = re.compile(r'^\s*File "([^"]+)", line (\d+)', re.MULTILINE)
_TB_CODE = re.compile(r'^\s{4}(\S.+)$', re.MULTILINE)
_TB_ERROR = re.compile(
    r'^([A-Za-z_][\w.]*(?:Error|Exception|Warning|Interrupt))\s*:\s*(.*)$',
    re.MULTILINE
)
# SyntaxError has a different format
_SYNTAX_ERROR = re.compile(
    r'^(\s*File "([^"]+)", line (\d+).*\n(?:.*\n)*?)'
    r'(SyntaxError|IndentationError)\s*:\s*(.*)$',
    re.MULTILINE
)


def parse_terminal_output(raw_output: str) -> List[ParsedError]:
    """
    Parse raw terminal output for Python errors.
    
    Handles:
      - Standard tracebacks (Traceback most recent call last)
      - SyntaxError (different format)
      - Multiple errors in same output
      - pytest output
      - Nested tracebacks
    
    Returns list of ParsedError (usually 1, but can be multiple).
    """
    errors = []
    
    # Try standard traceback first
    tb_errors = _parse_standard_traceback(raw_output)
    errors.extend(tb_errors)
    
    # Try syntax errors (different format)
    if not errors:
        syntax_errors = _parse_syntax_errors(raw_output)
        errors.extend(syntax_errors)
    
    # Try simple error line (no traceback, just ErrorType: message)
    if not errors:
        simple_errors = _parse_simple_errors(raw_output)
        errors.extend(simple_errors)
    
    return errors


def _parse_standard_traceback(raw: str) -> List[ParsedError]:
    """Parse standard Python tracebacks."""
    errors = []
    
    # Split on traceback starts
    parts = _TB_START.split(raw)
    
    for i, part in enumerate(parts):
        if i == 0:
            continue  # Skip text before first traceback
        
        # Find the error line (last ErrorType: message)
        error_match = None
        for m in _TB_ERROR.finditer(part):
            error_match = m
        
        if not error_match:
            continue
        
        error_type = error_match.group(1)
        error_message = error_match.group(2).strip()
        exact_error = f"{error_type}: {error_message}" if error_message else error_type
        
        # Find file references (take the LAST user file, not stdlib)
        file_path = ""
        line_number = 0
        for fm in _TB_FILE.finditer(part):
            fpath = fm.group(1)
            # Skip stdlib / site-packages
            if not any(skip in fpath for skip in [
                'site-packages', 'lib/python', 'Lib\\', 'lib\\',
                '<frozen', '<string>', 'importlib'
            ]):
                file_path = fpath
                line_number = int(fm.group(2))
        
        # Find code context (line after the File reference)
        code_context = ""
        code_matches = _TB_CODE.findall(part)
        if code_matches:
            code_context = code_matches[-1].strip()
        
        # Resolve pattern cause
        pattern_cause = _resolve_cause(error_type, error_message)
        
        errors.append(ParsedError(
            exact_error=exact_error,
            error_type=error_type,
            pattern_cause=pattern_cause,
            file_path=file_path,
            line_number=line_number,
            code_context=code_context,
            full_traceback="Traceback (most recent call last)" + part[:2000],
        ))
    
    return errors


def _parse_syntax_errors(raw: str) -> List[ParsedError]:
    """Parse SyntaxError / IndentationError (different format)."""
    errors = []
    
    for m in _SYNTAX_ERROR.finditer(raw):
        error_type = m.group(4)
        error_message = m.group(5).strip()
        file_path = m.group(2)
        line_number = int(m.group(3))
        
        errors.append(ParsedError(
            exact_error=f"{error_type}: {error_message}",
            error_type=error_type,
            pattern_cause="syntax_error" if error_type == "SyntaxError" else "indentation_error",
            file_path=file_path,
            line_number=line_number,
            code_context="",
            full_traceback=m.group(0)[:2000],
            is_syntax_error=True,
        ))
    
    return errors


def _parse_simple_errors(raw: str) -> List[ParsedError]:
    """Parse simple error messages without full traceback."""
    errors = []
    
    for m in _TB_ERROR.finditer(raw):
        error_type = m.group(1)
        error_message = m.group(2).strip()
        
        # Try to find file context nearby
        file_path = ""
        line_number = 0
        context_start = max(0, m.start() - 500)
        context = raw[context_start:m.start()]
        file_match = _TB_FILE.search(context)
        if file_match:
            file_path = file_match.group(1)
            line_number = int(file_match.group(2))
        
        errors.append(ParsedError(
            exact_error=f"{error_type}: {error_message}" if error_message else error_type,
            error_type=error_type,
            pattern_cause=_resolve_cause(error_type, error_message),
            file_path=file_path,
            line_number=line_number,
            code_context="",
            full_traceback=raw[max(0, m.start() - 200):m.end()][:2000],
        ))
    
    return errors


def has_python_error(raw_output: str) -> bool:
    """Quick check: does this output contain a Python error?"""
    return bool(_TB_ERROR.search(raw_output)) or bool(_TB_START.search(raw_output))


def extract_exit_code(raw_output: str) -> Optional[int]:
    """Try to extract exit code from terminal output."""
    # pytest: "1 failed" or "FAILED"
    if re.search(r'\d+ failed', raw_output) or 'FAILED' in raw_output:
        return 1
    # General: "exit code" or "return code"
    m = re.search(r'(?:exit|return)\s*(?:code|status)\s*[=:]\s*(\d+)', raw_output, re.I)
    if m:
        return int(m.group(1))
    return None
