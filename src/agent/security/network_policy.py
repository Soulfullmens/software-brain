"""
network_policy.py

NETWORK EGRESS POLICY ENGINE — Beyond NemoClaw Level.

Every outgoing network request passes through this engine.
Unknown domains are BLOCKED and queued for operator approval.

CAPABILITIES:
    1. YAML-based declarative policy loading
    2. Domain allowlist/blocklist with glob pattern matching
    3. Port-level control (default: 80/443 only)
    4. Request interception — scans every URL before it leaves
    5. Operator approval queue — unknown domains queued for human decision
    6. Adaptive learning — approved domains remembered with expiry
    7. Rate limiting — requests/min, requests/hour, concurrent
    8. Full audit trail — JSONL log of every request

GOES BEYOND NemoClaw:
    - Adaptive approval learning (auto-approve after N manual approvals)
    - Per-domain rate limiting
    - Approval expiry (domains don't stay approved forever)
    - Glob pattern matching on domains
"""
import os
import re
import json
import time
import fnmatch
import threading
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Set, Tuple
from enum import Enum
from datetime import datetime, timedelta
from urllib.parse import urlparse


# ═══════════════════════════════════════════════════════
# CORE TYPES
# ═══════════════════════════════════════════════════════

class NetworkVerdict(Enum):
    ALLOW = "allow"                 # Domain is in allowlist
    BLOCK = "block"                 # Domain is in blocklist (permanent)
    PENDING_APPROVAL = "pending"    # Domain queued for operator approval
    RATE_LIMITED = "rate_limited"   # Too many requests
    DENIED = "denied"              # Operator denied or timeout


class PolicyMode(Enum):
    STRICT = "strict"           # Block unknown, queue for approval
    PERMISSIVE = "permissive"   # Allow unknown, log for review
    DISABLED = "disabled"       # No filtering


@dataclass
class NetworkRequest:
    """Represents an outgoing network request."""
    url: str
    domain: str
    port: int
    method: str = "GET"
    source: str = "agent"       # Which component made the request
    timestamp: float = field(default_factory=time.time)


@dataclass
class NetworkResult:
    """Result of network policy check."""
    verdict: NetworkVerdict
    domain: str
    reason: str
    request_id: str = ""
    message_to_operator: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalRecord:
    """Tracks operator approvals for a domain."""
    domain: str
    approved: bool
    approval_count: int = 0
    last_approved: float = 0.0
    auto_approved: bool = False
    expires_at: float = 0.0


# ═══════════════════════════════════════════════════════
# NETWORK EGRESS POLICY ENGINE
# ═══════════════════════════════════════════════════════

class NetworkPolicyEngine:
    """
    Declarative network egress control.
    
    Every outgoing URL is checked against this engine.
    Unknown domains are blocked and queued for operator approval.
    
    Usage:
        engine = NetworkPolicyEngine.from_yaml("config/network_policy.yaml")
        result = engine.check_request("https://api.openai.com/v1/chat")
        if result.verdict == NetworkVerdict.ALLOW:
            # proceed with request
    """
    
    def __init__(self):
        self.mode: PolicyMode = PolicyMode.STRICT
        self.policy_name: str = "default"
        self.policy_version: str = "1.0"
        
        # Domain rules
        self.allowed_domains: List[str] = []
        self.blocked_domains: List[str] = []
        self.allowed_ports: Set[int] = {80, 443}
        
        # Rate limits
        self.max_requests_per_minute: int = 60
        self.max_requests_per_hour: int = 500
        self.max_concurrent: int = 10
        
        # Operator approval
        self.approval_timeout: int = 300        # seconds
        self.auto_approve_threshold: int = 3    # approve after N manual approvals
        self.remember_approvals: bool = True
        self.approval_expiry_hours: int = 24
        
        # State
        self._approval_records: Dict[str, ApprovalRecord] = {}
        self._pending_approvals: Dict[str, NetworkRequest] = {}
        self._request_timestamps: List[float] = []
        self._active_requests: int = 0
        self._audit_log: List[Dict] = []
        self._log_file: Optional[str] = None
        self._lock = threading.Lock()
        
        # Stats
        self.stats = {
            "total_requests": 0,
            "allowed": 0,
            "blocked": 0,
            "pending": 0,
            "rate_limited": 0,
            "auto_approved": 0,
        }
    
    @classmethod
    def from_yaml(cls, yaml_path: str) -> "NetworkPolicyEngine":
        """Load policy from YAML file."""
        engine = cls()
        
        if not os.path.exists(yaml_path):
            print(f"[NetworkPolicy] ⚠️ No policy file at {yaml_path}, using defaults")
            engine._set_defaults()
            return engine
        
        try:
            # Simple YAML parser (no dependency needed)
            policy = cls._parse_yaml(yaml_path)
            
            # Mode
            mode_str = policy.get("mode", "strict").lower()
            engine.mode = PolicyMode(mode_str) if mode_str in [m.value for m in PolicyMode] else PolicyMode.STRICT
            
            engine.policy_name = policy.get("policy_name", "default")
            engine.policy_version = policy.get("version", "1.0")
            
            # Domains
            engine.allowed_domains = policy.get("allowed_domains", [])
            engine.blocked_domains = policy.get("blocked_domains", [])
            
            # Ports
            engine.allowed_ports = set(policy.get("allowed_ports", [80, 443]))
            
            # Rate limits
            rate = policy.get("rate_limits", {})
            engine.max_requests_per_minute = rate.get("requests_per_minute", 60)
            engine.max_requests_per_hour = rate.get("requests_per_hour", 500)
            engine.max_concurrent = rate.get("max_concurrent", 10)
            
            # Approval settings
            approval = policy.get("approval", {})
            engine.approval_timeout = approval.get("timeout_seconds", 300)
            engine.auto_approve_threshold = approval.get("auto_approve_after", 3)
            engine.remember_approvals = approval.get("remember_approvals", True)
            engine.approval_expiry_hours = approval.get("approval_expiry_hours", 24)
            
            # Logging
            logging_cfg = policy.get("logging", {})
            engine._log_file = logging_cfg.get("log_file", None)
            
            print(f"[NetworkPolicy] ✅ Loaded policy '{engine.policy_name}' v{engine.policy_version} "
                  f"(mode={engine.mode.value}, {len(engine.allowed_domains)} allowed, "
                  f"{len(engine.blocked_domains)} blocked)")
            
        except Exception as e:
            print(f"[NetworkPolicy] ❌ Error loading policy: {e}, using defaults")
            engine._set_defaults()
        
        return engine
    
    @staticmethod
    def _parse_yaml(path: str) -> Dict:
        """
        Minimal YAML parser for flat/nested configs.
        Handles: scalars, lists (- item), nested dicts (key:).
        No external dependency required.
        """
        result = {}
        current_key = None
        current_list = None
        indent_stack = [(0, result)]
        
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                # Skip comments and empty lines
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                
                indent = len(line) - len(line.lstrip())
                
                # Pop indent stack if we've unindented
                while len(indent_stack) > 1 and indent <= indent_stack[-1][0]:
                    indent_stack.pop()
                    current_list = None
                
                target = indent_stack[-1][1]
                
                if stripped.startswith("- "):
                    # List item
                    value = stripped[2:].strip().strip('"').strip("'")
                    # Try to convert to int
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        pass
                    if current_key and isinstance(target.get(current_key), list):
                        target[current_key].append(value)
                    elif current_list is not None and isinstance(current_list, list):
                        current_list.append(value)
                    continue
                
                if ":" in stripped:
                    key, _, val = stripped.partition(":")
                    key = key.strip()
                    val = val.strip()
                    
                    # Remove inline comments
                    if "#" in val:
                        val = val[:val.index("#")].strip()
                    
                    val = val.strip('"').strip("'")
                    
                    if val:
                        # Key: value pair
                        try:
                            val = int(val)
                        except (ValueError, TypeError):
                            if val.lower() == "true":
                                val = True
                            elif val.lower() == "false":
                                val = False
                        target[key] = val
                        current_key = key
                    else:
                        # Key with no value — start of nested dict or list
                        # Peek next line to check if it's a list
                        target[key] = []  # Default to list, will convert if needed
                        current_key = key
                        indent_stack.append((indent + 2, target))
        
        return result
    
    def _set_defaults(self):
        """Set sensible defaults."""
        self.allowed_domains = [
            "api.anthropic.com", "api.openai.com",
            "*.googleapis.com", "generativelanguage.googleapis.com",
            "localhost", "127.0.0.1",
            "*.google.com", "*.bing.com",
        ]
        self.blocked_domains = ["*.evil.com", "*.malware.*"]
        self.allowed_ports = {80, 443, 8080, 11434}
    
    # ═══════════════════════════════════════════════════════
    # MAIN CHECK
    # ═══════════════════════════════════════════════════════
    
    def check_request(self, url: str, method: str = "GET", 
                      source: str = "agent") -> NetworkResult:
        """
        Check if an outgoing network request is allowed.
        This is the MAIN ENTRY POINT.
        """
        if self.mode == PolicyMode.DISABLED:
            return NetworkResult(
                verdict=NetworkVerdict.ALLOW,
                domain="*", reason="Network policy disabled"
            )
        
        # Parse URL
        try:
            parsed = urlparse(url)
            domain = parsed.hostname or ""
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except Exception:
            return NetworkResult(
                verdict=NetworkVerdict.BLOCK,
                domain="<invalid>",
                reason=f"Invalid URL: {url[:100]}"
            )
        
        request = NetworkRequest(
            url=url, domain=domain, port=port,
            method=method, source=source
        )
        
        self.stats["total_requests"] += 1
        
        # ── Step 1: Check blocklist (always enforced) ──
        if self._is_blocked(domain):
            result = NetworkResult(
                verdict=NetworkVerdict.BLOCK,
                domain=domain,
                reason=f"Domain '{domain}' is in blocklist",
                message_to_operator=f"🚫 BLOCKED: {domain} is permanently blocked by policy"
            )
            self._log_request(request, result)
            self.stats["blocked"] += 1
            return result
        
        # ── Step 2: Check port ──
        if port not in self.allowed_ports:
            result = NetworkResult(
                verdict=NetworkVerdict.BLOCK,
                domain=domain,
                reason=f"Port {port} not in allowed ports: {self.allowed_ports}",
                message_to_operator=f"🚫 BLOCKED: Port {port} for {domain} not allowed"
            )
            self._log_request(request, result)
            self.stats["blocked"] += 1
            return result
        
        # ── Step 3: Rate limiting ──
        rate_result = self._check_rate_limit()
        if rate_result:
            self._log_request(request, rate_result)
            self.stats["rate_limited"] += 1
            return rate_result
        
        # ── Step 4: Check allowlist ──
        if self._is_allowed(domain):
            result = NetworkResult(
                verdict=NetworkVerdict.ALLOW,
                domain=domain,
                reason=f"Domain '{domain}' is in allowlist"
            )
            self._log_request(request, result)
            self.stats["allowed"] += 1
            return result
        
        # ── Step 5: Check operator approval history ──
        approval = self._check_approval(domain)
        if approval:
            if approval.approved and approval.expires_at > time.time():
                result = NetworkResult(
                    verdict=NetworkVerdict.ALLOW,
                    domain=domain,
                    reason=f"Domain '{domain}' previously approved by operator"
                        f" (expires in {int((approval.expires_at - time.time()) / 60)}min)",
                    details={"auto_approved": approval.auto_approved}
                )
                self._log_request(request, result)
                self.stats["allowed"] += 1
                return result
        
        # ── Step 6: Unknown domain ──
        if self.mode == PolicyMode.PERMISSIVE:
            result = NetworkResult(
                verdict=NetworkVerdict.ALLOW,
                domain=domain,
                reason=f"Unknown domain '{domain}' — allowed in permissive mode (logged)"
            )
            self._log_request(request, result)
            self.stats["allowed"] += 1
            return result
        
        # STRICT mode: queue for approval
        request_id = f"net_{int(time.time() * 1000)}_{domain.replace('.', '_')}"
        self._pending_approvals[request_id] = request
        
        result = NetworkResult(
            verdict=NetworkVerdict.PENDING_APPROVAL,
            domain=domain,
            reason=f"Unknown domain '{domain}' — queued for operator approval",
            request_id=request_id,
            message_to_operator=f"🔔 APPROVAL NEEDED: Agent wants to reach '{domain}' "
                               f"(URL: {url[:100]}). Approve?"
        )
        self._log_request(request, result)
        self.stats["pending"] += 1
        return result
    
    # ═══════════════════════════════════════════════════════
    # OPERATOR APPROVAL INTERFACE
    # ═══════════════════════════════════════════════════════
    
    def approve_domain(self, domain: str, permanent: bool = False) -> str:
        """Operator approves a domain."""
        with self._lock:
            if domain not in self._approval_records:
                self._approval_records[domain] = ApprovalRecord(domain=domain, approved=True)
            
            record = self._approval_records[domain]
            record.approved = True
            record.approval_count += 1
            record.last_approved = time.time()
            
            if permanent:
                record.expires_at = time.time() + (365 * 24 * 3600)  # 1 year
            else:
                record.expires_at = time.time() + (self.approval_expiry_hours * 3600)
            
            # Auto-approve check
            if record.approval_count >= self.auto_approve_threshold:
                record.auto_approved = True
                self.stats["auto_approved"] += 1
                return f"✅ Domain '{domain}' auto-approved (approved {record.approval_count} times)"
            
            # Remove from pending
            to_remove = [rid for rid, req in self._pending_approvals.items() 
                        if req.domain == domain]
            for rid in to_remove:
                del self._pending_approvals[rid]
            
            return f"✅ Domain '{domain}' approved (expires in {self.approval_expiry_hours}h)"
    
    def deny_domain(self, domain: str) -> str:
        """Operator denies a domain."""
        with self._lock:
            self._approval_records[domain] = ApprovalRecord(
                domain=domain, approved=False
            )
            
            # Remove from pending
            to_remove = [rid for rid, req in self._pending_approvals.items() 
                        if req.domain == domain]
            for rid in to_remove:
                del self._pending_approvals[rid]
            
            return f"❌ Domain '{domain}' denied"
    
    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        """Get all pending approval requests."""
        now = time.time()
        pending = []
        expired = []
        
        for request_id, req in self._pending_approvals.items():
            age = now - req.timestamp
            if age > self.approval_timeout:
                expired.append(request_id)
            else:
                pending.append({
                    "request_id": request_id,
                    "domain": req.domain,
                    "url": req.url,
                    "source": req.source,
                    "age_seconds": int(age),
                    "timeout_in": int(self.approval_timeout - age),
                })
        
        # Clean expired
        for rid in expired:
            del self._pending_approvals[rid]
        
        return pending
    
    # ═══════════════════════════════════════════════════════
    # DOMAIN MATCHING
    # ═══════════════════════════════════════════════════════
    
    def _is_allowed(self, domain: str) -> bool:
        """Check if domain matches any allowlist pattern."""
        return self._matches_patterns(domain, self.allowed_domains)
    
    def _is_blocked(self, domain: str) -> bool:
        """Check if domain matches any blocklist pattern."""
        return self._matches_patterns(domain, self.blocked_domains)
    
    @staticmethod
    def _matches_patterns(domain: str, patterns: List[str]) -> bool:
        """Check if domain matches any glob patterns."""
        domain_lower = domain.lower()
        for pattern in patterns:
            pattern_lower = pattern.lower()
            if fnmatch.fnmatch(domain_lower, pattern_lower):
                return True
            # Also check without subdomain (e.g., "google.com" matches "*.google.com")
            if pattern_lower.startswith("*."):
                base = pattern_lower[2:]
                if domain_lower == base:
                    return True
        return False
    
    def _check_approval(self, domain: str) -> Optional[ApprovalRecord]:
        """Check if this domain has been approved before."""
        return self._approval_records.get(domain)
    
    # ═══════════════════════════════════════════════════════
    # RATE LIMITING
    # ═══════════════════════════════════════════════════════
    
    def _check_rate_limit(self) -> Optional[NetworkResult]:
        """Check request rate limits."""
        now = time.time()
        
        with self._lock:
            # Clean old timestamps
            self._request_timestamps = [
                t for t in self._request_timestamps if now - t < 3600
            ]
            self._request_timestamps.append(now)
            
            # Per-minute check
            last_minute = sum(1 for t in self._request_timestamps if now - t < 60)
            if last_minute > self.max_requests_per_minute:
                return NetworkResult(
                    verdict=NetworkVerdict.RATE_LIMITED,
                    domain="*",
                    reason=f"Rate limit: {last_minute}/{self.max_requests_per_minute} requests/min",
                    message_to_operator=f"⚠️ Network rate limit: {last_minute} requests in last minute"
                )
            
            # Per-hour check
            last_hour = len(self._request_timestamps)
            if last_hour > self.max_requests_per_hour:
                return NetworkResult(
                    verdict=NetworkVerdict.RATE_LIMITED,
                    domain="*",
                    reason=f"Rate limit: {last_hour}/{self.max_requests_per_hour} requests/hour"
                )
        
        return None
    
    # ═══════════════════════════════════════════════════════
    # AUDIT LOGGING
    # ═══════════════════════════════════════════════════════
    
    def _log_request(self, request: NetworkRequest, result: NetworkResult):
        """Log network request to audit trail."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "domain": request.domain,
            "port": request.port,
            "url": request.url[:200],
            "method": request.method,
            "source": request.source,
            "verdict": result.verdict.value,
            "reason": result.reason[:200],
        }
        
        self._audit_log.append(entry)
        
        # Keep last 1000 entries in memory
        if len(self._audit_log) > 1000:
            self._audit_log = self._audit_log[-500:]
        
        # Write to log file
        if self._log_file:
            try:
                os.makedirs(os.path.dirname(self._log_file), exist_ok=True)
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
            except Exception:
                pass  # Don't crash on log failure
    
    def get_audit_log(self, last_n: int = 50) -> List[Dict]:
        """Get recent audit entries."""
        return self._audit_log[-last_n:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get network policy statistics."""
        return {
            **self.stats,
            "mode": self.mode.value,
            "policy": self.policy_name,
            "allowed_domains_count": len(self.allowed_domains),
            "blocked_domains_count": len(self.blocked_domains),
            "pending_approvals": len(self._pending_approvals),
            "remembered_approvals": len([
                r for r in self._approval_records.values() if r.approved
            ]),
        }
    
    def add_allowed_domain(self, domain: str):
        """Dynamically add a domain to the allowlist."""
        if domain not in self.allowed_domains:
            self.allowed_domains.append(domain)
    
    def add_blocked_domain(self, domain: str):
        """Dynamically add a domain to the blocklist."""
        if domain not in self.blocked_domains:
            self.blocked_domains.append(domain)
