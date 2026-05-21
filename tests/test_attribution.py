"""
Phase 26A: Regret Attribution Verification

Proves that:
1. BlameVector correctly identifies primary blame dimension.
2. AttributionEngine produces normalized blame vectors.
3. Different failure types produce different blame distributions.
4. Blame is deterministic (same input → same output).
"""

import pytest
from src.learning.regret import FailureArtifact, FailureType
from src.learning.attribution import BlameVector, AttributionEngine


class TestBlameVector:
    
    def test_primary_blame_identification(self):
        """Primary blame is correctly identified."""
        blame = BlameVector(
            planner_confidence=0.1,
            risk_estimation=0.5,  # Highest
            authority_threshold=0.2,
            goal_selection=0.1,
            cost_projection=0.1
        )
        
        assert blame.primary_blame == "risk_estimation"
        
    def test_total_blame_calculation(self):
        """Total blame is sum of absolute values."""
        blame = BlameVector(
            planner_confidence=0.2,
            risk_estimation=-0.3,  # Negative (too cautious)
            authority_threshold=0.2,
            goal_selection=0.2,
            cost_projection=0.1
        )
        
        assert abs(blame.total_blame - 1.0) < 0.01


class TestAttributionEngine:
    
    def test_goal_failed_blames_goal_selection(self):
        """Goal failure primarily blames goal selection."""
        engine = AttributionEngine()
        
        artifact = FailureArtifact(
            failure_type=FailureType.GOAL_FAILED,
            goal_id="goal_123",
            irreversible=True,
            rollback_used=False
        )
        
        blame = engine.attribute(artifact)
        
        # Goal selection should have significant blame
        assert blame.goal_selection > 0.2
        # Blame should be normalized
        assert 0.9 < blame.total_blame < 1.1
        
    def test_cost_exceeded_blames_cost_projection(self):
        """Cost exceeded primarily blames cost projection."""
        engine = AttributionEngine()
        
        artifact = FailureArtifact(
            failure_type=FailureType.COST_THRESHOLD_EXCEEDED,
            delta_cost=500.0
        )
        
        blame = engine.attribute(artifact)
        
        assert blame.primary_blame == "cost_projection"
        
    def test_authority_blocked_blames_authority(self):
        """Authority blocked primarily blames authority_threshold, not planner."""
        engine = AttributionEngine()
        
        # When authority blocks, it's authority being too cautious
        artifact = FailureArtifact(
            failure_type=FailureType.AUTHORITY_BLOCKED,
            irreversible=True,
            rollback_possible=False
        )
        
        blame = engine.attribute(artifact)
        
        # Authority threshold should be primary blame (by absolute value)
        assert blame.primary_blame == "authority_threshold"
        
        # Authority threshold should be NEGATIVE (too cautious, not too permissive)
        assert blame.authority_threshold < 0
        
        # Planner confidence should be minor
        assert abs(blame.planner_confidence) < abs(blame.authority_threshold)
        
    def test_attribution_is_deterministic(self):
        """Same artifact produces same blame."""
        engine = AttributionEngine()
        
        artifact = FailureArtifact(
            failure_type=FailureType.ESCALATION_TRIGGERED,
            goal_id="goal_abc",
            irreversible=True
        )
        
        blame1 = engine.attribute(artifact)
        blame2 = engine.attribute(artifact)
        
        assert blame1.planner_confidence == blame2.planner_confidence
        assert blame1.risk_estimation == blame2.risk_estimation
        assert blame1.primary_blame == blame2.primary_blame


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
