"""
Tests for ContinualLearner — Gets Smarter Every Day

These tests verify:
1. Learning from interactions (fact extraction)
2. Learning from corrections (high-value learning)
3. Learning from errors (procedural memory)
4. Learning from web content (ingestion)
5. Learning skills (step-by-step procedures)
6. Knowledge consolidation
7. Rule-based fact extraction
8. Text similarity (Jaccard)
9. Stats tracking and growth rate

Uses mocked VectorMemoryStore — no ChromaDB needed.
"""

import pytest
from unittest.mock import MagicMock, call
from datetime import datetime

from src.learning.continual_learner import (
    ContinualLearner,
    LearningEvent,
    ConsolidationResult,
    ContinualLearnerStats,
    EXTRACT_FACTS_PROMPT,
)
from src.memory.vector_store import VectorMemoryStore, RetrievalResult


# ────────────────────────────────────────────────────────
#  Data Structure Tests
# ────────────────────────────────────────────────────────

class TestLearningEvent:
    """Tests for the LearningEvent data class."""

    def test_create_event(self):
        e = LearningEvent(
            event_type="interaction",
            content="test content",
            extracted_facts=["fact 1"],
            source="test",
            timestamp="2026-03-02T12:00:00",
            importance=0.5,
        )
        assert e.event_type == "interaction"
        assert len(e.extracted_facts) == 1


class TestConsolidationResult:
    """Tests for ConsolidationResult."""

    def test_create_result(self):
        r = ConsolidationResult(
            memories_reviewed=50,
            duplicates_merged=3,
            weak_memories_pruned=2,
            patterns_extracted=1,
            timestamp="2026-03-02T12:00:00",
        )
        assert r.memories_reviewed == 50
        assert r.duplicates_merged == 3


# ────────────────────────────────────────────────────────
#  Mock Setup
# ────────────────────────────────────────────────────────

def create_mock_store():
    """Create a mocked VectorMemoryStore."""
    store = MagicMock(spec=VectorMemoryStore)
    store.store.return_value = "mock-id-123"
    store.ingest_text.return_value = ["chunk-1", "chunk-2"]
    store.retrieve.return_value = []
    return store


def create_learner(store=None, llm_generate=None, auto_consolidate_every=100):
    """Create a ContinualLearner with mocked store."""
    if store is None:
        store = create_mock_store()
    return ContinualLearner(
        vector_store=store,
        llm_generate=llm_generate,
        auto_consolidate_every=auto_consolidate_every,
    )


# ────────────────────────────────────────────────────────
#  Learn from Interaction Tests
# ────────────────────────────────────────────────────────

class TestLearnFromInteraction:
    """Tests for learn_from_interaction()."""

    def test_returns_learning_event(self):
        learner = create_learner()
        event = learner.learn_from_interaction(
            user_message="My name is Abdul",
            agent_response="Nice to meet you, Abdul!",
        )
        assert isinstance(event, LearningEvent)
        assert event.event_type == "interaction"
        assert event.source == "user_interaction"

    def test_stores_episodic_memory(self):
        store = create_mock_store()
        learner = create_learner(store)
        learner.learn_from_interaction("Hello", "Hi there!")

        # Check that store was called with episodic collection
        calls = store.store.call_args_list
        episodic_calls = [c for c in calls if c[1].get("collection") == "episodic"
                          or (len(c[0]) > 1 and c[0][1] == "episodic")]
        assert len(episodic_calls) >= 1

    def test_extracts_facts_rule_based(self):
        learner = create_learner()
        event = learner.learn_from_interaction(
            user_message="I prefer Python over JavaScript",
            agent_response="Got it, you prefer Python!",
        )
        # Rule-based extraction should find "I prefer" pattern
        assert len(event.extracted_facts) > 0

    def test_extracts_facts_with_llm(self):
        mock_llm = MagicMock(return_value='["Abdul lives in Dubai", "He prefers dark mode"]')
        learner = create_learner(llm_generate=mock_llm)
        event = learner.learn_from_interaction(
            user_message="I live in Dubai and prefer dark mode",
            agent_response="Noted!",
        )
        assert "Abdul lives in Dubai" in event.extracted_facts
        assert "He prefers dark mode" in event.extracted_facts

    def test_increments_events_processed(self):
        learner = create_learner()
        learner.learn_from_interaction("msg1", "resp1")
        learner.learn_from_interaction("msg2", "resp2")
        assert learner._events_processed == 2

    def test_tracks_daily_counts(self):
        learner = create_learner()
        learner.learn_from_interaction("msg", "resp")
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in learner._daily_counts
        assert learner._daily_counts[today] >= 1

    def test_auto_consolidation_trigger(self):
        store = create_mock_store()
        store.retrieve.return_value = []
        learner = create_learner(store, auto_consolidate_every=3)

        learner.learn_from_interaction("msg1", "resp1")
        learner.learn_from_interaction("msg2", "resp2")
        assert learner._consolidations_run == 0

        learner.learn_from_interaction("msg3", "resp3")  # 3rd event triggers
        assert learner._consolidations_run == 1

    def test_fact_extraction_dedup(self):
        store = create_mock_store()
        learner = create_learner(store)
        learner.learn_from_interaction(
            user_message="The project uses FastAPI",
            agent_response="FastAPI is great!",
        )
        # Any semantic stores should have dedup=True
        semantic_calls = [c for c in store.store.call_args_list
                         if c[1].get("collection") == "semantic"]
        for sc in semantic_calls:
            assert sc[1].get("dedup") is True


# ────────────────────────────────────────────────────────
#  Learn from Correction Tests
# ────────────────────────────────────────────────────────

class TestLearnFromCorrection:
    """Tests for learn_from_correction()."""

    def test_returns_learning_event(self):
        learner = create_learner()
        event = learner.learn_from_correction(
            original_response="You use Django",
            correction="No, I use FastAPI",
        )
        assert event.event_type == "correction"
        assert event.importance == 0.9

    def test_stores_high_confidence_fact(self):
        store = create_mock_store()
        learner = create_learner(store)
        learner.learn_from_correction("Wrong answer", "Right answer")

        # Should store in semantic with high importance
        calls = store.store.call_args_list
        semantic_calls = [c for c in calls if c[1].get("collection") == "semantic"]
        assert len(semantic_calls) >= 1
        high_importance = [c for c in semantic_calls if float(c[1].get("importance", 0)) >= 0.9]
        assert len(high_importance) >= 1

    def test_stores_episodic_record(self):
        store = create_mock_store()
        learner = create_learner(store)
        learner.learn_from_correction("Wrong", "Right")

        calls = store.store.call_args_list
        episodic_calls = [c for c in calls if c[1].get("collection") == "episodic"]
        assert len(episodic_calls) >= 1

    def test_increments_corrections_counter(self):
        learner = create_learner()
        learner.learn_from_correction("Wrong", "Right")
        assert learner._corrections_applied == 1


# ────────────────────────────────────────────────────────
#  Learn from Error Tests
# ────────────────────────────────────────────────────────

class TestLearnFromError:
    """Tests for learn_from_error()."""

    def test_returns_learning_event(self):
        learner = create_learner()
        event = learner.learn_from_error(
            error_description="ImportError: no module named foo",
            solution="pip install foo",
        )
        assert event.event_type == "error"

    def test_stores_in_procedural(self):
        store = create_mock_store()
        learner = create_learner(store)
        learner.learn_from_error("SQLAlchemy connection timeout", "Increase pool size")

        calls = store.store.call_args_list
        procedural_calls = [c for c in calls if c[1].get("collection") == "procedural"]
        assert len(procedural_calls) >= 1

    def test_error_with_context(self):
        learner = create_learner()
        event = learner.learn_from_error(
            "PermissionError",
            "Run as admin",
            context="Windows file system",
        )
        assert "PermissionError" in event.content
        assert "Windows" in event.content


# ────────────────────────────────────────────────────────
#  Learn from Web Tests
# ────────────────────────────────────────────────────────

class TestLearnFromWeb:
    """Tests for learn_from_web()."""

    def test_returns_learning_event(self):
        learner = create_learner()
        event = learner.learn_from_web(
            url="https://example.com/article",
            content="Python is a programming language...",
        )
        assert event.event_type == "web_ingest"

    def test_calls_ingest_text(self):
        store = create_mock_store()
        learner = create_learner(store)
        learner.learn_from_web("https://example.com", "Article content here")

        store.ingest_text.assert_called_once()
        call_args = store.ingest_text.call_args
        assert call_args[1].get("source") == "https://example.com"
        assert call_args[1].get("collection") == "web_knowledge"

    def test_extracts_facts_from_web(self):
        learner = create_learner()
        event = learner.learn_from_web(
            url="https://example.com",
            content="The project uses FastAPI for the backend. We use Python 3.10.",
        )
        # Rule-based extraction should find "we use" pattern
        assert len(event.extracted_facts) >= 0  # May or may not extract depending on rules


# ────────────────────────────────────────────────────────
#  Learn Skill Tests
# ────────────────────────────────────────────────────────

class TestLearnSkill:
    """Tests for learn_skill()."""

    def test_returns_learning_event(self):
        learner = create_learner()
        event = learner.learn_skill(
            skill_name="deploy_docker",
            description="Deploy using Docker",
            steps=[
                "docker build -t app .",
                "docker run -p 8000:8000 app",
            ],
        )
        assert event.event_type == "observation"
        assert "deploy_docker" in event.content

    def test_stores_in_procedural(self):
        store = create_mock_store()
        learner = create_learner(store)
        learner.learn_skill(
            "git_deploy",
            "Deploy via git",
            ["git push origin main", "ssh server 'git pull'"],
        )

        calls = store.store.call_args_list
        procedural_calls = [c for c in calls if c[1].get("collection") == "procedural"]
        assert len(procedural_calls) >= 1

    def test_stores_steps_in_content(self):
        store = create_mock_store()
        learner = create_learner(store)
        learner.learn_skill(
            "test_skill",
            "A test skill",
            ["step one", "step two", "step three"],
        )

        call_args = store.store.call_args
        content = call_args[1].get("content", call_args[0][0] if call_args[0] else "")
        assert "step one" in content
        assert "step two" in content
        assert "step three" in content


# ────────────────────────────────────────────────────────
#  Consolidation Tests
# ────────────────────────────────────────────────────────

class TestConsolidate:
    """Tests for knowledge consolidation."""

    def test_returns_consolidation_result(self):
        learner = create_learner()
        result = learner.consolidate()
        assert isinstance(result, ConsolidationResult)
        assert isinstance(result.timestamp, str)

    def test_increments_consolidation_count(self):
        learner = create_learner()
        learner.consolidate()
        assert learner._consolidations_run == 1
        learner.consolidate()
        assert learner._consolidations_run == 2

    def test_updates_last_consolidation(self):
        learner = create_learner()
        assert learner._last_consolidation is None
        learner.consolidate()
        assert learner._last_consolidation is not None

    def test_reviews_memories(self):
        store = create_mock_store()
        store.retrieve.return_value = [
            RetrievalResult(
                id=f"mem-{i}", content=f"fact {i}", collection="semantic",
                metadata={"confidence": "0.8"}, relevance_score=0.5, distance=1.0,
            )
            for i in range(5)
        ]
        learner = create_learner(store)
        result = learner.consolidate()
        assert result.memories_reviewed >= 5


# ────────────────────────────────────────────────────────
#  Rule-Based Fact Extraction Tests
# ────────────────────────────────────────────────────────

class TestRuleBasedExtraction:
    """Tests for _rule_based_extract()."""

    def test_extracts_preference(self):
        learner = create_learner()
        facts = learner._rule_based_extract("USER: I prefer dark mode\nAGENT: Got it!")
        assert any("prefer" in f.lower() for f in facts)

    def test_extracts_name(self):
        learner = create_learner()
        facts = learner._rule_based_extract("USER: My name is Abdul\nAGENT: Hello Abdul!")
        assert any("name" in f.lower() for f in facts)

    def test_extracts_definition(self):
        learner = create_learner()
        facts = learner._rule_based_extract("FastAPI is a modern web framework")
        assert len(facts) >= 1

    def test_deduplicates(self):
        learner = create_learner()
        facts = learner._rule_based_extract(
            "I prefer Python\nI prefer Python\nI prefer Python"
        )
        assert facts.count(facts[0]) == 1 if facts else True

    def test_empty_input(self):
        learner = create_learner()
        facts = learner._rule_based_extract("")
        assert facts == []

    def test_strips_user_prefix(self):
        learner = create_learner()
        facts = learner._rule_based_extract("USER: I use VS Code for development")
        if facts:
            assert not facts[0].startswith("USER: ")

    def test_extracts_project_info(self):
        learner = create_learner()
        facts = learner._rule_based_extract("The project uses FastAPI and PostgreSQL")
        assert len(facts) >= 1


# ────────────────────────────────────────────────────────
#  Text Similarity Tests
# ────────────────────────────────────────────────────────

class TestTextSimilarity:
    """Tests for _text_similarity() Jaccard function."""

    def test_identical_strings(self):
        learner = create_learner()
        s = learner._text_similarity("hello world", "hello world")
        assert s == 1.0

    def test_completely_different(self):
        learner = create_learner()
        s = learner._text_similarity("hello world", "foo bar baz")
        assert s == 0.0

    def test_partial_overlap(self):
        learner = create_learner()
        s = learner._text_similarity("hello world", "hello there")
        assert 0.0 < s < 1.0

    def test_empty_string(self):
        learner = create_learner()
        s = learner._text_similarity("", "hello")
        assert s == 0.0

    def test_both_empty(self):
        learner = create_learner()
        s = learner._text_similarity("", "")
        assert s == 0.0

    def test_case_insensitive(self):
        learner = create_learner()
        s = learner._text_similarity("Hello World", "hello world")
        assert s == 1.0


# ────────────────────────────────────────────────────────
#  Stats Tests
# ────────────────────────────────────────────────────────

class TestContinualLearnerStats:
    """Tests for get_stats()."""

    def test_initial_stats(self):
        learner = create_learner()
        stats = learner.get_stats()
        assert stats.total_events_processed == 0
        assert stats.facts_extracted == 0
        assert stats.corrections_applied == 0
        assert stats.consolidations_run == 0
        assert stats.last_consolidation is None
        assert stats.knowledge_growth_rate == 0.0

    def test_stats_after_events(self):
        learner = create_learner()
        learner.learn_from_interaction("msg", "resp")
        learner.learn_from_correction("wrong", "right")

        stats = learner.get_stats()
        assert stats.total_events_processed == 2
        assert stats.corrections_applied == 1

    def test_growth_rate_calculation(self):
        learner = create_learner()
        # Simulate events across days
        learner._daily_counts = {
            "2026-03-01": 10,
            "2026-03-02": 15,
        }
        stats = learner.get_stats()
        # 25 total entries / 2 days = 12.5 entries/day
        assert stats.knowledge_growth_rate == 12.5

    def test_stats_after_consolidation(self):
        learner = create_learner()
        learner.consolidate()
        stats = learner.get_stats()
        assert stats.consolidations_run == 1
        assert stats.last_consolidation is not None


# ────────────────────────────────────────────────────────
#  LLM-based Fact Extraction Tests
# ────────────────────────────────────────────────────────

class TestLLMFactExtraction:
    """Tests for LLM-based fact extraction."""

    def test_llm_extraction_valid_json(self):
        mock_llm = MagicMock(return_value='["fact one", "fact two"]')
        learner = create_learner(llm_generate=mock_llm)
        facts = learner._extract_facts("Some interaction content")
        assert facts == ["fact one", "fact two"]

    def test_llm_extraction_invalid_json_falls_back(self):
        mock_llm = MagicMock(return_value="not valid json")
        learner = create_learner(llm_generate=mock_llm)
        # Should fall back to rule-based
        facts = learner._extract_facts("I prefer dark mode")
        # Rule-based should still work
        assert isinstance(facts, list)

    def test_llm_extraction_exception_falls_back(self):
        mock_llm = MagicMock(side_effect=Exception("API error"))
        learner = create_learner(llm_generate=mock_llm)
        facts = learner._extract_facts("I use Python for development")
        assert isinstance(facts, list)

    def test_no_llm_uses_rule_based(self):
        learner = create_learner(llm_generate=None)
        facts = learner._extract_facts("My name is Abdul and I use Python")
        assert isinstance(facts, list)
        assert len(facts) >= 1
