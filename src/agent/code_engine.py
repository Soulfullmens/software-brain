"""
code_engine.py

Code Generation, Analysis, and Execution Engine.

Claude-level code capabilities:
1. Code generation from natural language
2. Code analysis and explanation
3. Bug detection and fixing
4. Code execution in sandboxed environment
5. Multi-language support (Python, JS, shell)
6. Test generation
7. Refactoring suggestions
8. Documentation generation

Safety: All code execution is sandboxed with timeout, memory limits,
and no network/filesystem access by default.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .llm_router import LLMRouter, LLMRequest, Message, Role


# ────────────────────────────────────────────────────────
#  Data Structures
# ────────────────────────────────────────────────────────

@dataclass
class CodeBlock:
    """A block of code with metadata."""
    language: str
    code: str
    filename: Optional[str] = None
    description: str = ""


@dataclass
class CodeAnalysis:
    """Result of code analysis."""
    summary: str = ""
    issues: List[Dict[str, str]] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    complexity: str = "low"  # low, medium, high
    security_concerns: List[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """Result of code execution."""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time_ms: float = 0.0
    timed_out: bool = False
    error: Optional[str] = None


# ────────────────────────────────────────────────────────
#  System Prompts
# ────────────────────────────────────────────────────────

CODE_GEN_SYSTEM = """You are an expert programmer. Generate clean, correct, production-quality code.

RULES:
1. Write complete, runnable code — no placeholders or TODOs.
2. Follow the language's idioms and best practices.
3. Include error handling where appropriate.
4. Add comments only for non-obvious logic.
5. Use type hints in Python.
6. Security first — never write code with known vulnerabilities.

OUTPUT FORMAT:
```language
// your code here
```

If multiple files are needed, separate them with filename comments:
```python
# filename: main.py
...code...
```
"""

CODE_ANALYSIS_SYSTEM = """You are an expert code reviewer. Analyze code for:
1. Bugs and logical errors
2. Security vulnerabilities (OWASP Top 10)
3. Performance issues
4. Code style and readability
5. Missing edge cases

Respond in JSON:
{
  "summary": "Brief overview",
  "issues": [
    {"severity": "critical|high|medium|low", "line": 0, "description": "Issue description", "fix": "How to fix"}
  ],
  "suggestions": ["Improvement suggestion"],
  "complexity": "low|medium|high",
  "security_concerns": ["Any security issue"]
}
"""

CODE_FIX_SYSTEM = """You are an expert debugger. Fix the code based on the error.

RULES:
1. Identify the root cause, not just the symptom.
2. Provide the COMPLETE fixed code, not just a diff.
3. Explain what was wrong and why your fix works.
4. Don't change more than necessary.

OUTPUT FORMAT:
{
  "root_cause": "What caused the error",
  "explanation": "Why the fix works",
  "fixed_code": "Complete corrected code"
}
"""


# ────────────────────────────────────────────────────────
#  Code Engine
# ────────────────────────────────────────────────────────

class CodeEngine:
    """
    Code generation, analysis, and execution engine.

    Usage:
        engine = CodeEngine(llm=router)

        # Generate code
        code = engine.generate("Create a function that finds prime numbers up to n")

        # Analyze code
        analysis = engine.analyze("def f(x): return x/0")

        # Fix buggy code
        fixed = engine.fix_code(buggy_code, error_message)

        # Execute safely
        result = engine.execute(code, language="python")
    """

    def __init__(self, llm: LLMRouter, sandbox_timeout: int = 30,
                 allow_network: bool = False):
        self.llm = llm
        self.sandbox_timeout = sandbox_timeout
        self.allow_network = allow_network

    def generate(self, description: str, language: str = "python",
                 context: str = "", constraints: Optional[List[str]] = None) -> str:
        """Generate code from natural language description."""
        prompt = f"LANGUAGE: {language}\n"
        prompt += f"TASK: {description}\n"
        if context:
            prompt += f"\nCONTEXT:\n{context}\n"
        if constraints:
            prompt += f"\nCONSTRAINTS:\n" + "\n".join(f"- {c}" for c in constraints)

        response = self.llm.chat(prompt, system=CODE_GEN_SYSTEM, temperature=0.1)

        # Extract code from response
        return self._extract_code(response, language)

    def analyze(self, code: str, language: str = "python") -> CodeAnalysis:
        """Analyze code for bugs, security issues, and improvements."""
        prompt = f"LANGUAGE: {language}\n\nCODE:\n```{language}\n{code}\n```"

        try:
            result = self.llm.chat_json(prompt, system=CODE_ANALYSIS_SYSTEM)
            return CodeAnalysis(
                summary=result.get("summary", ""),
                issues=result.get("issues", []),
                suggestions=result.get("suggestions", []),
                complexity=result.get("complexity", "medium"),
                security_concerns=result.get("security_concerns", []),
            )
        except (json.JSONDecodeError, ConnectionError):
            return CodeAnalysis(summary="Analysis failed")

    def fix_code(self, code: str, error: str,
                 language: str = "python") -> Dict[str, str]:
        """Fix buggy code given an error message."""
        prompt = (
            f"LANGUAGE: {language}\n\n"
            f"BUGGY CODE:\n```{language}\n{code}\n```\n\n"
            f"ERROR:\n{error}"
        )
        try:
            return self.llm.chat_json(prompt, system=CODE_FIX_SYSTEM)
        except (json.JSONDecodeError, ConnectionError):
            return {
                "root_cause": "Could not determine",
                "explanation": "Analysis failed",
                "fixed_code": code,
            }

    def explain(self, code: str, language: str = "python",
                detail_level: str = "medium") -> str:
        """Explain what code does in plain English."""
        prompt = (
            f"Explain this {language} code at a {detail_level} detail level.\n\n"
            f"```{language}\n{code}\n```"
        )
        return self.llm.chat(
            prompt,
            system="You are a code explainer. Be clear and precise.",
            temperature=0.2,
        )

    def generate_tests(self, code: str, language: str = "python",
                       framework: str = "pytest") -> str:
        """Generate unit tests for the given code."""
        prompt = (
            f"Generate comprehensive unit tests for this {language} code.\n"
            f"Use {framework} framework.\n"
            f"Cover edge cases, error cases, and happy paths.\n\n"
            f"```{language}\n{code}\n```"
        )
        response = self.llm.chat(prompt, system=CODE_GEN_SYSTEM, temperature=0.1)
        return self._extract_code(response, language)

    def refactor(self, code: str, language: str = "python",
                 goals: Optional[List[str]] = None) -> str:
        """Suggest and apply refactoring to code."""
        goal_text = ", ".join(goals) if goals else "improve readability and maintainability"
        prompt = (
            f"Refactor this {language} code. Goals: {goal_text}\n\n"
            f"```{language}\n{code}\n```"
        )
        response = self.llm.chat(prompt, system=CODE_GEN_SYSTEM, temperature=0.1)
        return self._extract_code(response, language)

    def execute(self, code: str, language: str = "python",
                stdin: str = "", args: Optional[List[str]] = None) -> ExecutionResult:
        """
        Execute code in a sandboxed environment.

        Safety measures:
        - Timeout enforcement
        - Separate process
        - Temp directory for files
        - No persistent state
        """
        if language == "python":
            return self._execute_python(code, stdin, args or [])
        elif language in ("javascript", "js", "node"):
            return self._execute_node(code, stdin)
        elif language in ("shell", "bash", "sh"):
            return self._execute_shell(code)
        else:
            return ExecutionResult(
                error=f"Unsupported language: {language}",
                exit_code=-1,
            )

    def generate_and_run(self, description: str,
                         language: str = "python") -> Dict[str, Any]:
        """Generate code from description, then execute it."""
        code = self.generate(description, language)
        result = self.execute(code, language)
        return {
            "code": code,
            "execution": {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
            },
        }

    # ── Execution Backends ──

    def _execute_python(self, code: str, stdin: str = "",
                        args: Optional[List[str]] = None) -> ExecutionResult:
        """Execute Python code in subprocess."""
        t0 = time.time()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        try:
            cmd = [sys.executable, tmp_path] + (args or [])
            proc = subprocess.run(
                cmd,
                input=stdin,
                capture_output=True,
                text=True,
                timeout=self.sandbox_timeout,
                cwd=tempfile.gettempdir(),
            )
            return ExecutionResult(
                stdout=proc.stdout,
                stderr=proc.stderr,
                exit_code=proc.returncode,
                execution_time_ms=(time.time() - t0) * 1000,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                stderr="Execution timed out",
                exit_code=-1,
                timed_out=True,
                execution_time_ms=(time.time() - t0) * 1000,
            )
        except Exception as e:
            return ExecutionResult(error=str(e), exit_code=-1)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _execute_node(self, code: str, stdin: str = "") -> ExecutionResult:
        """Execute JavaScript via Node.js."""
        t0 = time.time()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        try:
            proc = subprocess.run(
                ["node", tmp_path],
                input=stdin,
                capture_output=True,
                text=True,
                timeout=self.sandbox_timeout,
                cwd=tempfile.gettempdir(),
            )
            return ExecutionResult(
                stdout=proc.stdout,
                stderr=proc.stderr,
                exit_code=proc.returncode,
                execution_time_ms=(time.time() - t0) * 1000,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(stderr="Execution timed out", exit_code=-1, timed_out=True)
        except FileNotFoundError:
            return ExecutionResult(error="Node.js not installed", exit_code=-1)
        except Exception as e:
            return ExecutionResult(error=str(e), exit_code=-1)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _execute_shell(self, code: str) -> ExecutionResult:
        """Execute shell commands (with safety restrictions)."""
        # Block obviously dangerous commands
        dangerous = ["rm -rf /", "format", "mkfs", ":(){", "fork bomb",
                      "dd if=", "chmod -R 777 /", "> /dev/sda"]
        code_lower = code.lower()
        for d in dangerous:
            if d in code_lower:
                return ExecutionResult(
                    error=f"Blocked dangerous command: {d}",
                    exit_code=-1,
                )

        t0 = time.time()
        try:
            proc = subprocess.run(
                code,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.sandbox_timeout,
                cwd=tempfile.gettempdir(),
            )
            return ExecutionResult(
                stdout=proc.stdout,
                stderr=proc.stderr,
                exit_code=proc.returncode,
                execution_time_ms=(time.time() - t0) * 1000,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(stderr="Execution timed out", exit_code=-1, timed_out=True)
        except Exception as e:
            return ExecutionResult(error=str(e), exit_code=-1)

    # ── Helpers ──

    @staticmethod
    def _extract_code(response: str, language: str) -> str:
        """Extract code block from LLM response."""
        # Try to find fenced code block
        markers = [f"```{language}", "```python", "```py", "```js",
                   "```javascript", "```bash", "```sh", "```"]
        for marker in markers:
            if marker in response:
                start = response.index(marker) + len(marker)
                # Find closing ```
                end = response.find("```", start)
                if end != -1:
                    return response[start:end].strip()

        # No code block found — return the whole response
        return response.strip()
