"""
Phase 26B.1: Blame Accumulation Verification

Proves that:
1. Single events don't dominate (capped contribution).
2. EMA smoothing works (pressure changes slowly).
3. Decay causes old blame to fade.
4. Regret score weights contribution.
5. Adjustment threshold gate works.
6. No oscillation from alternating blame.
"""

import pytest
from src.learning.attribution import BlameVector
from src.learning.accumulation import BlameAccumulator, PressureVector


class TestPressureVector:
    
    def test_primary_pressure_identification(self):
        """Primary pressure is correctly identified."""
        pressure = PressureVector(
            planner_confidence=0.1,
            risk_estimation=0.5,  # Highest
            authority_threshold=-0.2
        )
        
        assert pressure.primary_pressure == "risk_estimation"
        assert pressure.max_pressure == 0.5


class TestBlameAccumulator:
    
    def test_single_event_capped(self):
        """One event cannot dominate pressure."""
        accumulator = BlameAccumulator(max_single_contribution=0.1)
        
        # Huge blame
        huge_blame = BlameVector(
            planner_confidence=1.0,
            risk_estimation=1.0
        )
        
        accumulator.accumulate(huge_blame, regret_score=2.0)
        
        # Pressure should be capped, not 1.0
        assert accumulator.pressure.planner_confidence <= 0.1
        
    def test_ema_smoothing(self):
        """Pressure changes slowly with EMA."""
        accumulator = BlameAccumulator(ema_alpha=0.1, max_single_contribution=0.5)
        
        # First blame
        blame1 = BlameVector(planner_confidence=0.5)
        accumulator.accumulate(blame1, regret_score=1.0)
        pressure_after_1 = accumulator.pressure.planner_confidence
        
        # Second opposing blame
        blame2 = BlameVector(planner_confidence=-0.5)
        accumulator.accumulate(blame2, regret_score=1.0)
        pressure_after_2 = accumulator.pressure.planner_confidence
        
        # Pressure should NOT have flipped sign entirely (smoothed)
        # With alpha=0.1, change should be gradual
        assert abs(pressure_after_2) < abs(pressure_after_1)
        
    def test_decay_fades_old_blame(self):
        """Old pressure decays over time."""
        accumulator = BlameAccumulator(decay_rate=0.5)  # Aggressive decay for test
        
        # Initial blame
        blame = BlameVector(risk_estimation=0.5)
        accumulator.accumulate(blame, regret_score=1.0)
        initial_pressure = accumulator.pressure.risk_estimation
        
        # No new blame for 5 updates (empty blame)
        for _ in range(5):
            accumulator.accumulate(BlameVector(), regret_score=0.0)
            
        # Pressure should have decayed significantly
        final_pressure = accumulator.pressure.risk_estimation
        assert abs(final_pressure) < abs(initial_pressure) * 0.2
        
    def test_regret_weights_contribution(self):
        """Higher regret means more impact."""
        # Use higher max contribution so regret weighting can show difference
        accumulator_low = BlameAccumulator(max_single_contribution=0.5)
        accumulator_high = BlameAccumulator(max_single_contribution=0.5)
        
        blame = BlameVector(goal_selection=0.3)
        
        accumulator_low.accumulate(blame, regret_score=0.1)  # Low regret
        accumulator_high.accumulate(blame, regret_score=2.0)  # High regret
        
        # High regret should produce more pressure
        assert accumulator_high.pressure.goal_selection > accumulator_low.pressure.goal_selection
        
    def test_adjustment_threshold_gate(self):
        """Adjustment only allowed when pressure exceeds threshold."""
        # Use higher alpha to allow faster buildup for testing
        accumulator = BlameAccumulator(
            ema_alpha=0.5,           # Fast response
            decay_rate=1.0,          # No decay
            max_single_contribution=0.3  # Allow larger steps
        )
        
        # Low pressure initially
        small_blame = BlameVector(cost_projection=0.5)
        accumulator.accumulate(small_blame, regret_score=0.5)
        
        # After one event with low regret, pressure is small
        # Should not trigger yet
        assert accumulator.should_trigger_adjustment(threshold=0.2) is False
        
        # Build up pressure with many high-regret events
        for _ in range(20):
            accumulator.accumulate(small_blame, regret_score=2.0)
            
        # Now should trigger
        assert accumulator.should_trigger_adjustment(threshold=0.2) is True
        
    def test_no_oscillation_from_alternating_blame(self):
        """Alternating blame doesn't cause wild swings."""
        accumulator = BlameAccumulator(ema_alpha=0.1)
        
        positive_blame = BlameVector(authority_threshold=0.3)
        negative_blame = BlameVector(authority_threshold=-0.3)
        
        # Alternate 20 times
        for i in range(20):
            if i % 2 == 0:
                accumulator.accumulate(positive_blame, regret_score=1.0)
            else:
                accumulator.accumulate(negative_blame, regret_score=1.0)
                
        # Final pressure should be near zero (not oscillating wildly)
        assert abs(accumulator.pressure.authority_threshold) < 0.1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
