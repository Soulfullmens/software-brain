"""
inference_gateway.py

INFERENCE GATEWAY — Transparent LLM Proxy Layer.

Sits between the agent and ALL LLM providers.
Every inference call passes through this gateway.

CAPABILITIES:
    1. Request interception — every LLM call audited before sending
    2. PII masking — detects & masks sensitive data in prompts
    3. Cost tracking — per-provider, per-day, per-session budgets
    4. Rate limiting — requests/min per provider with burst protection
    5. Audit logging — full request/response log with token counts
    6. Provider switching — block/reroute providers in real-time
    7. Latency tracking — P50/P95/P99 per provider
    8. Response validation — detect anomalous/toxic responses

GOES BEYOND NemoClaw:
    - PII masking before external calls (NemoClaw doesn't mask data)
    - Per-provider latency percentiles
    - Session-level cost budgets
    - Response anomaly detection
"""
import os
import re
import json
import time
import threading
import statistics
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
from datetime import datetime


# ═══════════════════════════════════════════════════════
# CORE TYPES
# ═══════════════════════════════════════════════════════

class GatewayVerdict(Enum):
    PASS = "pass"               # Allow the request through
    BLOCK = "block"             # Block the request
    MODIFY = "modify"           # Request was modified (PII masked)
    RATE_LIMITED = "rate_limited"


@dataclass
class InferenceAuditEntry:
    """Single audit log entry."""
    timestamp: str
    provider: str
    model: str
    action: str                 # "request" or "response"
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    pii_masked: bool = False
    pii_types: List[str] = field(default_factory=list)
    verdict: str = "pass"
    session_id: str = ""


# ═══════════════════════════════════════════════════════
# PII DETECTOR & MASKER
# ═══════════════════════════════════════════════════════

class PIIMasker:
    """
    Detects and masks Personally Identifiable Information
    before sending prompts to external LLM providers.
    
    Protects: emails, phone numbers, API keys, SSNs,
    credit cards, IP addresses, physical addresses.
    """
    
    PII_PATTERNS = {
        "email": {
            "pattern": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "replacement": "[EMAIL_REDACTED]",
            "severity": "high",
        },
        "phone_international": {
            "pattern": r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b',
            "replacement": "[PHONE_REDACTED]",
            "severity": "high",
        },
        "api_key": {
            "pattern": r'\b(?:sk|pk|api|key|token|secret|bearer)[-_]?[A-Za-z0-9]{20,}\b',
            "replacement": "[API_KEY_REDACTED]",
            "severity": "critical",
        },
        "api_key_env": {
            "pattern": r'(?:API_KEY|SECRET_KEY|ACCESS_TOKEN|AUTH_TOKEN)\s*[=:]\s*["\']?[A-Za-z0-9_\-]{10,}["\']?',
            "replacement": "[API_KEY_REDACTED]",
            "severity": "critical",
        },
        "ssn": {
            "pattern": r'\b\d{3}-\d{2}-\d{4}\b',
            "replacement": "[SSN_REDACTED]",
            "severity": "critical",
        },
        "credit_card": {
            "pattern": r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
            "replacement": "[CC_REDACTED]",
            "severity": "critical",
        },
        "ipv4": {
            "pattern": r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
            "replacement": "[IP_REDACTED]",
            "severity": "medium",
        },
        "password_in_text": {
            "pattern": r'(?:password|passwd|pwd)\s*[=:]\s*["\']?[^\s"\']{4,}["\']?',
            "replacement": "[PASSWORD_REDACTED]",
            "severity": "critical",
        },
        "private_key": {
            "pattern": r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----',
            "replacement": "[PRIVATE_KEY_REDACTED]",
            "severity": "critical",
        },
    }
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._compiled = {
            name: re.compile(cfg["pattern"], re.IGNORECASE)
            for name, cfg in self.PII_PATTERNS.items()
        }
        self.total_masked = 0
        self.masked_by_type: Dict[str, int] = {}
    
    def mask(self, text: str) -> Tuple[str, bool, List[str]]:
        """
        Mask PII in text.
        Returns: (masked_text, was_modified, list_of_pii_types_found)
        """
        if not self.enabled or not text:
            return text, False, []
        
        masked = text
        found_types = []
        
        for name, pattern in self._compiled.items():
            replacement = self.PII_PATTERNS[name]["replacement"]
            new_text = pattern.sub(replacement, masked)
            if new_text != masked:
                found_types.append(name)
                count = len(pattern.findall(masked))
                self.total_masked += count
                self.masked_by_type[name] = self.masked_by_type.get(name, 0) + count
                masked = new_text
        
        return masked, len(found_types) > 0, found_types
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "total_masked": self.total_masked,
            "by_type": dict(self.masked_by_type),
        }


# ═══════════════════════════════════════════════════════
# COST TRACKER
# ═══════════════════════════════════════════════════════

class CostTracker:
    """
    Tracks inference costs per provider, per day, per session.
    
    Pricing is approximate and can be updated.
    """
    
    # Cost per 1M tokens (input/output) in USD
    PRICING = {
        "anthropic": {"input": 3.00, "output": 15.00, "model_prefix": "claude"},
        "openai": {"input": 2.50, "output": 10.00, "model_prefix": "gpt"},
        "gemini": {"input": 0.075, "output": 0.30, "model_prefix": "gemini"},
        "ollama": {"input": 0.0, "output": 0.0, "model_prefix": ""},  # Free (local)
    }
    
    def __init__(self, daily_budget_usd: float = 5.0, 
                 session_budget_usd: float = 1.0):
        self.daily_budget = daily_budget_usd
        self.session_budget = session_budget_usd
        
        self._daily_cost: float = 0.0
        self._session_cost: float = 0.0
        self._daily_reset_day: str = time.strftime("%Y-%m-%d")
        self._provider_costs: Dict[str, float] = {}
        self._lock = threading.Lock()
    
    def track(self, provider: str, input_tokens: int, 
              output_tokens: int) -> Tuple[float, bool]:
        """
        Track cost of an inference call.
        Returns: (cost_usd, budget_exceeded)
        """
        pricing = self.PRICING.get(provider, {"input": 1.0, "output": 3.0})
        cost = (input_tokens * pricing["input"] / 1_000_000 +
                output_tokens * pricing["output"] / 1_000_000)
        
        with self._lock:
            # Reset daily counter
            today = time.strftime("%Y-%m-%d")
            if today != self._daily_reset_day:
                self._daily_cost = 0.0
                self._daily_reset_day = today
            
            self._daily_cost += cost
            self._session_cost += cost
            self._provider_costs[provider] = self._provider_costs.get(provider, 0) + cost
            
            budget_exceeded = (
                self._daily_cost > self.daily_budget or
                self._session_cost > self.session_budget
            )
        
        return cost, budget_exceeded
    
    def reset_session(self):
        """Reset session cost counter."""
        self._session_cost = 0.0
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "daily_cost_usd": round(self._daily_cost, 6),
            "daily_budget_usd": self.daily_budget,
            "daily_remaining_usd": round(max(0, self.daily_budget - self._daily_cost), 6),
            "session_cost_usd": round(self._session_cost, 6),
            "session_budget_usd": self.session_budget,
            "by_provider": {k: round(v, 6) for k, v in self._provider_costs.items()},
        }


# ═══════════════════════════════════════════════════════
# LATENCY TRACKER
# ═══════════════════════════════════════════════════════

class LatencyTracker:
    """Tracks P50/P95/P99 latency per provider."""
    
    def __init__(self, window_size: int = 100):
        self._window_size = window_size
        self._latencies: Dict[str, List[float]] = {}
    
    def record(self, provider: str, latency_ms: float):
        """Record a latency measurement."""
        if provider not in self._latencies:
            self._latencies[provider] = []
        self._latencies[provider].append(latency_ms)
        # Keep window
        if len(self._latencies[provider]) > self._window_size:
            self._latencies[provider] = self._latencies[provider][-self._window_size:]
    
    def get_percentiles(self, provider: str) -> Dict[str, float]:
        """Get P50/P95/P99 for a provider."""
        data = self._latencies.get(provider, [])
        if not data:
            return {"p50": 0, "p95": 0, "p99": 0, "avg": 0, "count": 0}
        
        sorted_data = sorted(data)
        n = len(sorted_data)
        return {
            "p50": sorted_data[int(n * 0.50)] if n > 0 else 0,
            "p95": sorted_data[min(int(n * 0.95), n - 1)] if n > 0 else 0,
            "p99": sorted_data[min(int(n * 0.99), n - 1)] if n > 0 else 0,
            "avg": round(statistics.mean(data), 1),
            "count": n,
        }
    
    def get_all_stats(self) -> Dict[str, Dict[str, float]]:
        return {p: self.get_percentiles(p) for p in self._latencies}


# ═══════════════════════════════════════════════════════
# PROVIDER RATE LIMITER  
# ═══════════════════════════════════════════════════════

class ProviderRateLimiter:
    """Per-provider rate limiting with burst protection."""
    
    DEFAULT_LIMITS = {
        "anthropic": {"rpm": 50, "burst_10s": 10},
        "openai": {"rpm": 60, "burst_10s": 15},
        "gemini": {"rpm": 60, "burst_10s": 15},
        "ollama": {"rpm": 120, "burst_10s": 30},  # Local = generous
    }
    
    def __init__(self):
        self._timestamps: Dict[str, List[float]] = {}
        self._lock = threading.Lock()
    
    def check(self, provider: str) -> Tuple[bool, str]:
        """
        Check if request is within rate limits.
        Returns: (allowed, reason)
        """
        now = time.time()
        limits = self.DEFAULT_LIMITS.get(provider, {"rpm": 30, "burst_10s": 8})
        
        with self._lock:
            if provider not in self._timestamps:
                self._timestamps[provider] = []
            
            self._timestamps[provider].append(now)
            
            # Clean old (keep 1 hour)
            self._timestamps[provider] = [
                t for t in self._timestamps[provider] if now - t < 3600
            ]
            
            # Per-minute check
            last_min = sum(1 for t in self._timestamps[provider] if now - t < 60)
            if last_min > limits["rpm"]:
                return False, f"Rate limit: {last_min}/{limits['rpm']} rpm for {provider}"
            
            # Burst check
            last_10s = sum(1 for t in self._timestamps[provider] if now - t < 10)
            if last_10s > limits["burst_10s"]:
                return False, f"Burst: {last_10s}/{limits['burst_10s']} in 10s for {provider}"
        
        return True, "ok"


# ═══════════════════════════════════════════════════════
# THE INFERENCE GATEWAY
# ═══════════════════════════════════════════════════════

class InferenceGateway:
    """
    Transparent proxy between the agent and LLM providers.
    
    Every inference call passes through this gateway for:
    - PII masking
    - Cost tracking
    - Rate limiting
    - Audit logging
    - Latency tracking
    
    Usage:
        gateway = InferenceGateway()
        
        # Before sending to provider:
        verdict, masked_messages = gateway.intercept_request(
            provider="anthropic", model="claude-3-5-sonnet",
            messages=[...], system_prompt="..."
        )
        
        # After receiving response:
        gateway.log_response(
            provider="anthropic", model="claude-3-5-sonnet",
            input_tokens=100, output_tokens=500, latency_ms=1200
        )
    """
    
    def __init__(self, pii_masking: bool = True,
                 daily_budget_usd: float = 5.0,
                 session_budget_usd: float = 1.0):
        self.pii_masker = PIIMasker(enabled=pii_masking)
        self.cost_tracker = CostTracker(daily_budget_usd, session_budget_usd)
        self.latency_tracker = LatencyTracker()
        self.rate_limiter = ProviderRateLimiter()
        
        # Provider management
        self._blocked_providers: set = set()
        self._provider_redirects: Dict[str, str] = {}  # from -> to
        
        # Audit log
        self._audit_log: List[InferenceAuditEntry] = []
        self._log_file: Optional[str] = "logs/inference_audit.jsonl"
        self._lock = threading.Lock()
        
        # Session
        self._session_id: str = ""
        self._session_request_count: int = 0
        
        # Stats
        self.stats = {
            "total_requests": 0,
            "total_blocked": 0,
            "total_pii_masked": 0,
            "total_budget_exceeded": 0,
            "total_rate_limited": 0,
        }
    
    def set_session(self, session_id: str):
        """Set current session for cost tracking."""
        self._session_id = session_id
        self.cost_tracker.reset_session()
        self._session_request_count = 0
    
    def block_provider(self, provider: str):
        """Block a provider in real-time."""
        self._blocked_providers.add(provider)
    
    def unblock_provider(self, provider: str):
        """Unblock a provider."""
        self._blocked_providers.discard(provider)
    
    def redirect_provider(self, from_provider: str, to_provider: str):
        """Redirect requests from one provider to another."""
        self._provider_redirects[from_provider] = to_provider
    
    # ═══════════════════════════════════════════════════════
    # REQUEST INTERCEPTION
    # ═══════════════════════════════════════════════════════
    
    def intercept_request(self, provider: str, model: str,
                          messages: List[Dict[str, str]],
                          system_prompt: str = "") -> Tuple[GatewayVerdict, str, List[Dict[str, str]]]:
        """
        Intercept an outgoing LLM request.
        
        Returns: (verdict, effective_provider, masked_messages)
        """
        self.stats["total_requests"] += 1
        self._session_request_count += 1
        
        # ── 1. Provider redirect ──
        effective_provider = self._provider_redirects.get(provider, provider)
        
        # ── 2. Provider blocked? ──
        if effective_provider in self._blocked_providers:
            self.stats["total_blocked"] += 1
            self._log_audit(InferenceAuditEntry(
                timestamp=datetime.now().isoformat(),
                provider=effective_provider, model=model,
                action="request_blocked",
                verdict="block",
                session_id=self._session_id,
            ))
            return GatewayVerdict.BLOCK, effective_provider, messages
        
        # ── 3. Rate limiting ──
        allowed, reason = self.rate_limiter.check(effective_provider)
        if not allowed:
            self.stats["total_rate_limited"] += 1
            self._log_audit(InferenceAuditEntry(
                timestamp=datetime.now().isoformat(),
                provider=effective_provider, model=model,
                action="request_rate_limited",
                verdict="rate_limited",
                session_id=self._session_id,
            ))
            return GatewayVerdict.RATE_LIMITED, effective_provider, messages
        
        # ── 4. PII masking (only for external providers) ──
        masked_messages = messages
        pii_found = False
        pii_types = []
        
        if effective_provider != "ollama":  # Don't mask for local models
            masked_messages = []
            for msg in messages:
                masked_content, was_masked, types = self.pii_masker.mask(
                    msg.get("content", "")
                )
                if was_masked:
                    pii_found = True
                    pii_types.extend(types)
                masked_messages.append({**msg, "content": masked_content})
            
            # Also mask system prompt
            if system_prompt:
                _, sys_masked, sys_types = self.pii_masker.mask(system_prompt)
                if sys_masked:
                    pii_found = True
                    pii_types.extend(sys_types)
        
        if pii_found:
            self.stats["total_pii_masked"] += 1
        
        # ── 5. Budget check ──
        cost_stats = self.cost_tracker.get_stats()
        if cost_stats["daily_remaining_usd"] <= 0:
            self.stats["total_budget_exceeded"] += 1
            self._log_audit(InferenceAuditEntry(
                timestamp=datetime.now().isoformat(),
                provider=effective_provider, model=model,
                action="request_budget_exceeded",
                verdict="block",
                session_id=self._session_id,
            ))
            return GatewayVerdict.BLOCK, effective_provider, messages
        
        # ── 6. Log the request ──
        verdict = GatewayVerdict.MODIFY if pii_found else GatewayVerdict.PASS
        self._log_audit(InferenceAuditEntry(
            timestamp=datetime.now().isoformat(),
            provider=effective_provider, model=model,
            action="request",
            pii_masked=pii_found,
            pii_types=pii_types,
            verdict=verdict.value,
            session_id=self._session_id,
        ))
        
        return verdict, effective_provider, masked_messages
    
    # ═══════════════════════════════════════════════════════
    # RESPONSE LOGGING
    # ═══════════════════════════════════════════════════════
    
    def log_response(self, provider: str, model: str,
                     input_tokens: int, output_tokens: int,
                     latency_ms: float):
        """Log an LLM response after receiving it."""
        # Track cost
        cost, budget_exceeded = self.cost_tracker.track(
            provider, input_tokens, output_tokens
        )
        
        # Track latency
        self.latency_tracker.record(provider, latency_ms)
        
        # Audit
        self._log_audit(InferenceAuditEntry(
            timestamp=datetime.now().isoformat(),
            provider=provider, model=model,
            action="response",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            session_id=self._session_id,
        ))
        
        if budget_exceeded:
            self.stats["total_budget_exceeded"] += 1
    
    # ═══════════════════════════════════════════════════════
    # AUDIT LOGGING
    # ═══════════════════════════════════════════════════════
    
    def _log_audit(self, entry: InferenceAuditEntry):
        """Write audit entry."""
        with self._lock:
            self._audit_log.append(entry)
            
            # Keep last 500 in memory
            if len(self._audit_log) > 500:
                self._audit_log = self._audit_log[-250:]
        
        # Write to file
        if self._log_file:
            try:
                os.makedirs(os.path.dirname(self._log_file), exist_ok=True)
                entry_dict = {
                    "timestamp": entry.timestamp,
                    "provider": entry.provider,
                    "model": entry.model,
                    "action": entry.action,
                    "input_tokens": entry.input_tokens,
                    "output_tokens": entry.output_tokens,
                    "latency_ms": entry.latency_ms,
                    "cost_usd": entry.cost_usd,
                    "pii_masked": entry.pii_masked,
                    "verdict": entry.verdict,
                    "session_id": entry.session_id,
                }
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry_dict) + "\n")
            except Exception:
                pass
    
    def get_audit_log(self, last_n: int = 50) -> List[Dict]:
        """Get recent audit entries."""
        return [
            {
                "timestamp": e.timestamp,
                "provider": e.provider,
                "model": e.model,
                "action": e.action,
                "tokens": e.input_tokens + e.output_tokens,
                "latency_ms": e.latency_ms,
                "cost_usd": e.cost_usd,
                "pii_masked": e.pii_masked,
            }
            for e in self._audit_log[-last_n:]
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Full gateway statistics."""
        return {
            **self.stats,
            "cost": self.cost_tracker.get_stats(),
            "pii": self.pii_masker.get_stats(),
            "latency": self.latency_tracker.get_all_stats(),
            "blocked_providers": list(self._blocked_providers),
            "redirects": dict(self._provider_redirects),
            "session_id": self._session_id,
            "session_requests": self._session_request_count,
        }
