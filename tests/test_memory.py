"""
Tests for Layer 3: Memory System

These tests verify:
1. Decay works correctly (exponential decay formula)
2. Reinforcement works correctly (bounded increase)
3. Contradiction works correctly (confidence drops, count increments)
4. Forget works correctly (below threshold = inactive)

If these don't pass, DO NOT CONTINUE.
"""

import pytest
import tempfile
import math
import gc
import shutil
import os
from pathlib import Path
from datetime import datetime, timedelta

from src.memory.short_term import ShortTermMemory, STMEntry
from src.memory.episodic import EpisodicMemory, Episode, EPISODIC_DECAY_RATE, INACTIVE_THRESHOLD
from src.memory.semantic import SemanticMemory, Fact, SEMANTIC_DECAY_RATE
from src.memory.meta import MetaMemory, Unknown
from src.memory.manager import MemoryManager


@pytest.fixture
def temp_dir():
    """Create a temporary directory that handles Windows file locking."""
    tmpdir = tempfile.mkdtemp()
    yield Path(tmpdir)
    # Cleanup: force garbage collection to close SQLite connections
    gc.collect()
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass  # Ignore cleanup errors on Windows


class TestShortTermMemory:
    """Tests for in-memory short-term memory."""
    
    def test_add_and_retrieve(self):
        """Can add and retrieve entries."""
        stm = ShortTermMemory(max_size=10)
        stm.add("First message")
        stm.add("Second message")
        
        recent = stm.get_recent(5)
        assert len(recent) == 2
        assert recent[0].content == "First message"
        assert recent[1].content == "Second message"
    
    def test_max_size_enforced(self):
        """Buffer doesn't exceed max size."""
        stm = ShortTermMemory(max_size=3)
        for i in range(5):
            stm.add(f"Message {i}")
        
        # Should only have last 3
        assert len(stm) == 3
        entries = stm.get_all()
        assert entries[0].content == "Message 2"
        assert entries[2].content == "Message 4"
    
    def test_clear(self):
        """Clear empties everything."""
        stm = ShortTermMemory()
        stm.add("Test")
        stm.set_working_fact("key", "value")
        stm.set_attention(["topic1"])
        
        stm.clear()
        
        assert len(stm) == 0
        assert stm.get_working_fact("key") is None
        assert stm.get_attention() == []
    
    def test_working_facts(self):
        """Working facts are stored and retrieved."""
        stm = ShortTermMemory()
        stm.set_working_fact("current_file", "identity.py")
        
        assert stm.get_working_fact("current_file") == "identity.py"
        assert stm.get_working_fact("nonexistent") is None


class TestEpisodeDecay:
    """Tests for episodic memory decay - CRITICAL."""
    
    def test_decay_formula_correct(self):
        """Decay follows exponential formula: c(t) = c₀ × e^(−λΔt)"""
        episode = Episode.create(
            content="Test event",
            importance=0.8,
            source="test",
            confidence=1.0,
            decay_rate=0.1,  # λ = 0.1 per day
        )
        
        # Simulate 5 days passing
        future = datetime.now() + timedelta(days=5)
        episode.decay(future)
        
        # Expected: 1.0 * e^(-0.1 * 5) = e^(-0.5) ≈ 0.6065
        expected = math.exp(-0.1 * 5)
        assert episode.confidence == pytest.approx(expected, rel=0.01)
    
    def test_decay_with_default_rate(self):
        """Episodic decay rate is slow (λ = 0.01)."""
        episode = Episode.create(
            content="Test",
            importance=0.5,
            source="test",
        )
        initial = episode.confidence
        
        # After 30 days
        future = datetime.now() + timedelta(days=30)
        episode.decay(future)
        
        # e^(-0.01 * 30) ≈ 0.74
        expected = initial * math.exp(-EPISODIC_DECAY_RATE * 30)
        assert episode.confidence == pytest.approx(expected, rel=0.01)
    
    def test_decay_all_in_storage(self):
        """decay_all() applies decay to all stored episodes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            em = EpisodicMemory(db_path)
            
            # Store episodes with different confidences
            e1 = Episode.create("Event 1", 0.5, "test", confidence=0.9)
            e2 = Episode.create("Event 2", 0.5, "test", confidence=0.5)
            em.store(e1)
            em.store(e2)
            
            # Decay after 50 days (should push e2 below threshold)
            future = datetime.now() + timedelta(days=50)
            became_inactive = em.decay_all(future)
            
            # e2 should become inactive (0.5 * e^(-0.01*50) ≈ 0.30)
            # But actually 0.5 * e^(-0.5) ≈ 0.303, still above 0.2
            # Let's check the actual values
            e1_after = em.get(e1.id)
            e2_after = em.get(e2.id)
            
            assert e1_after.confidence < 0.9
            assert e2_after.confidence < 0.5


class TestEpisodeReinforcement:
    """Tests for episodic memory reinforcement - CRITICAL."""
    
    def test_reinforcement_formula_correct(self):
        """Reinforcement: new = old + α(1 - old)"""
        episode = Episode.create(
            content="Test",
            importance=0.5,
            source="test",
            confidence=0.6,
        )
        
        # Reinforce with α = 0.2
        episode.reinforce(strength=0.2)
        
        # Expected: 0.6 + 0.2*(1-0.6) = 0.6 + 0.08 = 0.68
        assert episode.confidence == pytest.approx(0.68, rel=0.01)
    
    def test_reinforcement_never_exceeds_one(self):
        """Reinforcement can never push confidence above 1.0."""
        episode = Episode.create(
            content="Test",
            importance=0.5,
            source="test",
            confidence=0.95,
        )
        
        # Massive reinforcement
        for _ in range(10):
            episode.reinforce(strength=0.3)
        
        assert episode.confidence < 1.0
    
    def test_reinforcement_updates_timestamp(self):
        """Reinforcement updates last_reinforced."""
        episode = Episode.create(
            content="Test",
            importance=0.5,
            source="test",
        )
        old_reinforced = episode.last_reinforced
        
        # Small delay to ensure different timestamp
        import time
        time.sleep(0.01)
        
        episode.reinforce()
        
        assert episode.last_reinforced > old_reinforced


class TestEpisodeContradiction:
    """Tests for episodic memory contradiction - CRITICAL."""
    
    def test_contradiction_reduces_confidence(self):
        """Contradiction reduces confidence."""
        episode = Episode.create(
            content="Test",
            importance=0.5,
            source="test",
            confidence=0.8,
        )
        
        episode.contradict(penalty=0.15)
        
        assert episode.confidence == pytest.approx(0.65, rel=0.01)
    
    def test_contradiction_increments_count(self):
        """Contradiction increments contradiction_count."""
        episode = Episode.create(
            content="Test",
            importance=0.5,
            source="test",
        )
        
        assert episode.contradiction_count == 0
        episode.contradict()
        assert episode.contradiction_count == 1
        episode.contradict()
        assert episode.contradiction_count == 2
    
    def test_contradiction_floors_at_zero(self):
        """Confidence can't go below zero."""
        episode = Episode.create(
            content="Test",
            importance=0.5,
            source="test",
            confidence=0.1,
        )
        
        episode.contradict(penalty=0.5)  # Would be -0.4
        
        assert episode.confidence == 0.0


class TestEpisodeForget:
    """Tests for memory becoming inactive - CRITICAL."""
    
    def test_below_threshold_inactive(self):
        """Memory below threshold is inactive."""
        episode = Episode.create(
            content="Test",
            importance=0.5,
            source="test",
            confidence=0.15,  # Below 0.2 threshold
        )
        
        assert not episode.is_active()
    
    def test_at_threshold_active(self):
        """Memory at exactly threshold is active."""
        episode = Episode.create(
            content="Test",
            importance=0.5,
            source="test",
            confidence=INACTIVE_THRESHOLD,
        )
        
        assert episode.is_active()
    
    def test_decay_causes_inactive(self):
        """Decay over time can cause memory to become inactive."""
        episode = Episode.create(
            content="Test",
            importance=0.5,
            source="test",
            confidence=0.25,  # Just above threshold
            decay_rate=0.1,   # Fast decay for testing
        )
        
        assert episode.is_active()
        
        # After 30 days: 0.25 * e^(-0.1 * 30) = 0.25 * e^(-3) ≈ 0.012
        future = datetime.now() + timedelta(days=30)
        episode.decay(future)
        
        assert not episode.is_active()


class TestSemanticMemory:
    """Tests for semantic memory (believed facts)."""
    
    def test_fact_creation(self):
        """Facts are created with correct defaults."""
        fact = Fact.create(
            statement="Owner prefers dark mode",
            source="observation",
        )
        
        assert fact.confidence == 0.7  # Default is cautious
        assert fact.decay_rate == SEMANTIC_DECAY_RATE
        assert fact.contradiction_count == 0
    
    def test_semantic_decays_faster_than_episodic(self):
        """Semantic memory decays faster (λ=0.05 vs λ=0.01)."""
        assert SEMANTIC_DECAY_RATE > EPISODIC_DECAY_RATE
    
    def test_fact_reliability(self):
        """Reliability check works correctly."""
        reliable = Fact.create("Test", "source", confidence=0.8)
        assert reliable.is_reliable()
        
        unreliable_confidence = Fact.create("Test", "source", confidence=0.5)
        assert not unreliable_confidence.is_reliable()
        
        unreliable_contradicted = Fact.create("Test", "source", confidence=0.8)
        unreliable_contradicted.contradiction_count = 5
        assert not unreliable_contradicted.is_reliable()


class TestMetaMemory:
    """Tests for meta-memory (unknowns)."""
    
    def test_unknown_creation(self):
        """Unknowns are created correctly."""
        unknown = Unknown.create(
            question="What is the owner's timezone?",
            priority=0.7,
        )
        
        assert unknown.confidence == 1.0  # Fully confident this is unknown
        assert unknown.attempts == 0
    
    def test_resolve_marks_inactive(self):
        """Resolving a question marks it inactive."""
        unknown = Unknown.create("Test question", priority=0.5)
        assert unknown.is_active()
        
        unknown.resolve()
        
        assert unknown.confidence == 0.0
        assert not unknown.is_active()
    
    def test_attempt_tracking(self):
        """Attempts are tracked correctly."""
        unknown = Unknown.create("Test", priority=0.5)
        
        unknown.attempt()
        unknown.attempt()
        
        assert unknown.attempts == 2


class TestMemoryManager:
    """Tests for the unified memory manager."""
    
    def test_store_and_retrieve_episode(self):
        """Can store and retrieve episodes via manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = MemoryManager(Path(tmpdir))
            
            episode = manager.store_episode(
                content="User asked about architecture",
                importance=0.8,
                source="conversation",
            )
            
            recent = manager.get_recent_episodes(hours=1)
            assert len(recent) == 1
            assert recent[0].id == episode.id
    
    def test_store_and_find_fact(self):
        """Can store and find facts via manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = MemoryManager(Path(tmpdir))
            
            manager.store_fact(
                statement="Owner prefers TypeScript",
                source="observation",
            )
            
            facts = manager.find_facts("TypeScript")
            assert len(facts) == 1
            assert "TypeScript" in facts[0].statement
    
    def test_decay_all_memory_types(self):
        """decay_all() affects all memory types."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = MemoryManager(Path(tmpdir))
            
            manager.store_episode("Event", 0.5, "test")
            manager.store_fact("Fact", "test")
            manager.add_unknown("Question?")
            
            future = datetime.now() + timedelta(days=30)
            results = manager.decay_all(future)
            
            assert "episodic" in results
            assert "semantic" in results
            assert "meta" in results
    
    def test_reinforce_via_manager(self):
        """Can reinforce memories via manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = MemoryManager(Path(tmpdir))
            
            fact = manager.store_fact("Test fact", "test", confidence=0.5)
            manager.reinforce(fact.id, strength=0.2)
            
            # Check it was reinforced
            updated = manager.find_facts("Test")[0]
            assert updated.confidence > 0.5
    
    def test_contradict_via_manager(self):
        """Can contradict memories via manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = MemoryManager(Path(tmpdir))
            
            fact = manager.store_fact("Wrong fact", "test", confidence=0.8)
            manager.contradict(fact.id, penalty=0.2)
            
            updated = manager.find_facts("Wrong")[0]
            assert updated.confidence < 0.8
            assert updated.contradiction_count == 1


class TestMemoryInvariants:
    """Tests for critical memory system invariants."""
    
    def test_memory_persists_across_sessions(self):
        """Memory survives manager recreation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            
            # Session 1
            manager1 = MemoryManager(data_dir)
            episode = manager1.store_episode("Important event", 0.9, "test")
            episode_id = episode.id
            
            # Session 2 (new manager, same data)
            manager2 = MemoryManager(data_dir)
            recent = manager2.get_recent_episodes(hours=1)
            
            assert len(recent) == 1
            assert recent[0].id == episode_id
    
    def test_stm_does_not_persist(self):
        """Short-term memory does NOT persist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            
            manager1 = MemoryManager(data_dir)
            manager1.add_to_context("Important context")
            
            manager2 = MemoryManager(data_dir)
            
            assert len(manager2.get_recent_context()) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
