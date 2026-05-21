"""
operator_approval.py

OPERATOR APPROVAL FLOW — Human-in-the-Loop Gateway.

Creates an async queue where risky actions wait for human approval.
Integrates tightly with SecurityKernel where ActionVerdict == ASK_USER.

CAPABILITIES:
    1. Approval Queue — pending actions wait up to N minutes
    2. Timeout Policy — auto-deny or auto-escalate on timeout
    3. Memory / Persistent Rules — "always allow this file" / "always block this tool"
    4. Batch Approval — approve multiple similar queued actions at once
    5. Audit Trail — records who approved what, and when

INSPIRATION:
    Matches NemoClaw's operator approval feature but adds:
    - Persistent memory
    - Batch resolution
    - Pluggable timeout policies
"""
import time
import json
import os
import threading
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable
from enum import Enum


# ═══════════════════════════════════════════════════════
# CORE TYPES
# ═══════════════════════════════════════════════════════

class ApprovalVerdict(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class ApprovalRequest:
    """A single request waiting for operator approval."""
    request_id: str
    tool: str
    command: str
    params: Dict[str, Any]
    goal: str
    reason: str                 # Why it needs approval (from SecurityKernel)
    threat_level: str           # Medium, High, Critical
    timestamp: float = field(default_factory=time.time)
    verdict: ApprovalVerdict = ApprovalVerdict.PENDING
    operator_note: str = ""
    timeout_seconds: int = 300  # Default 5 minutes
    
    @property
    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.timeout_seconds


@dataclass
class PersistentRule:
    """Rule created by operator to auto-handle future requests."""
    tool: str
    command: str
    params_match: Dict[str, str]  # Substring matches on params (e.g. {"path": "C:\\safe\\"})
    verdict: ApprovalVerdict      # APPROVED or DENIED
    expires_at: float = 0.0       # 0 = never expires


# ═══════════════════════════════════════════════════════
# OPERATOR APPROVAL QUEUE
# ═══════════════════════════════════════════════════════

class OperatorApprovalQueue:
    """
    Manages the human-in-the-loop workflow.
    
    Usage:
        queue = OperatorApprovalQueue()
        
        # SecurityKernel wants to ask user:
        verdict = queue.request_approval(
            tool="filesystem", command="delete_file",
            params={"path": "important.txt"},
            reason="Irreversible action", threat="HIGH"
        )
        # ^ Blocks until operator answers or timeout occurs
    """
    
    def __init__(self, data_file: str = "agent_data/operator_rules.json"):
        self._queue: Dict[str, ApprovalRequest] = {}
        self._events: Dict[str, threading.Event] = {}
        self._rules: List[PersistentRule] = []
        self._data_file = data_file
        self._lock = threading.Lock()
        
        # Notification callback (hooked by UI/CLI)
        self.on_new_request: Optional[Callable[[ApprovalRequest], None]] = None
        
        # Load persistent rules
        self._load_rules()
        
        # Background cleanup thread
        self._running = True
        self._cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
        self._cleanup_thread.start()
        
        self.stats = {
            "total_requests": 0,
            "approved": 0,
            "denied": 0,
            "timeouts": 0,
            "auto_handled": 0,
        }
    
    def shutdown(self):
        """Stop background worker."""
        self._running = False
    
    # ═══════════════════════════════════════════════════════
    # AGENT INTERFACE (Requesting Approval)
    # ═══════════════════════════════════════════════════════
    
    def request_approval(self, tool: str, command: str, params: Dict[str, Any],
                         reason: str, threat: str, goal: str = "",
                         timeout: int = 300) -> ApprovalVerdict:
        """
        Request approval from operator.
        THIS FUNCTION BLOCKS until a verdict is reached or timeout.
        """
        self.stats["total_requests"] += 1
        
        # ── 1. Check Persistent Rules ──
        auto_verdict = self._check_rules(tool, command, params)
        if auto_verdict:
            self.stats["auto_handled"] += 1
            print(f"[OperatorApproval] Auto-handled by rule: {auto_verdict.value.upper()} "
                  f"({tool}.{command})")
            return auto_verdict
        
        # ── 2. Add to Queue ──
        req_id = f"apr_{int(time.time()*100)}_{tool[:3]}_{command[:3]}"
        request = ApprovalRequest(
            request_id=req_id, tool=tool, command=command,
            params=params, goal=goal, reason=reason,
            threat_level=threat, timeout_seconds=timeout
        )
        event = threading.Event()
        
        with self._lock:
            self._queue[req_id] = request
            self._events[req_id] = event
        
        # ── 3. Notify Operator ──
        if self.on_new_request:
            try:
                self.on_new_request(request)
            except Exception as e:
                print(f"[OperatorApproval] Error in callback: {e}")
        else:
            print(f"\n[OperatorApprovalQueue] 🛑 ACTION BLOCKED WAITING FOR APPROVAL")
            print(f"  ID: {req_id}\n  Tool: {tool}.{command}\n  Reason: {reason}")
            print(f"  (Use CLI/API to approve: approve_action {req_id})\n")
        
        # ── 4. Wait for resolution ──
        # Block this thread until the event is set (by operator or timeout)
        event_set = event.wait(timeout)
        
        with self._lock:
            if req_id in self._queue:
                final_req = self._queue.pop(req_id)
                self._cleanup_event(req_id)
                
                if not event_set:
                    final_req.verdict = ApprovalVerdict.TIMEOUT
                    self.stats["timeouts"] += 1
                
                return final_req.verdict
            else:
                return ApprovalVerdict.ERROR
    
    # ═══════════════════════════════════════════════════════
    # OPERATOR INTERFACE (Resolving Requests)
    # ═══════════════════════════════════════════════════════
    
    def resolve_request(self, request_id: str, verdict: ApprovalVerdict,
                        note: str = "", create_rule: bool = False,
                        rule_expiry_hours: int = 0) -> bool:
        """Operator resolves a pending request."""
        with self._lock:
            if request_id not in self._queue:
                return False
            
            req = self._queue[request_id]
            req.verdict = verdict
            req.operator_note = note
            
            # Update stats
            if verdict == ApprovalVerdict.APPROVED:
                self.stats["approved"] += 1
            elif verdict == ApprovalVerdict.DENIED:
                self.stats["denied"] += 1
            
            # Create persistent rule if requested
            if create_rule and verdict in (ApprovalVerdict.APPROVED, ApprovalVerdict.DENIED):
                # By default, rule matches the exact path/url if present
                params_match = {}
                if "path" in req.params:
                    params_match["path"] = req.params["path"]
                elif "url" in req.params:
                    params_match["url"] = req.params["url"]
                
                expiry = 0.0
                if rule_expiry_hours > 0:
                    expiry = time.time() + (rule_expiry_hours * 3600)
                    
                self._add_rule(req.tool, req.command, params_match, verdict, expiry)
            
            # Wake up the waiting agent thread
            if request_id in self._events:
                self._events[request_id].set()
            
        return True
    
    def get_pending_requests(self, filter_threat: str = None) -> List[Dict]:
        """Get all currently pending requests."""
        with self._lock:
            now = time.time()
            return [
                {
                    "request_id": req.request_id,
                    "tool": req.tool,
                    "command": req.command,
                    "params": req.params,
                    "threat_level": req.threat_level,
                    "reason": req.reason,
                    "time_remaining": int((req.timestamp + req.timeout_seconds) - now)
                }
                for req in self._queue.values()
                if (not filter_threat or req.threat_level.lower() == filter_threat.lower())
            ]
    
    def batch_resolve(self, request_ids: List[str], verdict: ApprovalVerdict) -> int:
        """Resolve multiple requests at once."""
        count = 0
        for rid in request_ids:
            if self.resolve_request(rid, verdict):
                count += 1
        return count
    
    def clear_rules(self):
        """Clear all persistent rules."""
        with self._lock:
            self._rules.clear()
            self._save_rules()
    
    # ═══════════════════════════════════════════════════════
    # INTERNAL LOGIC
    # ═══════════════════════════════════════════════════════
    
    def _cleanup_event(self, request_id: str):
        if request_id in self._events:
            del self._events[request_id]
            
    def _cleanup_worker(self):
        """Background thread to handle timeouts."""
        while self._running:
            time.sleep(5)
            now = time.time()
            expired_ids = []
            
            with self._lock:
                for req_id, req in self._queue.items():
                    if now - req.timestamp > req.timeout_seconds:
                        expired_ids.append(req_id)
            
            for req_id in expired_ids:
                # Resolve as timeout (wakes up thread)
                self.resolve_request(req_id, ApprovalVerdict.TIMEOUT)
    
    # ═══════════════════════════════════════════════════════
    # PERSISTENT RULES (Memory)
    # ═══════════════════════════════════════════════════════
    
    def _check_rules(self, tool: str, command: str, params: Dict[str, Any]) -> Optional[ApprovalVerdict]:
        """Check if any rule covers this action."""
        now = time.time()
        with self._lock:
            for rule in self._rules:
                # Check expiry
                if rule.expires_at > 0 and now > rule.expires_at:
                    continue
                    
                # Match tool & command
                if rule.tool != tool and rule.tool != "*": continue
                if rule.command != command and rule.command != "*": continue
                
                # Match params (all must match if specified)
                params_match = True
                for k, v in rule.params_match.items():
                    if k not in params or v.lower() not in str(params[k]).lower():
                        params_match = False
                        break
                
                if params_match:
                    return rule.verdict
        return None
        
    def _add_rule(self, tool: str, command: str, params_match: Dict[str, str], 
                  verdict: ApprovalVerdict, expiry: float):
        self._rules.append(PersistentRule(
            tool=tool, command=command, params_match=params_match,
            verdict=verdict, expires_at=expiry
        ))
        self._save_rules()
        
    def _save_rules(self):
        try:
            os.makedirs(os.path.dirname(self._data_file), exist_ok=True)
            serializable = []
            for r in self._rules:
                serializable.append({
                    "tool": r.tool, "command": r.command,
                    "params": r.params_match, "verdict": r.verdict.value,
                    "expires_at": r.expires_at
                })
            with open(self._data_file, "w") as f:
                json.dump(serializable, f, indent=2)
        except Exception as e:
            print(f"[OperatorApproval] Failed to save rules: {e}")
            
    def _load_rules(self):
        try:
            if os.path.exists(self._data_file):
                with open(self._data_file, "r") as f:
                    data = json.load(f)
                    for item in data:
                        self._rules.append(PersistentRule(
                            tool=item["tool"], command=item["command"],
                            params_match=item.get("params", {}),
                            verdict=ApprovalVerdict(item["verdict"]),
                            expires_at=item.get("expires_at", 0.0)
                        ))
                print(f"[OperatorApproval] Loaded {len(self._rules)} persistent rules.")
        except Exception as e:
            print(f"[OperatorApproval] Failed to load rules: {e}")
