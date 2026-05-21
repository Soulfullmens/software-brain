"""
Small Model Bridge — The "Small Brain" That Powers Everything

PURPOSE: Run small quantized models (1-3B parameters, 2-6GB) locally
via Ollama, with automatic fallback to cloud APIs when needed.

THE CORE IDEA:
    Instead of needing a 175B parameter model (350GB+),
    we use a tiny model (1-3B params, 2-6GB) that:
    1. Handles reasoning, planning, and language
    2. Retrieves knowledge from Vector Memory (Big Memory)
    3. Learns from few examples (Few-Shot Learner)
    4. Gets smarter every day via Continual Learning

SUPPORTED SMALL MODELS (via Ollama):
    - phi3:mini          (3.8B, ~2.3GB)  — Microsoft, best quality/size
    - llama3.2:1b        (1B,   ~0.7GB)  — Meta, ultra-lightweight
    - llama3.2:3b        (3B,   ~2.0GB)  — Meta, good balance
    - gemma2:2b          (2.6B, ~1.6GB)  — Google, fast
    - qwen2.5:1.5b       (1.5B, ~1.0GB)  — Alibaba, multilingual
    - tinyllama:1.1b     (1.1B, ~0.6GB)  — Community, smallest

FALLBACK CHAIN:
    Local Ollama (free, private) → Gemini Flash (fast, cheap) → Claude (best quality)

MEMORY-AUGMENTED INFERENCE:
    1. User asks a question
    2. We retrieve relevant context from Vector Memory
    3. Context is injected into the prompt
    4. Small model generates a response WITH full knowledge access
    
    Result: 2GB model performs like a 200GB model for recalled knowledge
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ────────────────────────────────────────────────────────
#  Configuration
# ────────────────────────────────────────────────────────

class SmallModel(str, Enum):
    """Supported small models for local inference."""
    PHI3_MINI = "phi3:mini"
    LLAMA32_LATEST = "llama3.2:latest"  # 3B default tag
    LLAMA32_3B = "llama3.2:3b"
    LLAMA32_1B = "llama3.2:1b"
    GEMMA2_2B = "gemma2:2b"
    QWEN25_1_5B = "qwen2.5:1.5b"
    TINYLLAMA = "tinyllama:1.1b"


# Ordered by preference: quality → size → speed
# llama3.2 first because it's commonly pre-installed
DEFAULT_MODEL_PREFERENCE = [
    SmallModel.LLAMA32_LATEST,
    SmallModel.LLAMA32_3B,
    SmallModel.PHI3_MINI,
    SmallModel.GEMMA2_2B,
    SmallModel.QWEN25_1_5B,
    SmallModel.LLAMA32_1B,
    SmallModel.TINYLLAMA,
]


@dataclass
class SmallModelResponse:
    """Response from the small model."""
    content: str
    model: str
    provider: str              # "ollama" | "gemini" | "anthropic" | "fallback"
    latency_ms: float
    tokens_used: int
    memory_context_used: bool  # Whether vector memory was injected
    memory_entries_used: int   # How many memory entries were used


@dataclass
class ModelInfo:
    """Information about an available model."""
    name: str
    size_gb: float
    parameter_count: str
    available: bool


# ────────────────────────────────────────────────────────
#  Ollama Client (Local Small Model)
# ────────────────────────────────────────────────────────

class OllamaClient:
    """
    Direct HTTP client for Ollama inference.
    No external dependencies — just urllib.
    """

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self._available_models: Optional[List[str]] = None

    def is_running(self) -> bool:
        """Check if Ollama server is available."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """Get list of locally available models."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                models = [m["name"] for m in data.get("models", [])]
                self._available_models = models
                return models
        except Exception:
            return []

    def generate(
        self,
        prompt: str,
        model: str = "phi3:mini",
        system: str = "",
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """
        Generate a response from a local Ollama model.
        
        Returns dict with: response, model, total_duration, eval_count
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "10m",
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system:
            payload["system"] = system

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            return result

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "phi3:mini",
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """
        Chat-style inference with message history.
        
        messages: [{"role": "user"|"assistant"|"system", "content": "..."}]
        """
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            return result

    def generate_stream(
        self,
        prompt: str,
        model: str = "phi3:mini",
        system: str = "",
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ):
        """Stream tokens from Ollama. Yields chunks of text."""
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "keep_alive": "10m",
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system:
            payload["system"] = system

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            for raw_line in resp:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    token = obj.get("response", "")
                    if token:
                        yield token
                    if obj.get("done"):
                        return
                except json.JSONDecodeError:
                    pass

    def chat_stream(
        self,
        messages: list,
        model: str = "phi3:mini",
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ):
        """Stream chat tokens from Ollama. Yields chunks of text."""
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": "10m",
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            for raw_line in resp:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    token = obj.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if obj.get("done"):
                        return
                except json.JSONDecodeError:
                    pass

    def find_best_model(self) -> Optional[str]:
        """Find the best available small model."""
        available = self.list_models()
        if not available:
            return None

        for preferred in DEFAULT_MODEL_PREFERENCE:
            if preferred.value in available:
                return preferred.value
            # Also check partial matches (e.g., "llama3.2" matches "llama3.2:latest")
            base = preferred.value.split(":")[0]
            for avail in available:
                if base in avail:
                    return avail

        # Return first available as last resort
        return available[0] if available else None


# ────────────────────────────────────────────────────────
#  Small Model Bridge
# ────────────────────────────────────────────────────────

class SmallModelBridge:
    """
    The "Small Brain" — routes inference to the best available small model
    with automatic memory augmentation and cloud fallback.
    
    INFERENCE PIPELINE:
        1. User sends query
        2. Retrieve relevant context from Vector Memory (RAG)
        3. Build augmented prompt: system + memory_context + user_query
        4. Send to: Local Ollama → Gemini → Claude (fallback chain)
        5. Return response with metadata
    
    USAGE:
        bridge = SmallModelBridge()
        
        # Simple generation
        response = bridge.generate("What is quantum computing?")
        
        # With memory augmentation
        response = bridge.generate(
            "What does Abdul prefer?",
            memory_context="[semantic|0.92] Abdul prefers dark mode\\n[semantic|0.87] Abdul uses Python"
        )
        
        # Chat-style
        response = bridge.chat([
            {"role": "user", "content": "Remember I like TypeScript"},
            {"role": "assistant", "content": "Noted! You prefer TypeScript."},
            {"role": "user", "content": "What language do I prefer?"},
        ])
    """

    SYSTEM_PROMPT = (
        "You are Jarvis — a compact, efficient AI agent with persistent vector memory.\n\n"
        "## RULES\n"
        "- Use RELEVANT MEMORIES (provided below) to answer accurately.\n"
        "- Memories are scored by confidence (0.0-1.0). Higher = more relevant.\n"
        "- Prefer memories over training data — they reflect the user's real context.\n"
        "- Be concise, helpful, and honest about uncertainty.\n"
    )

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        preferred_model: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
    ):
        # Local inference
        self._ollama = OllamaClient(ollama_url)
        self._preferred_model = preferred_model
        self._active_model: Optional[str] = None

        # Cloud fallback keys
        self._gemini_key = gemini_api_key or os.environ.get("GEMINI_API_KEY", "")
        self._anthropic_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._openrouter_key = openrouter_api_key or os.environ.get("OPEN_ROUTER_API_KEY", "")

        # Rate-limit cache: provider → timestamp when it becomes available again
        # Skips providers instantly instead of wasting 10-30s on known 429s
        self._rate_limit_until: Dict[str, float] = {}

        # Stats
        self._stats = {
            "total_requests": 0,
            "ollama_requests": 0,
            "gemini_fallbacks": 0,
            "openrouter_fallbacks": 0,
            "anthropic_fallbacks": 0,
            "total_tokens": 0,
            "avg_latency_ms": 0.0,
        }

        # Self-diagnosis
        self._provider_errors: Dict[str, str] = {}  # last error per provider

        # Auto-detect best model
        self._detect_model()

    def _is_rate_limited(self, provider: str) -> bool:
        """Check if a provider is in rate-limit cooldown."""
        until = self._rate_limit_until.get(provider, 0)
        if time.time() < until:
            return True
        # Expired — clear it
        self._rate_limit_until.pop(provider, None)
        self._provider_errors.pop(provider, None)
        return False

    def _mark_rate_limited(self, provider: str, seconds: int = 300, reason: str = ""):
        """Mark a provider as rate-limited for N seconds."""
        self._rate_limit_until[provider] = time.time() + seconds
        self._provider_errors[provider] = reason or f"rate-limited for {seconds}s"

    def _detect_model(self):
        """Find the best available local model."""
        if self._preferred_model:
            self._active_model = self._preferred_model
            return

        if self._ollama.is_running():
            best = self._ollama.find_best_model()
            if best:
                self._active_model = best

    # ────────────────────────────────────────────────
    #  Generate (Core)
    # ────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        memory_context: str = "",
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> SmallModelResponse:
        """
        Generate a response using the best available model.
        
        The memory_context parameter is the key to the "Small Brain + Big Memory"
        architecture: it injects retrieved knowledge into the prompt, giving
        the small model access to unlimited external knowledge.
        
        Fallback chain: Ollama → OpenRouter → Gemini → Anthropic
        """
        self._stats["total_requests"] += 1
        start = time.time()

        sys_prompt = system or self.SYSTEM_PROMPT

        # Build augmented prompt with memory context
        augmented_prompt = prompt
        memory_used = False
        memory_count = 0
        if memory_context:
            augmented_prompt = (
                f"{memory_context}\n"
                f"Given the above memories, answer the following:\n{prompt}"
            )
            memory_used = True
            memory_count = memory_context.count("\n") + 1

        # Try local Ollama first
        if self._active_model and self._ollama.is_running():
            try:
                result = self._ollama.generate(
                    prompt=augmented_prompt,
                    model=self._active_model,
                    system=sys_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                latency = (time.time() - start) * 1000
                self._stats["ollama_requests"] += 1
                tokens = result.get("eval_count", 0)
                self._stats["total_tokens"] += tokens
                return SmallModelResponse(
                    content=result.get("response", ""),
                    model=self._active_model,
                    provider="ollama",
                    latency_ms=latency,
                    tokens_used=tokens,
                    memory_context_used=memory_used,
                    memory_entries_used=memory_count,
                )
            except Exception:
                pass  # Fall through to cloud

        # Cloud fallback chain — skips rate-limited providers instantly
        cloud_providers = [
            ("anthropic", self._anthropic_key, self._call_anthropic, "claude-sonnet-4-20250514", "anthropic_fallbacks"),
            ("gemini", self._gemini_key, self._call_gemini, "gemini-2.0-flash", "gemini_fallbacks"),
            ("openrouter", self._openrouter_key, self._call_openrouter, "openrouter/auto", "openrouter_fallbacks"),
        ]

        for name, key, call_fn, model_name, stat_key in cloud_providers:
            if not key or self._is_rate_limited(name):
                continue
            try:
                response = call_fn(augmented_prompt, sys_prompt, temperature, max_tokens)
                latency = (time.time() - start) * 1000
                self._stats[stat_key] += 1
                return SmallModelResponse(
                    content=response,
                    model=model_name,
                    provider=name,
                    latency_ms=latency,
                    tokens_used=0,
                    memory_context_used=memory_used,
                    memory_entries_used=memory_count,
                )
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    self._mark_rate_limited(name, 300, f"429 rate limited")
                elif e.code == 400:
                    body = ""
                    try:
                        body = e.read().decode()[:200]
                    except Exception:
                        pass
                    if "credit" in body.lower() or "balance" in body.lower():
                        self._mark_rate_limited(name, 3600, "out of credits")
                    else:
                        self._mark_rate_limited(name, 60, f"400: {body[:80]}")
            except Exception:
                pass

        # All cloud providers unavailable — use memory-based synthesis
        # This demonstrates the "Big Memory" concept: even without an LLM,
        # the retrieved memories provide a useful answer.
        latency = (time.time() - start) * 1000
        if memory_context and memory_used:
            # Extract the most relevant memory entries, filtering noise
            lines = []
            for l in memory_context.split("\n"):
                l = l.strip()
                if not l or l.startswith("==="):
                    continue
                if "[ERROR]" in l or "No model available" in l:
                    continue
                content = l.split("] ", 1)[-1] if "] " in l else l
                if len(content) > 5 and not content.startswith("PROTOTYPE:"):
                    lines.append(content)
            if lines:
                synthesis = (
                    "Based on my memories (no LLM active — using memory recall):\n" +
                    "\n".join(f"  - {l[:200]}" for l in lines[:8])
                )
                return SmallModelResponse(
                    content=synthesis,
                    model="memory-synthesis",
                    provider="memory_fallback",
                    latency_ms=latency,
                    tokens_used=0,
                    memory_context_used=True,
                    memory_entries_used=memory_count,
                )

        # Friendly fallback — no LLM and no relevant memories
        return SmallModelResponse(
            content=(
                "I don't have an active LLM right now, so I can't generate a full answer. "
                "My memory system is still working — try asking about something we've discussed before!\n\n"
                "To restore full capability:\n"
                "  • Local: ollama pull phi3:mini && ollama serve\n"
                "  • Or add API credits at openrouter.ai/settings/credits"
            ),
            model="none",
            provider="fallback",
            latency_ms=latency,
            tokens_used=0,
            memory_context_used=bool(memory_context),
            memory_entries_used=memory_count,
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        memory_context: str = "",
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> SmallModelResponse:
        """
        Chat-style inference with message history.
        Memory context is injected as a system-level prefix.
        """
        self._stats["total_requests"] += 1
        start = time.time()

        sys_prompt = system or self.SYSTEM_PROMPT
        memory_used = False
        memory_count = 0

        if memory_context:
            sys_prompt = f"{sys_prompt}\n\n## RELEVANT MEMORIES\n{memory_context}"
            memory_used = True
            memory_count = memory_context.count("\n") + 1

        # Try Ollama
        if self._active_model and self._ollama.is_running():
            try:
                chat_messages = [{"role": "system", "content": sys_prompt}] + messages
                result = self._ollama.chat(
                    messages=chat_messages,
                    model=self._active_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                latency = (time.time() - start) * 1000
                self._stats["ollama_requests"] += 1
                content = result.get("message", {}).get("content", "")
                tokens = result.get("eval_count", 0)
                self._stats["total_tokens"] += tokens
                return SmallModelResponse(
                    content=content,
                    model=self._active_model,
                    provider="ollama",
                    latency_ms=latency,
                    tokens_used=tokens,
                    memory_context_used=memory_used,
                    memory_entries_used=memory_count,
                )
            except Exception:
                pass

        # Flatten to single prompt for cloud fallback
        flat_prompt = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in messages
        )
        return self.generate(
            prompt=flat_prompt,
            system=sys_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # ────────────────────────────────────────────────
    #  Cloud Fallbacks
    # ────────────────────────────────────────────────

    def _call_gemini(
        self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> str:
        """Call Gemini API as fallback."""
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={self._gemini_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "systemInstruction": {"parts": [{"text": system}]},
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return (
                result.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )

    # OpenRouter model fallback list (tried in order — lighter models first to avoid rate limits)
    _OPENROUTER_MODELS = [
        "google/gemma-3-4b-it:free",
        "google/gemma-3-12b-it:free",
        "meta-llama/llama-3.2-3b-instruct:free",
    ]

    def _call_openrouter(
        self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> str:
        """Call OpenRouter API — tries each model once, fast fail on account-level 429."""
        url = "https://openrouter.ai/api/v1/chat/completions"
        last_error = None

        for model in self._OPENROUTER_MODELS:
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._openrouter_key}",
                    "HTTP-Referer": "https://software-brain.local",
                    "X-Title": "Software Brain SmartAgent",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    result = json.loads(resp.read())
                    content = (
                        result.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                    if content:
                        return content
            except urllib.error.HTTPError as e:
                last_error = e
                # Check if it's an account-level daily limit (all models will fail)
                if e.code == 429:
                    try:
                        body = e.read().decode()[:300]
                    except Exception:
                        body = ""
                    if "per-day" in body or "daily" in body.lower():
                        raise  # Don't try more models — entire account is limited
                    continue  # Model-specific limit — try next
                if e.code in (400, 404, 503):
                    continue
                raise
            except Exception as e:
                last_error = e
                continue

        if last_error:
            raise last_error
        raise RuntimeError("All OpenRouter models exhausted")

    def _call_anthropic(
        self, prompt: str, system: str, temperature: float, max_tokens: int
    ) -> str:
        """Call Anthropic API as fallback."""
        url = "https://api.anthropic.com/v1/messages"
        payload = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self._anthropic_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return result.get("content", [{}])[0].get("text", "")

    # ────────────────────────────────────────────────
    #  Info & Stats
    # ────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Get current status of the small model bridge."""
        ollama_running = self._ollama.is_running()
        available_models = self._ollama.list_models() if ollama_running else []

        # Provider health report
        now = time.time()
        provider_health = {}
        for name in ["openrouter", "gemini", "anthropic"]:
            until = self._rate_limit_until.get(name, 0)
            if until > now:
                remaining = int(until - now)
                provider_health[name] = f"rate-limited ({remaining}s remaining): {self._provider_errors.get(name, '')}"
            else:
                provider_health[name] = "available"

        return {
            "active_model": self._active_model,
            "ollama_running": ollama_running,
            "available_local_models": available_models,
            "gemini_available": bool(self._gemini_key) and not self._is_rate_limited("gemini"),
            "openrouter_available": bool(self._openrouter_key) and not self._is_rate_limited("openrouter"),
            "anthropic_available": bool(self._anthropic_key) and not self._is_rate_limited("anthropic"),
            "provider_health": provider_health,
            "stats": dict(self._stats),
        }

    def get_available_models(self) -> List[ModelInfo]:
        """List all available models with info."""
        models = []
        available = self._ollama.list_models() if self._ollama.is_running() else []

        model_info = {
            "phi3:mini": ("3.8B", 2.3),
            "llama3.2:1b": ("1B", 0.7),
            "llama3.2:3b": ("3B", 2.0),
            "gemma2:2b": ("2.6B", 1.6),
            "qwen2.5:1.5b": ("1.5B", 1.0),
            "tinyllama:1.1b": ("1.1B", 0.6),
        }

        for name, (params, size) in model_info.items():
            models.append(ModelInfo(
                name=name,
                size_gb=size,
                parameter_count=params,
                available=name in available,
            ))

        return models

    def switch_model(self, model_name: str) -> bool:
        """Switch to a different local model."""
        available = self._ollama.list_models()
        if model_name in available:
            self._active_model = model_name
            return True
        return False

    def generate_stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        memory_context: str = "",
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ):
        """
        Stream tokens for fastest perceived response time.
        Yields text chunks as they're generated.
        Falls back to non-streaming cloud if Ollama unavailable.
        """
        sys_prompt = system or self.SYSTEM_PROMPT
        augmented_prompt = prompt
        if memory_context:
            augmented_prompt = f"{memory_context}\n\nQUESTION: {prompt}"

        # Try Ollama streaming first
        if self._active_model and self._ollama.is_running():
            try:
                yield from self._ollama.generate_stream(
                    prompt=augmented_prompt,
                    model=self._active_model,
                    system=sys_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return
            except Exception:
                pass

        # Fallback: cloud (non-streaming, yield whole response)
        resp = self.generate(
            prompt=prompt, system=system,
            memory_context=memory_context,
            temperature=temperature, max_tokens=max_tokens,
        )
        yield resp.content

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        memory_context: str = "",
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ):
        """
        Stream chat tokens. Yields text chunks.
        Falls back to non-streaming if Ollama unavailable.
        """
        sys_prompt = system or self.SYSTEM_PROMPT
        if memory_context:
            sys_prompt = f"{sys_prompt}\n\n{memory_context}"

        # Try Ollama streaming
        if self._active_model and self._ollama.is_running():
            try:
                chat_messages = [{"role": "system", "content": sys_prompt}] + messages
                yield from self._ollama.chat_stream(
                    messages=chat_messages,
                    model=self._active_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return
            except Exception:
                pass

        # Fallback: non-streaming
        resp = self.chat(
            messages=messages, system=system,
            memory_context=memory_context,
            temperature=temperature, max_tokens=max_tokens,
        )
        yield resp.content
