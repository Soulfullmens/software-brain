"""
Tests for SmallModelBridge — The "Small Brain" Layer

These tests verify:
1. OllamaClient connectivity and model discovery
2. SmallModelBridge fallback chain (Ollama → Gemini → Anthropic)
3. Memory-augmented prompt construction
4. Chat-style inference
5. Model detection and switching
6. Status reporting and stats

All tests use mocked HTTP calls — no real Ollama/API needed.
"""

import pytest
import json
from unittest.mock import MagicMock, patch, PropertyMock
from io import BytesIO

from src.agent.small_model_bridge import (
    SmallModel,
    SmallModelResponse,
    ModelInfo,
    OllamaClient,
    SmallModelBridge,
    DEFAULT_MODEL_PREFERENCE,
)


# ────────────────────────────────────────────────────────
#  SmallModel Enum Tests
# ────────────────────────────────────────────────────────

class TestSmallModel:
    """Tests for the SmallModel enum."""

    def test_phi3_mini(self):
        assert SmallModel.PHI3_MINI.value == "phi3:mini"

    def test_llama32_1b(self):
        assert SmallModel.LLAMA32_1B.value == "llama3.2:1b"

    def test_all_models_are_strings(self):
        for model in SmallModel:
            assert isinstance(model.value, str)
            assert ":" in model.value or "." in model.value


class TestSmallModelResponse:
    """Tests for the SmallModelResponse data class."""

    def test_create_response(self):
        r = SmallModelResponse(
            content="Hello",
            model="phi3:mini",
            provider="ollama",
            latency_ms=150.0,
            tokens_used=20,
            memory_context_used=True,
            memory_entries_used=3,
        )
        assert r.content == "Hello"
        assert r.provider == "ollama"
        assert r.memory_context_used is True
        assert r.memory_entries_used == 3


class TestDefaultModelPreference:
    """Tests for model preference ordering."""

    def test_llama32_latest_first(self):
        assert DEFAULT_MODEL_PREFERENCE[0] == SmallModel.LLAMA32_LATEST

    def test_tinyllama_last(self):
        assert DEFAULT_MODEL_PREFERENCE[-1] == SmallModel.TINYLLAMA


# ────────────────────────────────────────────────────────
#  OllamaClient Tests (mocked)
# ────────────────────────────────────────────────────────

class TestOllamaClient:
    """Tests for the Ollama HTTP client."""

    def test_default_url(self):
        client = OllamaClient()
        assert client.base_url == "http://localhost:11434"

    def test_custom_url(self):
        client = OllamaClient("http://myserver:5555/")
        assert client.base_url == "http://myserver:5555"

    def test_is_running_when_down(self):
        client = OllamaClient("http://localhost:99999")
        assert client.is_running() is False

    def test_list_models_when_down(self):
        client = OllamaClient("http://localhost:99999")
        models = client.list_models()
        assert models == []

    @patch("urllib.request.urlopen")
    def test_is_running_when_up(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = OllamaClient()
        assert client.is_running() is True

    @patch("urllib.request.urlopen")
    def test_list_models_success(self, mock_urlopen):
        mock_resp = MagicMock()
        data = json.dumps({"models": [{"name": "phi3:mini"}, {"name": "llama3.2:1b"}]})
        mock_resp.read.return_value = data.encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = OllamaClient()
        models = client.list_models()
        assert "phi3:mini" in models
        assert "llama3.2:1b" in models

    @patch("urllib.request.urlopen")
    def test_find_best_model_phi3(self, mock_urlopen):
        mock_resp = MagicMock()
        data = json.dumps({"models": [{"name": "phi3:mini"}, {"name": "tinyllama:1.1b"}]})
        mock_resp.read.return_value = data.encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = OllamaClient()
        best = client.find_best_model()
        assert best == "phi3:mini"

    def test_find_best_model_none_available(self):
        client = OllamaClient("http://localhost:99999")
        assert client.find_best_model() is None

    @patch("urllib.request.urlopen")
    def test_generate_response_parsing(self, mock_urlopen):
        mock_resp = MagicMock()
        data = json.dumps({
            "response": "Hello there!",
            "model": "phi3:mini",
            "total_duration": 500000000,
            "eval_count": 15,
        })
        mock_resp.read.return_value = data.encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        client = OllamaClient()
        result = client.generate("Say hello", model="phi3:mini")
        assert result["response"] == "Hello there!"
        assert result["eval_count"] == 15


# ────────────────────────────────────────────────────────
#  SmallModelBridge Tests
# ────────────────────────────────────────────────────────

def create_mock_bridge(
    ollama_running=False,
    active_model=None,
    gemini_key="",
    anthropic_key="",
):
    """Create a SmallModelBridge with mocked Ollama."""
    with patch.object(SmallModelBridge, "__init__", lambda self, **kw: None):
        bridge = SmallModelBridge.__new__(SmallModelBridge)
        bridge._ollama = MagicMock(spec=OllamaClient)
        bridge._ollama.is_running.return_value = ollama_running
        bridge._ollama.list_models.return_value = []
        bridge._preferred_model = None
        bridge._active_model = active_model
        bridge._gemini_key = gemini_key
        bridge._anthropic_key = anthropic_key
        bridge._openrouter_key = ""
        bridge._rate_limit_until = {}
        bridge._provider_errors = {}
        bridge._stats = {
            "total_requests": 0,
            "ollama_requests": 0,
            "gemini_fallbacks": 0,
            "openrouter_fallbacks": 0,
            "anthropic_fallbacks": 0,
            "total_tokens": 0,
            "avg_latency_ms": 0.0,
        }
        return bridge


class TestSmallModelBridgeGenerate:
    """Tests for the generate() method."""

    def test_no_providers_returns_error(self):
        bridge = create_mock_bridge(ollama_running=False)
        response = bridge.generate("Hello")
        assert response.provider == "fallback"
        assert "[ERROR]" in response.content or "[NO LLM AVAILABLE]" in response.content or "don't have an active LLM" in response.content
        assert response.model == "none"

    def test_ollama_success(self):
        bridge = create_mock_bridge(ollama_running=True, active_model="phi3:mini")
        bridge._ollama.generate.return_value = {
            "response": "I am phi3",
            "eval_count": 10,
        }
        response = bridge.generate("Hello")
        assert response.provider == "ollama"
        assert response.content == "I am phi3"
        assert response.model == "phi3:mini"
        assert response.tokens_used == 10

    def test_ollama_failure_falls_to_gemini(self):
        bridge = create_mock_bridge(
            ollama_running=True,
            active_model="phi3:mini",
            gemini_key="fake-key",
        )
        bridge._ollama.generate.side_effect = Exception("connection error")

        with patch.object(bridge, "_call_gemini", return_value="gemini response"):
            response = bridge.generate("Hello")
            assert response.provider == "gemini"
            assert response.content == "gemini response"

    def test_gemini_failure_falls_to_anthropic(self):
        bridge = create_mock_bridge(
            ollama_running=False,
            gemini_key="fake",
            anthropic_key="fake",
        )
        with patch.object(bridge, "_call_gemini", side_effect=Exception("api error")):
            with patch.object(bridge, "_call_anthropic", return_value="claude response"):
                response = bridge.generate("Hello")
                assert response.provider == "anthropic"
                assert response.content == "claude response"

    def test_memory_context_augments_prompt(self):
        bridge = create_mock_bridge(ollama_running=True, active_model="phi3:mini")
        bridge._ollama.generate.return_value = {
            "response": "response with context",
            "eval_count": 20,
        }
        response = bridge.generate(
            "What color?",
            memory_context="[semantic|0.9] User's favorite color is blue",
        )
        assert response.memory_context_used is True
        assert response.memory_entries_used >= 1
        # Verify the prompt was augmented
        call_args = bridge._ollama.generate.call_args
        assert "favorite color" in call_args[1].get("prompt", call_args[0][0] if call_args[0] else "")

    def test_stats_increment(self):
        bridge = create_mock_bridge(ollama_running=True, active_model="phi3:mini")
        bridge._ollama.generate.return_value = {"response": "ok", "eval_count": 5}
        bridge.generate("hello")
        assert bridge._stats["total_requests"] == 1
        assert bridge._stats["ollama_requests"] == 1

    def test_no_memory_context(self):
        bridge = create_mock_bridge(ollama_running=True, active_model="phi3:mini")
        bridge._ollama.generate.return_value = {"response": "ok", "eval_count": 5}
        response = bridge.generate("Hello")
        assert response.memory_context_used is False
        assert response.memory_entries_used == 0


class TestSmallModelBridgeChat:
    """Tests for the chat() method."""

    def test_chat_with_ollama(self):
        bridge = create_mock_bridge(ollama_running=True, active_model="phi3:mini")
        bridge._ollama.chat.return_value = {
            "message": {"content": "Hi from chat"},
            "eval_count": 8,
        }
        messages = [
            {"role": "user", "content": "Hello"},
        ]
        response = bridge.chat(messages)
        assert response.provider == "ollama"
        assert response.content == "Hi from chat"

    def test_chat_falls_back_to_generate(self):
        bridge = create_mock_bridge(ollama_running=False)
        # When Ollama is down, chat should flatten messages and call generate
        with patch.object(bridge, "generate") as mock_gen:
            mock_gen.return_value = SmallModelResponse(
                content="fallback response",
                model="gemini-2.0-flash",
                provider="gemini",
                latency_ms=100,
                tokens_used=0,
                memory_context_used=False,
                memory_entries_used=0,
            )
            response = bridge.chat([{"role": "user", "content": "Hello"}])
            assert response.content == "fallback response"

    def test_chat_memory_context_injected_in_system(self):
        bridge = create_mock_bridge(ollama_running=True, active_model="phi3:mini")
        bridge._ollama.chat.return_value = {
            "message": {"content": "ctx response"},
            "eval_count": 5,
        }
        response = bridge.chat(
            [{"role": "user", "content": "Who am I?"}],
            memory_context="[semantic|0.9] User is Abdul",
        )
        assert response.memory_context_used is True
        # Verify system prompt includes memory context
        call_args = bridge._ollama.chat.call_args
        messages_sent = call_args[1].get("messages", call_args[0][0] if call_args[0] else [])
        assert any("Abdul" in m.get("content", "") for m in messages_sent)


class TestSmallModelBridgeStatus:
    """Tests for status and info methods."""

    def test_get_status_offline(self):
        bridge = create_mock_bridge(ollama_running=False)
        status = bridge.get_status()
        assert status["ollama_running"] is False
        assert status["active_model"] is None
        assert isinstance(status["stats"], dict)

    def test_get_status_online(self):
        bridge = create_mock_bridge(ollama_running=True, active_model="phi3:mini")
        bridge._ollama.list_models.return_value = ["phi3:mini"]
        status = bridge.get_status()
        assert status["ollama_running"] is True
        assert status["active_model"] == "phi3:mini"
        assert "phi3:mini" in status["available_local_models"]

    def test_get_available_models(self):
        bridge = create_mock_bridge(ollama_running=True)
        bridge._ollama.list_models.return_value = ["phi3:mini"]
        models = bridge.get_available_models()
        assert len(models) > 0
        assert all(isinstance(m, ModelInfo) for m in models)
        phi3 = next((m for m in models if m.name == "phi3:mini"), None)
        assert phi3 is not None
        assert phi3.available is True

    def test_switch_model_success(self):
        bridge = create_mock_bridge(ollama_running=True, active_model="phi3:mini")
        bridge._ollama.list_models.return_value = ["phi3:mini", "llama3.2:1b"]
        result = bridge.switch_model("llama3.2:1b")
        assert result is True
        assert bridge._active_model == "llama3.2:1b"

    def test_switch_model_unavailable(self):
        bridge = create_mock_bridge(ollama_running=True, active_model="phi3:mini")
        bridge._ollama.list_models.return_value = ["phi3:mini"]
        result = bridge.switch_model("nonexistent:model")
        assert result is False
        assert bridge._active_model == "phi3:mini"

    def test_gemini_available_flag(self):
        bridge = create_mock_bridge(gemini_key="test-key")
        status = bridge.get_status()
        assert status["gemini_available"] is True

    def test_anthropic_available_flag(self):
        bridge = create_mock_bridge(anthropic_key="test-key")
        status = bridge.get_status()
        assert status["anthropic_available"] is True
