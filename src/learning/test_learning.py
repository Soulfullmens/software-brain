"""
Tests for Layer 4: Learning Engine

Verifies:
1. Repeated prediction failures reduce future confidence/trust
2. Single failure does NOT cause drastic change
3. Trust updates are bounded [0.1, 1.0]
4. Policy persistence
5. Separation of concerns (Engine does not touch BeliefState)
"""

import pytest
import os
import json
from tempfile import TemporaryDirectory

from src.learning.learning_engine import LearningEngine
from src.learning.signals import LearningSignal
from src.learning.policy import LearningPolicy


class TestLearningEngine:
    
    def test_single_failure_slow_update(self):
        """Test 2: Single failure causes small change."""
        engine = LearningEngine()
        initial_bias = engine.policy.prediction_bias
        
        # Signal: Low magnitude failure
        signal = LearningSignal.prediction_failure(prediction_probability=0.5, source="test")
        
        engine.learn(signal)
        
        # Change should be small: 0.5 * 0.05 = 0.025
        # New bias should be slightly negative
        assert engine.policy.prediction_bias < initial_bias
        assert engine.policy.prediction_bias == pytest.approx(-0.025)
        
        # Source trust should also drop slightly
        assert engine.policy.get_trust("test") < 1.0
        assert engine.policy.get_trust("test") == pytest.approx(0.975)

    def test_repeated_failures_accumulate(self):
        """Test 1: Repeated failures significantly reduce trust/bias."""
        engine = LearningEngine()
        
        # 10 failures of high magnitude
        for _ in range(10):
            signal = LearningSignal.prediction_failure(prediction_probability=0.9, source="unreliable")
            engine.learn(signal)
            
        # 0.9 * 0.05 = 0.045 per step * 10 = 0.45 drop
        assert engine.policy.prediction_bias == pytest.approx(-0.45)
        assert engine.policy.get_trust("unreliable") == pytest.approx(0.55)

    def test_trust_bounds(self):
        """Test 3: Trust is clamped to [0.1, 1.0]."""
        engine = LearningEngine()
        
        # Hammer the engine with failures
        for _ in range(50):
            signal = LearningSignal.prediction_failure(prediction_probability=1.0, source="bad_source")
            engine.learn(signal)
            
        # Should not go below 0.1
        assert engine.policy.get_trust("bad_source") == 0.1
        
        # Now define a policy with > 1.0 manual set (simulating logic error or recovery)
        # and verify setter clamps it back if we were to push it up
        # We can't easily push it up via signals in v0 (only failures implemented),
        # but we can call _set_trust directly to test the clamp logic
        engine._set_trust("bad_source", 1.5)
        assert engine.policy.get_trust("bad_source") == 1.0

    def test_persistence(self):
        """Test 4: Learning survives restart."""
        with TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "policy.json")
            
            # 1. Create engine and learn something
            engine1 = LearningEngine(persistence_path=path)
            engine1.learn(LearningSignal.prediction_failure(0.8, "persist_test"))
            engine1.save()
            
            saved_bias = engine1.policy.prediction_bias
            saved_trust = engine1.policy.get_trust("persist_test")
            
            # 2. Load new engine from same path
            engine2 = LearningEngine(persistence_path=path)
            engine2.load()
            
            assert engine2.policy.prediction_bias == saved_bias
            assert engine2.policy.get_trust("persist_test") == saved_trust

    def test_contradiction_learning(self):
        """Contradictions reduce trust of the loser."""
        engine = LearningEngine()
        
        signal = LearningSignal.contradiction(source_lost="liar", urgency=0.8)
        engine.learn(signal)
        
        # Drop = 0.8 * 0.05 = 0.04
        assert engine.policy.get_trust("liar") == pytest.approx(0.96)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
