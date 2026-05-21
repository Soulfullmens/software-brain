"""
Phase 26B.2: Heuristic Adjustment Verification

Proves that:
1. Adjustment only triggers when pressure exceeds threshold.
2. Only one dimension is mutated at a time (primary pressure).
3. Deltas are bounded.
4. Pressure is reset after adjustment.
5. Adjustments are logged and reversible.
6. Full loop integration (Failure → Mutation).
"""

import pytest
from src.learning.regret import FailureArtifact, FailureType, RegretLedger
from src.learning.attribution import BlameVector, AttributionEngine
from src.learning.accumulation import BlameAccumulator
from src.learning.adjustment import (
    AdjustmentPolicy, AdjustmentLog, AdjustmentEvent, AdjustmentDimension
)


@pytest.fixture
def full_pipeline():
    """Full learning pipeline: Attribution → Accumulation → Adjustment."""
    accumulator = BlameAccumulator(
        ema_alpha=0.5,
        decay_rate=1.0,  # No decay for predictable tests
        max_single_contribution=1.0  # No capping for predictable tests
    )
    log = AdjustmentLog()
    policy = AdjustmentPolicy(
        accumulator=accumulator,
        log=log,
        threshold=0.1,
        sensitivity=0.1
    )
    return {
        "attribution": AttributionEngine(),
        "accumulator": accumulator,
        "log": log,
        "policy": policy
    }


class TestAdjustmentPolicy:
    
    def test_no_adjustment_below_threshold(self, full_pipeline):
        """No mutation when pressure is below threshold."""
        policy = full_pipeline["policy"]
        accumulator = full_pipeline["accumulator"]
        
        # Small blame
        small_blame = BlameVector(risk_estimation=0.1)
        accumulator.accumulate(small_blame, regret_score=0.5)
        
        # Should not adjust
        event = policy.adjust()
        assert event is None
        assert len(full_pipeline["log"].events) == 0
        
    def test_adjustment_triggers_at_threshold(self, full_pipeline):
        """Mutation triggers when pressure exceeds threshold."""
        policy = full_pipeline["policy"]
        accumulator = full_pipeline["accumulator"]
        
        # Build up pressure
        blame = BlameVector(cost_projection=0.5)
        for _ in range(10):
            accumulator.accumulate(blame, regret_score=2.0)
            
        # Should trigger
        assert policy.should_adjust() is True
        
        event = policy.adjust()
        assert event is not None
        assert event.dimension == AdjustmentDimension.COST_PROJECTION
        assert len(full_pipeline["log"].events) == 1
        
    def test_only_primary_dimension_mutated(self, full_pipeline):
        """Only the dimension with highest pressure is mutated."""
        # Create NEW accumulator with higher cap to allow differentiation
        accumulator = BlameAccumulator(
            ema_alpha=0.5,
            decay_rate=1.0,
            max_single_contribution=1.0  # No capping for this test
        )
        log = AdjustmentLog()
        policy = AdjustmentPolicy(
            accumulator=accumulator,
            log=log,
            threshold=0.1
        )
        
        # Very unequal blame - goal_selection is clearly dominant
        blame = BlameVector(
            goal_selection=0.9,
            risk_estimation=0.05,
            planner_confidence=0.05
        )
        for _ in range(5):
            accumulator.accumulate(blame, regret_score=1.0)
            
        event = policy.adjust()
        
        # Only goal_selection should have been adjusted
        assert event.dimension == AdjustmentDimension.GOAL_SELECTION
        
    def test_deltas_are_bounded(self, full_pipeline):
        """Even extreme pressure produces bounded deltas."""
        policy = full_pipeline["policy"]
        accumulator = full_pipeline["accumulator"]
        
        # Extreme blame
        extreme_blame = BlameVector(authority_threshold=1.0)
        for _ in range(50):
            accumulator.accumulate(extreme_blame, regret_score=5.0)
            
        event = policy.adjust()
        
        # Delta should be bounded by knob config (max_delta=0.01 for authority)
        assert abs(event.delta) <= 0.01
        
    def test_pressure_reset_after_adjustment(self, full_pipeline):
        """Pressure for adjusted dimension is reset to zero."""
        policy = full_pipeline["policy"]
        accumulator = full_pipeline["accumulator"]
        
        # Build pressure
        blame = BlameVector(planner_confidence=0.6)
        for _ in range(10):
            accumulator.accumulate(blame, regret_score=2.0)
            
        pressure_before = accumulator.get_pressure().planner_confidence
        assert abs(pressure_before) > 0.1  # Verify pressure exists
        
        policy.adjust()
        
        # Pressure should be reset
        pressure_after = accumulator.get_pressure().planner_confidence
        assert pressure_after == 0.0


class TestAdjustmentLog:
    
    def test_append_and_retrieve(self):
        """Events can be appended and retrieved."""
        log = AdjustmentLog()
        
        event = AdjustmentEvent(
            dimension=AdjustmentDimension.RISK_ESTIMATION,
            old_value=0.0,
            new_value=0.02,
            delta=0.02
        )
        log.append(event)
        
        assert len(log.events) == 1
        assert log.events[0].dimension == AdjustmentDimension.RISK_ESTIMATION
        
    def test_reversal_tracking(self):
        """Reversed events are tracked separately."""
        log = AdjustmentLog()
        
        event1 = AdjustmentEvent(dimension=AdjustmentDimension.COST_PROJECTION, delta=0.01)
        event2 = AdjustmentEvent(dimension=AdjustmentDimension.COST_PROJECTION, delta=0.01)
        
        log.append(event1)
        log.append(event2)
        
        # Reverse one
        log.mark_reversed(event1.id)
        
        assert len(log.get_unreversed()) == 1
        assert log.net_adjustment(AdjustmentDimension.COST_PROJECTION) == 0.01
        

class TestFullLoopIntegration:
    
    def test_failure_to_mutation_loop(self, full_pipeline):
        """
        Full loop: Failure → Attribution → Accumulation → Gate → Mutation → Reset.
        
        This is THE critical integration test.
        """
        attribution = full_pipeline["attribution"]
        accumulator = full_pipeline["accumulator"]
        policy = full_pipeline["policy"]
        log = full_pipeline["log"]
        
        # Step 1: Create failure artifacts
        failure1 = FailureArtifact(
            failure_type=FailureType.COST_THRESHOLD_EXCEEDED,
            goal_id="goal_expensive",
            delta_cost=200.0
        )
        failure2 = FailureArtifact(
            failure_type=FailureType.COST_THRESHOLD_EXCEEDED,
            goal_id="goal_also_expensive",
            delta_cost=300.0
        )
        
        # Step 2: Attribute (diagnose)
        blame1 = attribution.attribute(failure1)
        blame2 = attribution.attribute(failure2)
        
        # Both should primarily blame cost_projection
        assert blame1.primary_blame == "cost_projection"
        assert blame2.primary_blame == "cost_projection"
        
        # Step 3: Accumulate (regulate)
        for _ in range(5):
            accumulator.accumulate(blame1, regret_score=failure1.regret_score)
            accumulator.accumulate(blame2, regret_score=failure2.regret_score)
            
        # Step 4: Gate check
        assert policy.should_adjust() is True
        
        # Step 5: Mutate
        old_cost_factor = policy.get_knob_value(AdjustmentDimension.COST_PROJECTION)
        event = policy.adjust()
        new_cost_factor = policy.get_knob_value(AdjustmentDimension.COST_PROJECTION)
        
        # Cost factor should have increased (positive pressure → higher factor)
        assert event is not None
        assert event.dimension == AdjustmentDimension.COST_PROJECTION
        assert new_cost_factor > old_cost_factor
        
        # Step 6: Verify pressure reset
        assert accumulator.get_pressure().cost_projection == 0.0
        
        # Step 7: Log should be auditable
        assert len(log.events) == 1
        assert log.events[0].parameter_name == "cost_inflation_factor"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
