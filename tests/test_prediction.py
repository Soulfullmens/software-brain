"""
Tests for Layer 2 Step 5: Prediction Lifecycle

Verifies:
1. Prediction lifecycle states (active -> confirmed/denied/expired)
2. Manager creation and expiry logic
3. Distinction between denied (failure) and expired (timeout)
4. Coherence F-term reaction (only denied predictions impact it)
5. No memory/learning handling here (out of scope)
"""

import pytest
import time
from datetime import datetime, timedelta

from src.cognition.belief_state import BeliefState
from src.cognition.prediction import Prediction
from src.cognition.prediction_manager import PredictionManager


class TestPredictionLifecycle:
    """Tests for the Prediction object lifecycle."""
    
    def test_create_prediction(self):
        """Create a prediction."""
        p = Prediction.create(
            statement="Test", probability=0.8, expected_by=datetime.now()
        )
        assert p.is_active()
        assert p.outcome is None
    
    def test_mark_confirmed(self):
        """Mark as confirmed."""
        p = Prediction.create("Test", 0.8, datetime.now())
        p.mark_confirmed()
        
        assert not p.is_active()
        assert p.outcome == "confirmed"
        assert p.outcome_time is not None
    
    def test_mark_denied(self):
        """Mark as denied."""
        p = Prediction.create("Test", 0.8, datetime.now())
        p.mark_denied()
        
        assert not p.is_active()
        assert p.outcome == "denied"
        assert p.outcome_time is not None
        
    def test_mark_expired(self):
        """Mark as expired."""
        p = Prediction.create("Test", 0.8, datetime.now())
        p.mark_expired()
        
        assert not p.is_active()
        assert p.outcome == "expired"
        assert p.outcome_time is not None


class TestPredictionManager:
    """Tests for the Prediction Manager."""
    
    def test_create_prediction_adds_to_state(self):
        """Manager adds prediction to state."""
        state = BeliefState.create_empty()
        manager = PredictionManager(state)
        
        p = manager.create_prediction(
            statement="Manager Test",
            probability=0.7,
            expected_by=datetime.now() + timedelta(hours=1)
        )
        
        assert state.prediction_count() == 1
        assert state.predictions[0] == p
        assert state.get_active_predictions()[0] == p
    
    def test_expiry_check(self):
        """Expiry check marks past-deadline predictions as expired."""
        state = BeliefState.create_empty()
        manager = PredictionManager(state)
        
        # Past deadline
        p1 = manager.create_prediction(
            "Past", 0.8, datetime.now() - timedelta(minutes=1)
        )
        # Future deadline
        p2 = manager.create_prediction(
            "Future", 0.8, datetime.now() + timedelta(minutes=10)
        )
        
        expired_count = manager.check_expiry()
        
        assert expired_count == 1
        assert p1.outcome == "expired"
        assert p2.is_active()
    
    def test_expiry_updates_timestamp(self):
        """Expiry updates state timestamp."""
        state = BeliefState.create_empty()
        manager = PredictionManager(state)
        
        old_ts = state.timestamp
        time.sleep(0.01)
        
        manager.create_prediction("Past", 0.8, datetime.now() - timedelta(minutes=1))
        manager.check_expiry()
        
        assert state.timestamp > old_ts
    
    def test_resolve_prediction(self):
        """Can manually resolve a prediction."""
        state = BeliefState.create_empty()
        manager = PredictionManager(state)
        
        p = manager.create_prediction("Test", 0.8, datetime.now() + timedelta(hours=1))
        
        success, signal = manager.resolve_prediction(p.id, "confirmed")
        
        assert success
        assert signal is None
        assert p.outcome == "confirmed"
    
    def test_resolve_denied_emits_signal(self):
        """Denied prediction emits a LearningSignal."""
        state = BeliefState.create_empty()
        manager = PredictionManager(state)
        
        p = manager.create_prediction("Test", 0.9, datetime.now() + timedelta(hours=1))
        
        success, signal = manager.resolve_prediction(p.id, "denied")
        
        assert success
        assert signal is not None
        assert signal.type == "prediction_failure"
        assert signal.magnitude == 0.9  # Magnitude = probability
    
    def test_resolve_nonexistent(self):
        """Resolving missing ID returns False."""
        state = BeliefState.create_empty()
        manager = PredictionManager(state)
        
        success, signal = manager.resolve_prediction("missing", "confirmed")
        assert not success
        assert signal is None


class TestFailureLoad:
    """Tests for failure signal calculation."""
    
    def test_failure_load_only_counts_denied(self):
        """Expired predictions do not count as failure."""
        state = BeliefState.create_empty()
        manager = PredictionManager(state)
        
        # Denied (counts)
        p1 = manager.create_prediction("Denied", 0.9, datetime.now())
        manager.resolve_prediction(p1.id, "denied")
        
        # Expired (does not count)
        p2 = manager.create_prediction("Expired", 0.9, datetime.now())
        manager.resolve_prediction(p2.id, "expired")
        
        # Confirmed (does not count)
        p3 = manager.create_prediction("Confirmed", 0.9, datetime.now())
        manager.resolve_prediction(p3.id, "confirmed")
        
        load = manager.get_failure_load()
        
        assert load == 0.9  # Only p1 counts


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
