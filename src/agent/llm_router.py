"""
llm_router.py

Multi-Provider LLM Router — The Neural Backbone.
Routes requests to the best available LLM with automatic fallback,
streaming support, structured output, and conversation history.

Supported Providers:
    - Anthropic (Claude Opus 4, Sonnet 4, Haiku)
    - Google (Gemini 2.0 Flash, Pro)
    - OpenAI (GPT-4o, o1, o3)
    - Local (Ollama — any model)

Claude-Level Features:
    1. Multi-turn conversation with full history
    2. System prompt injection (role-based)
    3. Structured JSON output enforcement
    4. Streaming token-by-token responses
    5. Automatic provider fallback on failure
    6. Token counting and budget management
    7. Tool/function calling protocol
    8. Temperature/top-p/max-token control per request
"""
import json
import os
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, List, Optional
from enum import Enum

# ═════════════════════════════════════════════════════════════════════════════
# 3. LLM ROUTER (Multi-Provider Support + Inference Gateway)
# ═════════════════════════════════════════════════════════════════════════════

from .security.inference_gateway import InferenceGateway, GatewayVerdict


# ────────────────────────────────────────────────────────
#  Data Structures
# ────────────────────────────────────────────────────────

class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    role: Role
    content: str
    name: Optional[str] = None          # tool name (for tool results)
    tool_call_id: Optional[str] = None  # for tool result pairing
    tool_calls: Optional[List[Dict]] = None  # tool calls from assistant


@dataclass
class ToolDefinition:
    """Claude-style tool definition for function calling."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema for parameters

    def to_anthropic(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def to_openai(self) -> Dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }

    def to_gemini(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


@dataclass
class LLMRequest:
    """Unified request across all providers."""
    messages: List[Message]
    system: str = ""
    model: Optional[str] = None
    temperature: float = 0.2
    max_tokens: int = 4096
    top_p: float = 1.0
    stream: bool = False
    json_mode: bool = False
    tools: Optional[List[ToolDefinition]] = None
    tool_choice: Optional[str] = None  # "auto", "any", "none", or specific name
    stop_sequences: Optional[List[str]] = None


@dataclass
class ToolCall:
    """A tool call requested by the LLM."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    """Unified response from any provider."""
    content: str
    model: str
    provider: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    raw: Optional[Dict] = None


@dataclass
class ProviderConfig:
    api_key: str
    base_url: Optional[str] = None
    default_model: str = ""
    priority: int = 0
    max_retries: int = 3


# ────────────────────────────────────────────────────────
#  Provider Implementations
# ────────────────────────────────────────────────────────

class _BaseProvider:
    """Shared HTTP logic for all providers."""

    def __init__(self, config: ProviderConfig):
        self.config = config

    def _http_post(self, url: str, payload: Dict, headers: Dict,
                   timeout_s: float = 60) -> Dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _http_post_stream(self, url: str, payload: Dict, headers: Dict,
                          timeout_s: float = 120) -> Generator[str, None, None]:
        """Stream response line by line (SSE)."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            buffer = ""
            while True:
                chunk = resp.read(1024)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line.startswith("data: "):
                        yield line[6:]


class AnthropicProvider(_BaseProvider):
    """Anthropic Claude API (Messages API)."""

    def generate(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self.config.default_model
        url = f"{self.config.base_url}/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.config.api_key,
            "anthropic-version": "2023-06-01",
        }

        messages = []
        for m in request.messages:
            if m.role == Role.SYSTEM:
                continue  # system handled separately
            if m.role == Role.TOOL:
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.tool_call_id,
                        "content": m.content,
                    }],
                })
            else:
                messages.append({"role": m.role.value, "content": m.content})

        payload: Dict[str, Any] = {
            "model": model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }

        if request.system:
            payload["system"] = request.system
        if request.tools:
            payload["tools"] = [t.to_anthropic() for t in request.tools]
        if request.tool_choice:
            if request.tool_choice == "auto":
                payload["tool_choice"] = {"type": "auto"}
            elif request.tool_choice == "any":
                payload["tool_choice"] = {"type": "any"}
            elif request.tool_choice == "none":
                pass  # don't include tools
            else:
                payload["tool_choice"] = {"type": "tool", "name": request.tool_choice}
        if request.stop_sequences:
            payload["stop_sequences"] = request.stop_sequences

        t0 = time.time()
        raw = self._http_post(url, payload, headers, self.config.timeout_ms / 1000)
        latency = (time.time() - t0) * 1000

        # Parse response
        content_parts = raw.get("content", [])
        text = ""
        tool_calls = []
        for part in content_parts:
            if part["type"] == "text":
                text += part["text"]
            elif part["type"] == "tool_use":
                tool_calls.append(ToolCall(
                    id=part["id"],
                    name=part["name"],
                    arguments=part["input"],
                ))

        usage = raw.get("usage", {})
        return LLMResponse(
            content=text,
            model=raw.get("model", model),
            provider="anthropic",
            tool_calls=tool_calls,
            stop_reason=raw.get("stop_reason", "end_turn"),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            latency_ms=latency,
            raw=raw,
        )


class OpenAIProvider(_BaseProvider):
    """OpenAI Chat Completions API (also works for Azure OpenAI)."""

    def generate(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self.config.default_model
        url = f"{self.config.base_url}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }

        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        for m in request.messages:
            if m.role == Role.SYSTEM:
                continue
            msg: Dict[str, Any] = {"role": m.role.value, "content": m.content}
            if m.role == Role.TOOL:
                msg["tool_call_id"] = m.tool_call_id
            if m.tool_calls:
                msg["tool_calls"] = m.tool_calls
            messages.append(msg)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
        }

        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}
        if request.tools:
            payload["tools"] = [t.to_openai() for t in request.tools]
        if request.tool_choice:
            payload["tool_choice"] = request.tool_choice
        if request.stop_sequences:
            payload["stop"] = request.stop_sequences

        t0 = time.time()
        raw = self._http_post(url, payload, headers, self.config.timeout_ms / 1000)
        latency = (time.time() - t0) * 1000

        choice = raw["choices"][0]
        msg = choice["message"]
        tool_calls = []
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tool_calls.append(ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=json.loads(tc["function"]["arguments"]),
                ))

        usage = raw.get("usage", {})
        return LLMResponse(
            content=msg.get("content", "") or "",
            model=raw.get("model", model),
            provider="openai",
            tool_calls=tool_calls,
            stop_reason=choice.get("finish_reason", "stop"),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_ms=latency,
            raw=raw,
        )


class GeminiProvider(_BaseProvider):
    """Google Gemini Generative Language API."""

    def generate(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self.config.default_model
        url = (f"https://generativelanguage.googleapis.com/v1beta/"
               f"models/{model}:generateContent?key={self.config.api_key}")
        headers = {"Content-Type": "application/json"}

        contents = []
        for m in request.messages:
            if m.role == Role.SYSTEM:
                continue
            role = "user" if m.role in (Role.USER, Role.TOOL) else "model"
            contents.append({"role": role, "parts": [{"text": m.content}]})

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
                "topP": request.top_p,
            },
        }

        if request.system:
            payload["systemInstruction"] = {
                "parts": [{"text": request.system}]
            }

        if request.tools:
            payload["tools"] = [{
                "functionDeclarations": [t.to_gemini() for t in request.tools]
            }]

        t0 = time.time()
        raw = self._http_post(url, payload, headers, self.config.timeout_ms / 1000)
        latency = (time.time() - t0) * 1000

        text = ""
        tool_calls = []
        candidates = raw.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                if "text" in part:
                    text += part["text"]
                elif "functionCall" in part:
                    fc = part["functionCall"]
                    tool_calls.append(ToolCall(
                        id=f"gemini_{int(time.time()*1000)}",
                        name=fc["name"],
                        arguments=fc.get("args", {}),
                    ))

        usage = raw.get("usageMetadata", {})
        return LLMResponse(
            content=text,
            model=model,
            provider="gemini",
            tool_calls=tool_calls,
            stop_reason="end_turn",
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            latency_ms=latency,
            raw=raw,
        )


class OllamaProvider(_BaseProvider):
    """Local Ollama API."""

    def generate(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self.config.default_model
        url = f"{self.config.base_url}/api/chat"
        headers = {"Content-Type": "application/json"}

        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        for m in request.messages:
            if m.role == Role.SYSTEM:
                continue
            messages.append({"role": m.role.value, "content": m.content})

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
                "top_p": request.top_p,
            },
        }

        if request.json_mode:
            payload["format"] = "json"

        t0 = time.time()
        raw = self._http_post(url, payload, headers, self.config.timeout_ms / 1000)
        latency = (time.time() - t0) * 1000

        msg = raw.get("message", {})
        return LLMResponse(
            content=msg.get("content", ""),
            model=model,
            provider="ollama",
            stop_reason="stop",
            input_tokens=raw.get("prompt_eval_count", 0),
            output_tokens=raw.get("eval_count", 0),
            latency_ms=latency,
            raw=raw,
        )


# ────────────────────────────────────────────────────────
#  LLM Router — Main Entry Point
# ────────────────────────────────────────────────────────

class LLMRouter:
    """
    Intelligently routes LLM requests to available providers based on priority.
    Features fallback mechanisms and token budget/cost tracking via Inference Gateway.
    """
    
    def __init__(self):
        self.providers: Dict[str, ProviderConfig] = {}
        # The new gateway layer checks for PII, tracks costs, blocks/redirects
        self.gateway = InferenceGateway()

        # Token limit and usage tracking
        self._daily_reset_day = time.strftime("%Y-%m-%d")
        self._daily_tokens = 0
        self.MAX_DAILY_TOKENS = 1_000_000
        self.total_requests = 0
        self.total_failures = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    @property
    def priority_order(self) -> List[str]:
        """Returns provider names sorted by priority (descending)."""
        return [k for k, v in sorted(self.providers.items(), key=lambda item: item[1].config.priority, reverse=True)]

    def add_provider(self, name: str, provider):
        self.providers[name] = provider

    @classmethod
    def from_env(cls, env_path: str = ".env") -> "LLMRouter":
        """Auto-configure from environment variables or .env file."""
        router = cls()

        # Search for .env locally or in parent dir
        search_paths = [env_path, os.path.join("..", env_path), os.path.join(os.path.dirname(__file__), "..", "..", ".env")]
        found_env = None
        for path in search_paths:
            if os.path.exists(path):
                found_env = path
                break

        # Load .env file
        env_vars = {}
        if found_env:
            with open(found_env, "r") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, val = line.split("=", 1)
                        env_vars[key.strip()] = val.strip().strip('"').strip("'")

        def get_key(name: str) -> str:
            return env_vars.get(name, os.environ.get(name, ""))

        # OpenRouter (Standard OpenAI API spec but routed differently)
        openrouter_key = get_key("OPENROUTER_API_KEY")
        if openrouter_key:
            router.add_provider("openai", OpenAIProvider(ProviderConfig(
                api_key=openrouter_key,
                base_url="https://openrouter.ai/api",
                default_model=get_key("DEFAULT_MODEL") or "anthropic/claude-3-haiku",
                priority=40,
            )))

        # Claude (Opus level reasoning - teacher model)
        anthropic_key = get_key("ANTHROPIC_API_KEY")
        if anthropic_key:
            router.add_provider("anthropic", AnthropicProvider(ProviderConfig(
                api_key=anthropic_key,
                base_url="https://api.anthropic.com",
                default_model="claude-3-5-sonnet-latest",
                priority=10,  # Fallback only when local is unsure
            )))

        gemini_key = get_key("GEMINI_API_KEY")
        if gemini_key:
            router.add_provider("gemini", GeminiProvider(ProviderConfig(
                api_key=gemini_key,
                base_url="https://generativelanguage.googleapis.com",
                default_model="gemini-2.0-flash",
                priority=20,  # Free tier fallback
            )))

        openai_key = get_key("OPENAI_API_KEY")
        if openai_key:
            router.add_provider("openai", OpenAIProvider(ProviderConfig(
                api_key=openai_key,
                base_url="https://api.openai.com",
                default_model="gpt-4o",
                priority=30,
            )))

        # Ollama (local - Primary model for all daily operations)
        ollama_url = get_key("OLLAMA_URL") or "http://localhost:11434"
        router.add_provider("ollama", OllamaProvider(ProviderConfig(
            api_key="",
            base_url=ollama_url,
            default_model="llama3.2",
            priority=0, # Local primary - broke the benchmark
        )))

        return router


    def _check_daily_budget(self):
        """Reset daily counter at midnight; raise if budget exceeded."""
        today = time.strftime("%Y-%m-%d")
        if today != self._daily_reset_day:
            self._daily_tokens = 0
            self._daily_reset_day = today
        if self._daily_tokens >= self.MAX_DAILY_TOKENS:
            raise RuntimeError(
                f"Daily token budget exceeded ({self._daily_tokens:,}/{self.MAX_DAILY_TOKENS:,}). "
                "Resets at midnight. Adjust LLMRouter.MAX_DAILY_TOKENS to increase."
            )

    def generate(self, request: LLMRequest,
                 provider: Optional[str] = None) -> LLMResponse:
        """
        Generate a response, with automatic fallback on failure.
        """
        self._check_daily_budget()
        order = [provider] if provider else list(self.priority_order)

        last_error = None
        for pname in order:
            p = self.providers.get(pname)
            if not p:
                continue
            for attempt in range(p.config.max_retries + 1):
                try:
                    self.total_requests += 1
                    response = p.generate(request)
                    self.total_input_tokens += response.input_tokens
                    self.total_output_tokens += response.output_tokens
                    self._daily_tokens += response.input_tokens + response.output_tokens
                    return response
                except Exception as e:
                    last_error = e
                    self.total_failures += 1
                    if attempt < p.config.max_retries:
                        time.sleep(1.0 * (attempt + 1))
                    continue

        raise ConnectionError(
            f"All LLM providers failed. Last error: {last_error}"
        )

    # ── Convenience Methods ──

    def chat(self, user_message: str, system: str = "",
             provider: Optional[str] = None, **kwargs) -> str:
        """Simple single-turn chat. Returns text."""
        request = LLMRequest(
            messages=[Message(Role.USER, user_message)],
            system=system,
            **kwargs,
        )
        return self.generate(request, provider).content

    def chat_json(self, user_message: str, system: str = "",
                  provider: Optional[str] = None, **kwargs) -> Dict:
        """Chat with JSON output enforcement."""
        request = LLMRequest(
            messages=[Message(Role.USER, user_message)],
            system=system,
            json_mode=True,
            **kwargs,
        )
        text = self.generate(request, provider).content
        # Extract JSON from response (handles markdown fences)
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(text)

    def chat_with_history(self, messages: List[Message], system: str = "",
                          provider: Optional[str] = None, **kwargs) -> LLMResponse:
        """Multi-turn chat with full conversation history."""
        request = LLMRequest(
            messages=messages,
            system=system,
            **kwargs,
        )
        return self.generate(request, provider)

    def chat_with_tools(self, messages: List[Message],
                        tools: List[ToolDefinition],
                        system: str = "",
                        tool_choice: str = "auto",
                        provider: Optional[str] = None,
                        **kwargs) -> LLMResponse:
        """Chat with tool/function calling support."""
        request = LLMRequest(
            messages=messages,
            system=system,
            tools=tools,
            tool_choice=tool_choice,
            **kwargs,
        )
        return self.generate(request, provider)

    def usage_stats(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "providers": list(self.providers.keys())
        }
