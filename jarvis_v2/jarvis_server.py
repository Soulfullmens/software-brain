"""
jarvis_server.py — Stdio JSON-RPC server for VS Code extension.

The VS Code extension (TypeScript) spawns this process and talks to it
via stdin/stdout using simple JSON messages (one per line).

Protocol:
  Extension sends: {"id": 1, "method": "check_risks", "params": {...}}
  Server responds: {"id": 1, "result": {...}}

Methods:
  check_risks     — Pre-run scan on code text
  record_error    — Auto-record error from terminal output  
  record_success  — Record successful run
  record_edit     — Record file save/edit
  get_status      — Session + memory stats
  dismiss         — User dismissed warning
  accept          — User found warning useful
  parse_output    — Parse raw terminal output for errors

No HTTP. No dependencies. Just stdin → Python → stdout.
"""
import sys
import json
import os
import traceback as tb_module

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_v2.jarvis_dev import JarvisDev
from jarvis_v2.traceback_parser import parse_terminal_output, has_python_error


class JarvisServer:
    """
    JSON-RPC over stdio. One JSON object per line.
    
    VS Code extension spawns: python jarvis_server.py
    Then sends/receives JSON line by line.
    """
    
    def __init__(self):
        self.pilot = JarvisDev()
        self._methods = {
            "check_risks": self._check_risks,
            "record_error": self._record_error,
            "record_success": self._record_success,
            "record_edit": self._record_edit,
            "parse_output": self._parse_output,
            "get_status": self._get_status,
            "dismiss": self._dismiss,
            "accept": self._accept,
            "ping": self._ping,
        }
    
    def run(self):
        """Main loop: read stdin, dispatch, write stdout."""
        # Signal ready
        self._send({"type": "ready", "version": "2.1"})
        
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                self._send_error(None, "Invalid JSON")
                continue
            
            req_id = request.get("id")
            method = request.get("method", "")
            params = request.get("params", {})
            
            handler = self._methods.get(method)
            if not handler:
                self._send_error(req_id, f"Unknown method: {method}")
                continue
            
            try:
                result = handler(params)
                self._send({"id": req_id, "result": result})
            except Exception as e:
                self._send_error(req_id, str(e))
    
    def _send(self, obj: dict):
        """Write one JSON line to stdout."""
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()
    
    def _send_error(self, req_id, message: str):
        """Send error response."""
        self._send({"id": req_id, "error": message})
    
    # ═══════════════════════════════════════
    # METHOD HANDLERS
    # ═══════════════════════════════════════
    
    def _check_risks(self, params: dict) -> dict:
        """
        Pre-run risk check. THE core method.
        
        Params: {file_path, code_text?, command?}
        Returns: {warnings: [{message, confidence, severity, error_class, line_hint, type}]}
        """
        file_path = params.get("file_path", "")
        code_text = params.get("code_text")
        command = params.get("command", f"python {os.path.basename(file_path)}")
        
        warnings = self.pilot.check_before_run(command, file_path, code_text)
        
        return {"warnings": warnings}
    
    def _record_error(self, params: dict) -> dict:
        """
        Record an error. Called when terminal output contains a traceback.
        
        Params: {traceback_text, file_path?, command?, code_snippet?}
        Returns: {error_class, is_repeat, times_seen, stuck, ...}
        """
        return self.pilot.record_error(
            traceback_text=params.get("traceback_text", ""),
            file_path=params.get("file_path", ""),
            command=params.get("command", ""),
            code_snippet=params.get("code_snippet", ""),
        )
    
    def _record_success(self, params: dict) -> dict:
        """Record successful run. Params: {command}"""
        self.pilot.record_success(params.get("command", ""))
        return {"ok": True}
    
    def _record_edit(self, params: dict) -> dict:
        """Record file save/edit. Params: {file_path}"""
        self.pilot.record_edit(params.get("file_path", ""))
        return {"ok": True}
    
    def _parse_output(self, params: dict) -> dict:
        """
        Parse raw terminal output for Python errors.
        Auto-records any errors found.
        
        Params: {raw_output, command?}
        Returns: {has_error, errors: [{exact_error, error_type, pattern_cause, file_path, line_number, ...}]}
        """
        raw = params.get("raw_output", "")
        command = params.get("command", "")
        
        if not has_python_error(raw):
            return {"has_error": False, "errors": []}
        
        parsed = parse_terminal_output(raw)
        
        # Auto-record each error (ZERO manual input)
        results = []
        for err in parsed:
            record_result = self.pilot.record_error(
                traceback_text=err.full_traceback,
                file_path=err.file_path,
                command=command,
                code_snippet=err.code_context,
            )
            results.append({
                "exact_error": err.exact_error,
                "error_type": err.error_type,
                "pattern_cause": err.pattern_cause,
                "file_path": err.file_path,
                "line_number": err.line_number,
                "code_context": err.code_context,
                "is_repeat": record_result.get("is_repeat", False),
                "times_seen": record_result.get("times_seen", 1),
                "stuck": record_result.get("stuck", False),
            })
        
        return {"has_error": True, "errors": results}
    
    def _get_status(self, params: dict) -> dict:
        """Get full status. Params: {}"""
        return self.pilot.status()
    
    def _dismiss(self, params: dict) -> dict:
        """User dismissed warning. Params: {}"""
        self.pilot.dismiss_warning()
        return {"ok": True}
    
    def _accept(self, params: dict) -> dict:
        """User found warning useful. Params: {}"""
        self.pilot.accept_warning()
        return {"ok": True}
    
    def _ping(self, params: dict) -> dict:
        """Health check. Params: {}"""
        return {"pong": True, "version": "2.1"}


if __name__ == "__main__":
    server = JarvisServer()
    server.run()
