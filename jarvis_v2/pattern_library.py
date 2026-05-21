"""
pattern_library.py — Hand-Curated Python Error Archetypes.

NOT ML. NOT embeddings. Manual patterns that match ERROR CLASSES,
not exact tracebacks.

Why manual: Manual patterns beat premature ML. They're transparent,
debuggable, and you can add new ones in 30 seconds.

Each pattern has:
  - error_class: the semantic category (not the exact exception)
  - signatures: strings that identify this class in tracebacks/output
  - pre_run_signals: code patterns that predict this error BEFORE running
  - fix_hint: what to tell the developer
  - severity: how much time this typically wastes (seconds)
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict
import re


@dataclass
class ErrorPattern:
    """One class of predictable Python error."""
    error_class: str           # e.g. "missing_import"
    signatures: List[str]      # Strings found in traceback
    pre_run_signals: List[str] # Code patterns that predict this BEFORE run
    fix_hint: str              # Human-readable fix
    severity_seconds: int      # Typical time wasted debugging this
    category: str = "general"  # "import", "path", "type", "syntax", "env", "api"
    
    def matches_traceback(self, traceback_text: str) -> bool:
        """Does this traceback match our error class?"""
        text = traceback_text.lower()
        return any(sig.lower() in text for sig in self.signatures)
    
    def matches_code(self, code_text: str) -> Optional[Dict]:
        """Does this code contain pre-run signals that predict this error?
        
        Returns match details or None.
        """
        for signal in self.pre_run_signals:
            # Signals can be regex patterns (prefixed with 'r:') or plain strings
            if signal.startswith("r:"):
                pattern = signal[2:]
                match = re.search(pattern, code_text)
                if match:
                    return {
                        "signal": signal,
                        "match": match.group(),
                        "line_hint": code_text[:match.start()].count('\n') + 1
                    }
            else:
                if signal in code_text:
                    idx = code_text.index(signal)
                    return {
                        "signal": signal,
                        "match": signal,
                        "line_hint": code_text[:idx].count('\n') + 1
                    }
        return None


# ═══════════════════════════════════════════════════════
# THE PATTERN LIBRARY — Start with 15. Add as you hit them.
# ═══════════════════════════════════════════════════════

PATTERNS: List[ErrorPattern] = [
    
    # ── IMPORT ERRORS ──────────────────────────────────
    
    ErrorPattern(
        error_class="missing_import",
        signatures=[
            "ModuleNotFoundError", "ImportError", "No module named"
        ],
        pre_run_signals=[
            # Using a name that was never imported
            "r:^(?!.*import\\s+os).*\\bos\\.path\\b",
            "r:^(?!.*import\\s+json).*\\bjson\\.(loads|dumps)\\b",
            "r:^(?!.*import\\s+sys).*\\bsys\\.(path|argv|exit)\\b",
        ],
        fix_hint="Add the missing import at the top of the file.",
        severity_seconds=30,
        category="import"
    ),
    
    ErrorPattern(
        error_class="circular_import",
        signatures=[
            "ImportError: cannot import name",
            "partially initialized module",
            "circular import"
        ],
        pre_run_signals=[],  # Hard to detect statically
        fix_hint="Break circular dependency: move import inside function or restructure modules.",
        severity_seconds=600,
        category="import"
    ),
    
    # ── NAME / REFERENCE ERRORS ────────────────────────
    
    ErrorPattern(
        error_class="undefined_variable",
        signatures=[
            "NameError: name", "is not defined"
        ],
        pre_run_signals=[
            # Variable used but likely undefined after refactor
            "r:\\b(result|data|response|output)\\b.*=.*\n.*\\b\\1\\b",
        ],
        fix_hint="Variable is not defined. Check for typos or missing assignment.",
        severity_seconds=60,
        category="name"
    ),
    
    ErrorPattern(
        error_class="attribute_error",
        signatures=[
            "AttributeError:", "has no attribute"
        ],
        pre_run_signals=[],
        fix_hint="Object doesn't have this attribute. Check the type or API docs.",
        severity_seconds=120,
        category="type"
    ),
    
    # ── TYPE ERRORS ────────────────────────────────────
    
    ErrorPattern(
        error_class="type_mismatch",
        signatures=[
            "TypeError:", "unsupported operand type",
            "expected str instance", "not subscriptable",
            "argument must be"
        ],
        pre_run_signals=[
            # Concatenating str + int
            "r:\".*\"\\s*\\+\\s*\\w+",
            "r:f?['\"].*['\"]\\s*\\+\\s*\\d+",
        ],
        fix_hint="Type mismatch. Check if you're mixing str/int/list inappropriately.",
        severity_seconds=120,
        category="type"
    ),
    
    ErrorPattern(
        error_class="none_reference",
        signatures=[
            "'NoneType' object", "NoneType", "is None"
        ],
        pre_run_signals=[
            # Chaining without None check
            "r:\\.\\w+\\(\\)\\.\\w+",
        ],
        fix_hint="Something is None when it shouldn't be. Check return values.",
        severity_seconds=180,
        category="type"
    ),
    
    # ── PATH / FILE ERRORS ─────────────────────────────
    
    ErrorPattern(
        error_class="file_not_found",
        signatures=[
            "FileNotFoundError", "No such file or directory",
            "FileExistsError"
        ],
        pre_run_signals=[
            # Hardcoded paths
            "r:open\\(['\"](?!/)[^'\"]+['\"]",
            "r:['\"]C:\\\\",
            "r:['\"]\\./(?!test)",
        ],
        fix_hint="File path doesn't exist. Check relative vs absolute paths.",
        severity_seconds=120,
        category="path"
    ),
    
    ErrorPattern(
        error_class="permission_denied",
        signatures=[
            "PermissionError", "Permission denied", "Access is denied"
        ],
        pre_run_signals=[],
        fix_hint="Permission denied. Check file/folder permissions or run with admin rights.",
        severity_seconds=180,
        category="path"
    ),
    
    # ── SYNTAX ERRORS ──────────────────────────────────
    
    ErrorPattern(
        error_class="syntax_error",
        signatures=[
            "SyntaxError:", "invalid syntax", "unexpected indent",
            "IndentationError"
        ],
        pre_run_signals=[
            # Mismatched brackets (simple check)
            "r:\\([^)]*$",
            # Missing colon after if/for/def/class
            "r:^\\s*(if|for|while|def|class)\\s+[^:]+$",
        ],
        fix_hint="Syntax error. Check for missing colons, brackets, or indentation.",
        severity_seconds=30,
        category="syntax"
    ),
    
    # ── ENVIRONMENT ERRORS ─────────────────────────────
    
    ErrorPattern(
        error_class="venv_mismatch",
        signatures=[
            "ModuleNotFoundError", "No module named",
            "pip install"
        ],
        pre_run_signals=[
            # Import of commonly-missing packages
            "r:import\\s+(pandas|numpy|requests|flask|django|pytest|torch)",
        ],
        fix_hint="Package not installed. Check your virtualenv is activated and run pip install.",
        severity_seconds=120,
        category="env"
    ),
    
    ErrorPattern(
        error_class="port_in_use",
        signatures=[
            "Address already in use", "port is already allocated",
            "OSError: [Errno 98]", "OSError: [Errno 48]",
            "[WinError 10048]"
        ],
        pre_run_signals=[
            "r:\\bport\\s*=\\s*\\d+",
            "r:bind\\(",
            "r:listen\\(",
        ],
        fix_hint="Port already in use. Kill the old process or use a different port.",
        severity_seconds=120,
        category="env"
    ),
    
    # ── API / DATA ERRORS ──────────────────────────────
    
    ErrorPattern(
        error_class="json_decode_error",
        signatures=[
            "JSONDecodeError", "json.decoder.JSONDecodeError",
            "Expecting value:", "Invalid control character"
        ],
        pre_run_signals=[
            # Reading file and immediately json.loads
            "r:json\\.loads?\\(.*read\\(",
            "r:json\\.loads?\\(.*open\\(",
        ],
        fix_hint="Invalid JSON. Check the file/response is actually valid JSON.",
        severity_seconds=120,
        category="api"
    ),
    
    ErrorPattern(
        error_class="key_error",
        signatures=[
            "KeyError:", "KeyError"
        ],
        pre_run_signals=[
            # Dict access without .get()
            "r:\\w+\\[['\"]\\w+['\"]\\]",
        ],
        fix_hint="Key doesn't exist in dict. Use .get() for safe access.",
        severity_seconds=60,
        category="api"
    ),
    
    ErrorPattern(
        error_class="encoding_error",
        signatures=[
            "UnicodeDecodeError", "UnicodeEncodeError",
            "codec can't decode", "codec can't encode"
        ],
        pre_run_signals=[
            # open() without encoding=
            "r:open\\([^)]*\\)(?!.*encoding)",
            # read_csv without encoding
            "r:read_csv\\([^)]*\\)(?!.*encoding)",
        ],
        fix_hint="Encoding issue. Add encoding='utf-8' to open() or read_csv().",
        severity_seconds=180,
        category="api"
    ),
    
    ErrorPattern(
        error_class="index_error",
        signatures=[
            "IndexError:", "list index out of range",
            "tuple index out of range"
        ],
        pre_run_signals=[
            # Accessing [0] without length check
            "r:\\w+\\[0\\]",
            "r:\\w+\\[-1\\]",
        ],
        fix_hint="Index out of range. Check list length before accessing elements.",
        severity_seconds=60,
        category="type"
    ),
]


def match_traceback(traceback_text: str) -> List[ErrorPattern]:
    """Find all patterns matching a traceback."""
    return [p for p in PATTERNS if p.matches_traceback(traceback_text)]


def scan_code_for_risks(code_text: str) -> List[Dict]:
    """
    Scan code for pre-run risk signals.
    
    Returns list of {pattern, match_details} for each risk found.
    """
    risks = []
    for pattern in PATTERNS:
        match = pattern.matches_code(code_text)
        if match:
            risks.append({
                "pattern": pattern,
                "match": match,
                "error_class": pattern.error_class,
                "fix_hint": pattern.fix_hint,
                "severity": pattern.severity_seconds,
            })
    return risks


def get_pattern_by_class(error_class: str) -> Optional[ErrorPattern]:
    """Look up a pattern by its class name."""
    for p in PATTERNS:
        if p.error_class == error_class:
            return p
    return None


def list_categories() -> Dict[str, int]:
    """List pattern categories and counts."""
    cats = {}
    for p in PATTERNS:
        cats[p.category] = cats.get(p.category, 0) + 1
    return cats
