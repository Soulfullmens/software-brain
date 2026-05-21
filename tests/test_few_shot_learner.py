"""
Tests for FewShotLearner — Learn Once, Recognize Forever

These tests verify:
1. Prototype creation from 1-5 examples
2. Recognition via embedding similarity
3. Category-based filtering
4. Example addition to existing prototypes
5. Prototype management (list, get, forget)
6. Stats tracking

Uses mocked VectorMemoryStore to avoid ChromaDB dependency.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.learning.few_shot_learner import (
    FewShotLearner,
    Prototype,
    RecognitionResult,
    LearnerStats,
)
from src.memory.vector_store import VectorMemoryStore, RetrievalResult


# ────────────────────────────────────────────────────────
#  Data Structure Tests
# ────────────────────────────────────────────────────────

class TestPrototype:
    """Tests for the Prototype data class."""

    def test_create_prototype(self):
        p = Prototype(
            name="kitkat",
            category="food",
            description="Chocolate wafer bar",
            examples=["red wrapper"],
            memory_id="abc-123",
            created_at=datetime.now().isoformat(),
        )
        assert p.name == "kitkat"
        assert p.category == "food"
        assert p.recognition_count == 0
        assert p.last_recognized is None


class TestRecognitionResult:
    """Tests for the RecognitionResult data class."""

    def test_no_match(self):
        r = RecognitionResult(
            matched=False,
            prototype_name=None,
            confidence=0.0,
            category=None,
            all_matches=[],
            input_text="test",
        )
        assert r.matched is False
        assert r.prototype_name is None

    def test_match(self):
        r = RecognitionResult(
            matched=True,
            prototype_name="spam",
            confidence=0.82,
            category="email",
            all_matches=[{"name": "spam", "confidence": 0.82}],
            input_text="buy now",
        )
        assert r.matched is True
        assert r.confidence == 0.82


# ────────────────────────────────────────────────────────
#  Mock Store
# ────────────────────────────────────────────────────────

def create_mock_vector_store():
    """Create a mocked VectorMemoryStore."""
    store = MagicMock(spec=VectorMemoryStore)
    # Default: no existing prototypes
    store.retrieve.return_value = []
    store.store_prototype.return_value = "mock-proto-id"
    store.match_prototype.return_value = []
    store.delete.return_value = True
    return store


# ────────────────────────────────────────────────────────
#  FewShotLearner Tests
# ────────────────────────────────────────────────────────

class TestFewShotLearnerInit:
    """Tests for initialization."""

    def test_init_empty_store(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store)
        assert learner._total_recognitions == 0
        assert len(learner._prototypes) == 0

    def test_init_loads_existing(self):
        store = create_mock_vector_store()
        store.retrieve.return_value = [
            RetrievalResult(
                id="existing-1",
                content="PROTOTYPE: old_concept",
                collection="prototypes",
                metadata={"prototype_name": "old_concept", "category": "general", "created_at": "2026-01-01"},
                relevance_score=0.5,
                distance=1.0,
            )
        ]
        learner = FewShotLearner(store)
        assert "old_concept" in learner._prototypes

    def test_custom_thresholds(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store, recognition_threshold=0.7, strong_match_threshold=0.9)
        assert learner._recognition_threshold == 0.7
        assert learner._strong_match_threshold == 0.9


class TestFewShotLearnerLearn:
    """Tests for the learn() method — one-shot/few-shot learning."""

    def test_learn_basic(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store)

        proto = learner.learn(
            name="kitkat",
            description="Chocolate wafer bar by Nestle",
            examples=["red wrapper chocolate"],
            category="food",
        )

        assert proto.name == "kitkat"
        assert proto.category == "food"
        assert "kitkat" in learner._prototypes
        store.store_prototype.assert_called_once()

    def test_learn_without_examples(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store)

        proto = learner.learn(
            name="abstract_concept",
            description="A concept with no examples",
        )
        assert proto.examples == []

    def test_learn_multiple_prototypes(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store)

        learner.learn("spam", "Junk email", ["Buy now!"], "email")
        learner.learn("ham", "Normal email", ["Meeting at 3pm"], "email")

        assert len(learner._prototypes) == 2
        assert "spam" in learner._prototypes
        assert "ham" in learner._prototypes

    def test_learn_with_metadata(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store)

        learner.learn(
            name="test",
            description="Test prototype",
            metadata={"author": "Abdul"},
        )
        call_args = store.store_prototype.call_args
        assert call_args[1].get("name") == "test" or call_args[0][0] == "test"


class TestFewShotLearnerRecognize:
    """Tests for the recognize() method."""

    def test_recognize_no_match(self):
        store = create_mock_vector_store()
        store.match_prototype.return_value = []  # no matches
        learner = FewShotLearner(store)

        result = learner.recognize("random text")
        assert result.matched is False
        assert result.prototype_name is None
        assert result.confidence == 0.0
        assert result.all_matches == []

    def test_recognize_match(self):
        store = create_mock_vector_store()
        store.match_prototype.return_value = [
            RetrievalResult(
                id="proto-1",
                content="PROTOTYPE: spam_email",
                collection="prototypes",
                metadata={"prototype_name": "spam_email", "category": "email"},
                relevance_score=0.85,
                distance=0.3,
            )
        ]
        learner = FewShotLearner(store)
        # Add to internal cache so recognition count updates
        learner._prototypes["spam_email"] = Prototype(
            name="spam_email", category="email", description="Spam",
            examples=[], memory_id="proto-1", created_at="2026-01-01",
        )

        result = learner.recognize("Free money! Click here!")
        assert result.matched is True
        assert result.prototype_name == "spam_email"
        assert result.confidence == 0.85
        assert learner._prototypes["spam_email"].recognition_count == 1

    def test_recognize_with_category_filter(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store)

        learner.recognize("test input", category="food")
        store.match_prototype.assert_called_once()
        call_args = store.match_prototype.call_args
        assert call_args[1].get("category") == "food"

    def test_recognize_custom_threshold(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store)

        learner.recognize("test input", threshold=0.9)
        call_args = store.match_prototype.call_args
        assert call_args[1].get("threshold") == 0.9

    def test_recognize_increments_total(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store)

        learner.recognize("input 1")
        learner.recognize("input 2")
        assert learner._total_recognitions == 2

    def test_recognize_multiple_matches_best_first(self):
        store = create_mock_vector_store()
        store.match_prototype.return_value = [
            RetrievalResult(
                id="proto-1", content="PROTOTYPE: spam",
                collection="prototypes",
                metadata={"prototype_name": "spam", "category": "email"},
                relevance_score=0.85, distance=0.3,
            ),
            RetrievalResult(
                id="proto-2", content="PROTOTYPE: phishing",
                collection="prototypes",
                metadata={"prototype_name": "phishing", "category": "email"},
                relevance_score=0.72, distance=0.56,
            ),
        ]
        learner = FewShotLearner(store)

        result = learner.recognize("suspicious email")
        assert result.matched is True
        assert result.prototype_name == "spam"  # highest confidence
        assert len(result.all_matches) == 2


class TestFewShotLearnerAddExample:
    """Tests for adding examples to existing prototypes."""

    def test_add_example_success(self):
        store = create_mock_vector_store()
        store.store_prototype.return_value = "new-proto-id"
        learner = FewShotLearner(store)

        learner.learn("kitkat", "Chocolate bar", ["red wrapper"], "food")
        result = learner.add_example("kitkat", "crispy layers")
        assert result is True
        assert "crispy layers" in learner._prototypes["kitkat"].examples

    def test_add_example_nonexistent(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store)

        result = learner.add_example("nonexistent", "example")
        assert result is False


class TestFewShotLearnerManagement:
    """Tests for prototype management."""

    def test_list_prototypes_all(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store)
        learner.learn("spam", "Spam email", category="email")
        learner.learn("kitkat", "Chocolate", category="food")

        protos = learner.list_prototypes()
        assert len(protos) == 2

    def test_list_prototypes_by_category(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store)
        learner.learn("spam", "Spam email", category="email")
        learner.learn("kitkat", "Chocolate", category="food")

        protos = learner.list_prototypes(category="food")
        assert len(protos) == 1
        assert protos[0].name == "kitkat"

    def test_get_prototype(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store)
        learner.learn("kitkat", "Chocolate")

        proto = learner.get_prototype("kitkat")
        assert proto is not None
        assert proto.name == "kitkat"

    def test_get_nonexistent_prototype(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store)
        assert learner.get_prototype("nonexistent") is None

    def test_forget_prototype(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store)
        learner.learn("kitkat", "Chocolate")

        result = learner.forget("kitkat")
        assert result is True
        assert "kitkat" not in learner._prototypes
        store.delete.assert_called_once()

    def test_forget_nonexistent(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store)
        result = learner.forget("nonexistent")
        assert result is False


class TestFewShotLearnerStats:
    """Tests for stats tracking."""

    def test_empty_stats(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store)

        stats = learner.get_stats()
        assert stats.total_prototypes == 0
        assert stats.total_recognitions == 0
        assert stats.most_recognized is None
        assert stats.categories == {}

    def test_stats_after_learning(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store)
        learner.learn("spam", "Spam", category="email")
        learner.learn("ham", "Normal", category="email")
        learner.learn("kitkat", "Chocolate", category="food")

        stats = learner.get_stats()
        assert stats.total_prototypes == 3
        assert stats.categories["email"] == 2
        assert stats.categories["food"] == 1

    def test_stats_most_recognized(self):
        store = create_mock_vector_store()
        learner = FewShotLearner(store)
        learner.learn("spam", "Spam", category="email")
        # Simulate recognitions
        learner._prototypes["spam"].recognition_count = 5

        stats = learner.get_stats()
        assert stats.most_recognized == "spam"
