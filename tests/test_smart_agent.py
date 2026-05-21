"""
Tests for SmartAgent — The Unified "Small Brain + Big Memory" Agent

These tests verify:
1. Agent initialization and configuration
2. Chat (memory-augmented conversation)
3. Correction learning
4. Teaching (few-shot via SmartAgent interface)
5. Recognition
6. Memory operations (remember, recall, ingest)
7. Skill learning
8. Session management
9. Status reporting
10. Status text formatting

All components are mocked — runs without any external deps.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.agent.smart_agent import (
    SmartAgent,
    SmartResponse,
    AgentStatus,
)
from src.agent.small_model_bridge import SmallModelResponse
from src.memory.vector_store import VectorMemoryStore, RetrievalResult, VectorStoreStats
from src.learning.few_shot_learner import (
    FewShotLearner,
    Prototype,
    RecognitionResult,
    LearnerStats,
)
from src.learning.continual_learner import (
    ContinualLearner,
    LearningEvent,
    ContinualLearnerStats,
)


# ────────────────────────────────────────────────────────
#  Data Structure Tests
# ────────────────────────────────────────────────────────

class TestSmartResponse:
    """Tests for the SmartResponse data class."""

    def test_create_response(self):
        r = SmartResponse(
            content="Hello world",
            model_used="phi3:mini",
            provider="ollama",
            memories_retrieved=5,
            memories_used_in_context=True,
            new_facts_learned=2,
            latency_ms=150.0,
        )
        assert r.content == "Hello world"
        assert r.memories_retrieved == 5
        assert r.thinking is None

    def test_with_thinking(self):
        r = SmartResponse(
            content="Answer",
            model_used="phi3:mini",
            provider="ollama",
            memories_retrieved=0,
            memories_used_in_context=False,
            new_facts_learned=0,
            latency_ms=50.0,
            thinking="Let me think step by step...",
        )
        assert r.thinking == "Let me think step by step..."


class TestAgentStatus:
    """Tests for the AgentStatus data class."""

    def test_create_status(self):
        s = AgentStatus(
            active_model="phi3:mini",
            ollama_running=True,
            available_models=["phi3:mini"],
            total_memories=100,
            memories_by_collection={"semantic": 50, "episodic": 50},
            prototypes_learned=5,
            facts_extracted=42,
            total_interactions=20,
            knowledge_growth_rate=3.5,
            avg_latency_ms=200.0,
            total_requests=10,
        )
        assert s.total_memories == 100
        assert s.knowledge_growth_rate == 3.5


# ────────────────────────────────────────────────────────
#  Mock SmartAgent Factory
# ────────────────────────────────────────────────────────

def create_mock_agent():
    """Create a SmartAgent with all components mocked."""
    with patch.object(SmartAgent, "__init__", lambda self, **kw: None):
        agent = SmartAgent.__new__(SmartAgent)

        # Mock memory
        agent._memory = MagicMock(spec=VectorMemoryStore)
        agent._memory.retrieve_for_context.return_value = ""
        agent._memory.retrieve.return_value = []
        agent._memory.store.return_value = "mock-id"
        agent._memory.get_stats.return_value = VectorStoreStats(
            total_entries=0,
            entries_by_collection={c: 0 for c in ["episodic", "semantic", "procedural", "prototypes", "web_knowledge"]},
            storage_path="/tmp",
            embedding_model="mock",
            embedding_dimensions=384,
        )

        # Mock brain
        agent._brain = MagicMock()
        agent._brain.generate.return_value = SmallModelResponse(
            content="Test response",
            model="phi3:mini",
            provider="ollama",
            latency_ms=100.0,
            tokens_used=20,
            memory_context_used=False,
            memory_entries_used=0,
        )
        agent._brain.chat.return_value = SmallModelResponse(
            content="Chat response",
            model="phi3:mini",
            provider="ollama",
            latency_ms=100.0,
            tokens_used=20,
            memory_context_used=False,
            memory_entries_used=0,
        )
        agent._brain.get_status.return_value = {
            "active_model": "phi3:mini",
            "ollama_running": True,
            "available_local_models": ["phi3:mini"],
        }

        # Mock few-shot
        agent._few_shot = MagicMock(spec=FewShotLearner)
        agent._few_shot.learn.return_value = Prototype(
            name="test", category="general", description="Test",
            examples=[], memory_id="p-1", created_at="2026-01-01",
        )
        agent._few_shot.recognize.return_value = RecognitionResult(
            matched=False, prototype_name=None, confidence=0.0,
            category=None, all_matches=[], input_text="",
        )
        agent._few_shot.get_stats.return_value = LearnerStats(
            total_prototypes=0, categories={},
            total_recognitions=0, most_recognized=None,
        )

        # Mock continual learner
        agent._continual = MagicMock(spec=ContinualLearner)
        agent._continual.learn_from_interaction.return_value = LearningEvent(
            event_type="interaction", content="test",
            extracted_facts=["fact1"], source="test",
            timestamp="2026-01-01T00:00:00", importance=0.5,
        )
        agent._continual.get_stats.return_value = ContinualLearnerStats(
            total_events_processed=0, facts_extracted=0,
            corrections_applied=0, consolidations_run=0,
            last_consolidation=None, knowledge_growth_rate=0.0,
        )

        # State
        agent._system_prompt = "You are SmartAgent."
        agent._conversation = []
        agent._session_start = datetime.now()
        agent._total_requests = 0
        agent._total_latency = 0.0
        agent._data_dir = "/tmp/test"

        return agent


# ────────────────────────────────────────────────────────
#  Chat Tests
# ────────────────────────────────────────────────────────

class TestSmartAgentChat:
    """Tests for the chat() method — main interface."""

    def test_basic_chat(self):
        agent = create_mock_agent()
        response = agent.chat("Hello!")
        assert isinstance(response, SmartResponse)
        assert response.content == "Test response"

    def test_chat_increments_requests(self):
        agent = create_mock_agent()
        agent.chat("Hello")
        assert agent._total_requests == 1
        agent.chat("World")
        assert agent._total_requests == 2

    def test_chat_adds_to_conversation(self):
        agent = create_mock_agent()
        agent.chat("First message")
        assert len(agent._conversation) == 2  # user + assistant
        assert agent._conversation[0]["role"] == "user"
        assert agent._conversation[1]["role"] == "assistant"

    def test_chat_with_memory_retrieval(self):
        agent = create_mock_agent()
        agent._memory.retrieve_for_context.return_value = (
            "=== RETRIEVED MEMORIES ===\n"
            "[semantic|0.9] Abdul prefers dark mode\n"
            "=== END MEMORIES ===\n"
        )
        response = agent.chat("What do I prefer?")
        assert response.memories_used_in_context is True
        assert response.memories_retrieved > 0

    def test_chat_without_memory(self):
        agent = create_mock_agent()
        response = agent.chat("Hello", use_memory=False)
        agent._memory.retrieve_for_context.assert_not_called()
        assert response.memories_used_in_context is False

    def test_chat_learns_from_interaction(self):
        agent = create_mock_agent()
        agent.chat("My favorite color is blue")
        agent._continual.learn_from_interaction.assert_called_once()

    def test_chat_returns_latency(self):
        agent = create_mock_agent()
        response = agent.chat("Hello")
        assert response.latency_ms >= 0

    def test_multi_turn_uses_chat_mode(self):
        agent = create_mock_agent()
        # First turn uses generate (single turn)
        agent.chat("Hello")
        agent._brain.generate.assert_called_once()

        # Second turn should use chat (multi-turn)
        agent.chat("Follow up")
        agent._brain.chat.assert_called_once()

    def test_chat_response_fields(self):
        agent = create_mock_agent()
        response = agent.chat("test")
        assert response.model_used == "phi3:mini"
        assert response.provider == "ollama"
        assert isinstance(response.new_facts_learned, int)


# ────────────────────────────────────────────────────────
#  Correction Tests
# ────────────────────────────────────────────────────────

class TestSmartAgentCorrect:
    """Tests for the correct() method."""

    def test_correct_returns_acknowledgment(self):
        agent = create_mock_agent()
        result = agent.correct("Wrong answer", "Right answer")
        assert "Right answer" in result

    def test_correct_calls_continual_learner(self):
        agent = create_mock_agent()
        agent.correct("Wrong", "Right")
        agent._continual.learn_from_correction.assert_called_once_with(
            original_response="Wrong",
            correction="Right",
        )


# ────────────────────────────────────────────────────────
#  Teach Tests
# ────────────────────────────────────────────────────────

class TestSmartAgentTeach:
    """Tests for the teach() method."""

    def test_teach_returns_confirmation(self):
        agent = create_mock_agent()
        result = agent.teach(
            name="kitkat",
            description="Chocolate bar",
            examples=["red wrapper"],
            category="food",
        )
        assert "kitkat" in result
        assert "1 example" in result

    def test_teach_with_multiple_examples(self):
        agent = create_mock_agent()
        result = agent.teach(
            name="spam",
            description="Junk email",
            examples=["Buy now!", "You won!", "Free money!"],
        )
        assert "3 example" in result

    def test_teach_calls_few_shot(self):
        agent = create_mock_agent()
        agent.teach("test_concept", "A test concept", ["example 1"])
        agent._few_shot.learn.assert_called_once()


# ────────────────────────────────────────────────────────
#  Recognize Tests
# ────────────────────────────────────────────────────────

class TestSmartAgentRecognize:
    """Tests for the recognize() method."""

    def test_recognize_no_match(self):
        agent = create_mock_agent()
        result = agent.recognize("random text")
        assert result["matched"] is False
        assert result["name"] is None

    def test_recognize_match(self):
        agent = create_mock_agent()
        agent._few_shot.recognize.return_value = RecognitionResult(
            matched=True,
            prototype_name="spam",
            confidence=0.85,
            category="email",
            all_matches=[{"name": "spam", "confidence": 0.85}],
            input_text="buy now!",
        )
        result = agent.recognize("buy now!")
        assert result["matched"] is True
        assert result["name"] == "spam"
        assert result["confidence"] == 0.85

    def test_recognize_with_category(self):
        agent = create_mock_agent()
        agent.recognize("test", category="food")
        call_args = agent._few_shot.recognize.call_args
        assert call_args[1].get("category") == "food"


# ────────────────────────────────────────────────────────
#  Memory Tests
# ────────────────────────────────────────────────────────

class TestSmartAgentMemory:
    """Tests for remember(), recall(), and ingest_text()."""

    def test_remember_stores_fact(self):
        agent = create_mock_agent()
        result = agent.remember("Abdul created this project")
        assert "Remembered" in result
        agent._memory.store.assert_called_once()

    def test_remember_with_importance(self):
        agent = create_mock_agent()
        agent.remember("Critical fact", importance=0.95)
        call_args = agent._memory.store.call_args
        assert call_args[1].get("importance") == 0.95

    def test_recall_returns_list(self):
        agent = create_mock_agent()
        agent._memory.retrieve.return_value = [
            RetrievalResult(
                id="m1", content="Abdul is the creator",
                collection="semantic", metadata={"source": "user"},
                relevance_score=0.9, distance=0.2,
            )
        ]
        results = agent.recall("Who created this?")
        assert len(results) == 1
        assert results[0]["content"] == "Abdul is the creator"
        assert results[0]["relevance"] == 0.9

    def test_recall_empty(self):
        agent = create_mock_agent()
        results = agent.recall("Unknown topic")
        assert results == []

    def test_ingest_text(self):
        agent = create_mock_agent()
        agent._continual.learn_from_web.return_value = LearningEvent(
            event_type="web_ingest", content="Ingested",
            extracted_facts=["fact1", "fact2"], source="doc",
            timestamp="2026-01-01T00:00:00", importance=0.4,
        )
        result = agent.ingest_text("Large text document...", source="readme.md")
        assert "readme.md" in result
        assert "2 facts" in result


# ────────────────────────────────────────────────────────
#  Skill Learning Tests
# ────────────────────────────────────────────────────────

class TestSmartAgentLearnSkill:
    """Tests for learn_skill()."""

    def test_learn_skill_returns_confirmation(self):
        agent = create_mock_agent()
        result = agent.learn_skill(
            name="deploy_docker",
            description="Deploy with Docker",
            steps=["build", "run", "check"],
        )
        assert "deploy_docker" in result
        assert "3 steps" in result

    def test_learn_skill_calls_continual(self):
        agent = create_mock_agent()
        agent.learn_skill("test", "Test skill", ["step 1"])
        agent._continual.learn_skill.assert_called_once()


# ────────────────────────────────────────────────────────
#  Session Management Tests
# ────────────────────────────────────────────────────────

class TestSmartAgentSession:
    """Tests for session management."""

    def test_new_session_clears_conversation(self):
        agent = create_mock_agent()
        agent._conversation = [{"role": "user", "content": "old msg"}]
        result = agent.new_session()
        assert agent._conversation == []
        assert "Memory is persistent" in result

    def test_get_conversation(self):
        agent = create_mock_agent()
        agent._conversation = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        conv = agent.get_conversation()
        assert len(conv) == 2
        # Should return a copy
        conv.append({"role": "user", "content": "extra"})
        assert len(agent._conversation) == 2


# ────────────────────────────────────────────────────────
#  Status Tests
# ────────────────────────────────────────────────────────

class TestSmartAgentStatus:
    """Tests for status() and status_text()."""

    def test_status_returns_agent_status(self):
        agent = create_mock_agent()
        status = agent.status()
        assert isinstance(status, AgentStatus)
        assert status.active_model == "phi3:mini"

    def test_status_includes_memory_stats(self):
        agent = create_mock_agent()
        agent._memory.get_stats.return_value = VectorStoreStats(
            total_entries=100,
            entries_by_collection={"semantic": 50, "episodic": 30, "procedural": 20, "prototypes": 0, "web_knowledge": 0},
            storage_path="/tmp",
            embedding_model="mock",
            embedding_dimensions=384,
        )
        status = agent.status()
        assert status.total_memories == 100

    def test_status_text_is_string(self):
        agent = create_mock_agent()
        text = agent.status_text()
        assert isinstance(text, str)
        assert "SmartAgent" in text

    def test_status_text_contains_key_info(self):
        agent = create_mock_agent()
        text = agent.status_text()
        assert "Model" in text
        assert "Memories" in text

    def test_avg_latency_calculated(self):
        agent = create_mock_agent()
        agent._total_requests = 4
        agent._total_latency = 800.0
        status = agent.status()
        assert status.avg_latency_ms == 200.0

    def test_avg_latency_zero_requests(self):
        agent = create_mock_agent()
        status = agent.status()
        assert status.avg_latency_ms == 0


# ────────────────────────────────────────────────────────
#  From Env Tests
# ────────────────────────────────────────────────────────

class TestSmartAgentFromEnv:
    """Tests for the from_env() factory method."""

    def test_from_env_creates_agent(self):
        with patch.object(SmartAgent, "__init__", return_value=None):
            agent = SmartAgent.from_env(env_path="nonexistent.env")
            assert agent is not None
