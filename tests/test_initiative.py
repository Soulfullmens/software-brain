"""
Phase 21B: Bounded Initiative Recovery Verification

Proves that:
1. Initiative grows slowly with successes
2. Initiative drops sharply with failures
3. Promotion requires time + success + health
4. The system can earn NORMAL again
5. Risk tolerance is bounded
"""

import pytest
from datetime import datetime, timedelta
from src.system.bootstrap import boot_agent
from src.system.initiative import InitiativeEngine
from src.system.autonomy import AutonomyLevel


@pytest.fixture
def temp_brain_dir(tmp_path):
    path = tmp_path / "brain_data"
    path.mkdir()
    yield path


class TestInitiativeGrowth:
    
    def test_success_increases_initiative(self):
        """Successes increase initiative."""
        engine = InitiativeEngine()
        
        initial = engine.initiative_score
        
        for _ in range(10):
            engine.record_success()
        
        assert engine.initiative_score > initial
        assert engine.consecutive_successes == 10
        
    def test_consecutive_success_bonus(self):
        """Consecutive successes get bonus growth."""
        engine = InitiativeEngine()
        
        # First success
        engine.initiative_score = 0.5
        first_growth = engine.record_success() - 0.5
        
        # Reset and do 5 consecutive
        engine.initiative_score = 0.5
        engine.consecutive_successes = 5
        fifth_growth = engine.record_success() - 0.5
        
        # Fifth should grow more due to bonus
        assert fifth_growth > first_growth
        
    def test_initiative_bounded_at_max(self):
        """Initiative cannot exceed max."""
        engine = InitiativeEngine()
        
        for _ in range(100):
            engine.record_success()
        
        assert engine.initiative_score <= engine.max_initiative
        

class TestInitiativeDecay:
    
    def test_failure_decreases_initiative(self):
        """Failures decrease initiative."""
        engine = InitiativeEngine()
        engine.initiative_score = 0.7
        
        engine.record_failure()
        
        assert engine.initiative_score < 0.7
        assert engine.consecutive_failures == 1
        
    def test_consecutive_failure_penalty(self):
        """Consecutive failures have harsher penalty."""
        engine = InitiativeEngine()
        
        engine.initiative_score = 0.7
        first_drop = 0.7 - engine.record_failure()
        
        engine.initiative_score = 0.7
        engine.consecutive_failures = 3
        third_drop = 0.7 - engine.record_failure()
        
        assert third_drop > first_drop
        
    def test_initiative_bounded_at_min(self):
        """Initiative cannot go below min."""
        engine = InitiativeEngine()
        
        for _ in range(50):
            engine.record_failure()
        
        assert engine.initiative_score >= engine.min_initiative


class TestPromotionMechanics:
    
    def test_promotion_requires_initiative_threshold(self):
        """Promotion needs initiative >= threshold."""
        engine = InitiativeEngine()
        engine.initiative_score = 0.3  # Below 0.5 threshold
        engine.level_start_time = datetime.now() - timedelta(minutes=15)
        
        eligible, level, reason = engine.check_promotion_eligible(
            current_level="CAUTIOUS",
            coherence=0.8,
            critique_count=0
        )
        
        assert eligible is False
        assert "Initiative too low" in reason
        
    def test_promotion_requires_time_at_level(self):
        """Promotion needs time at current level."""
        engine = InitiativeEngine()
        engine.initiative_score = 0.6  # Above threshold
        engine.level_start_time = datetime.now()  # Just started
        
        eligible, level, reason = engine.check_promotion_eligible(
            current_level="CAUTIOUS",
            coherence=0.8,
            critique_count=0
        )
        
        assert eligible is False
        assert "time" in reason.lower()
        
    def test_promotion_requires_health(self):
        """Promotion needs good system health."""
        engine = InitiativeEngine()
        engine.initiative_score = 0.6
        engine.level_start_time = datetime.now() - timedelta(minutes=15)
        
        # Low coherence
        eligible, level, reason = engine.check_promotion_eligible(
            current_level="CAUTIOUS",
            coherence=0.4,
            critique_count=0
        )
        
        assert eligible is False
        assert "Coherence" in reason
        
    def test_cautious_to_normal_promotion(self):
        """CAUTIOUS can promote to NORMAL with right conditions."""
        engine = InitiativeEngine()
        engine.initiative_score = 0.6
        engine.level_start_time = datetime.now() - timedelta(minutes=15)
        
        eligible, level, reason = engine.check_promotion_eligible(
            current_level="CAUTIOUS",
            coherence=0.8,
            critique_count=0
        )
        
        assert eligible is True
        assert level == "NORMAL"


class TestDemotionMechanics:
    
    def test_demotion_on_low_coherence(self):
        """Low coherence triggers demotion."""
        engine = InitiativeEngine()
        engine.initiative_score = 0.8
        
        demote, level, reason = engine.check_demotion_needed(
            current_level="NORMAL",
            coherence=0.35,
            critique_count=0
        )
        
        assert demote is True
        assert level == "CAUTIOUS"
        
    def test_demotion_on_low_initiative(self):
        """Low initiative triggers demotion."""
        engine = InitiativeEngine()
        engine.initiative_score = 0.25  # Below 0.3
        
        demote, level, reason = engine.check_demotion_needed(
            current_level="NORMAL",
            coherence=0.8,
            critique_count=0
        )
        
        assert demote is True
        assert level == "CAUTIOUS"


class TestRecoveryInitiative:
    
    def test_recovery_resets_initiative(self):
        """Recovery resets initiative to low baseline."""
        engine = InitiativeEngine()
        engine.initiative_score = 0.9
        engine.consecutive_successes = 20
        
        engine.reset_for_recovery()
        
        assert engine.initiative_score == 0.3
        assert engine.consecutive_successes == 0
        
    def test_earning_normal_after_recovery(self):
        """System can earn NORMAL again after recovery."""
        engine = InitiativeEngine()
        
        # Recover
        engine.reset_for_recovery()
        assert engine.initiative_score == 0.3
        
        # Simulate time passing
        engine.level_start_time = datetime.now() - timedelta(minutes=15)
        
        # Build up successes
        for _ in range(20):
            engine.record_success()
        
        # Check promotion
        eligible, level, reason = engine.check_promotion_eligible(
            current_level="CAUTIOUS",
            coherence=0.8,
            critique_count=0
        )
        
        # Should be eligible for NORMAL
        assert engine.initiative_score >= 0.5
        assert eligible is True
        assert level == "NORMAL"
        
        print(f"[INITIATIVE TEST] Earned NORMAL: {reason}")


class TestRiskTolerance:
    
    def test_risk_tolerance_scales_with_initiative(self):
        """Risk tolerance is bounded and scales with initiative."""
        engine = InitiativeEngine()
        
        engine.initiative_score = 0.2
        low_risk = engine.get_risk_tolerance()
        
        engine.initiative_score = 0.8
        high_risk = engine.get_risk_tolerance()
        
        assert high_risk > low_risk
        assert high_risk < 1.0  # Always bounded


class TestIntegratedInitiativeRecovery:
    
    def test_full_recovery_to_normal_cycle(self, temp_brain_dir):
        """Test complete cycle: freeze -> recover -> earn NORMAL."""
        agent = boot_agent(temp_brain_dir, "Resilient")
        
        from src.system.recovery import RecoveryProtocol
        from src.system.autonomy import FreezeReason
        
        initiative = InitiativeEngine()
        recovery = RecoveryProtocol()
        
        # 1. Start at NORMAL
        assert agent.autonomy.state.level == AutonomyLevel.NORMAL
        
        # 2. Freeze
        agent.autonomy._freeze(FreezeReason.MANUAL_FREEZE)
        assert agent.autonomy.state.frozen is True
        
        # 3. Recover
        agent.autonomy.state.frozen_at = datetime.now() - timedelta(minutes=10)
        success, _ = recovery.attempt_recovery(
            autonomy_state=agent.autonomy.state,
            coherence=0.8,
            critique_count=0
        )
        assert success is True
        assert agent.autonomy.state.level == AutonomyLevel.CAUTIOUS
        
        # 4. Reset initiative for recovery
        initiative.reset_for_recovery()
        assert initiative.initiative_score == 0.3
        
        # 5. Simulate time + build successes
        initiative.level_start_time = datetime.now() - timedelta(minutes=15)
        for _ in range(20):
            initiative.record_success()
        
        # 6. Check promotion eligibility
        eligible, new_level, _ = initiative.check_promotion_eligible(
            current_level="CAUTIOUS",
            coherence=0.8,
            critique_count=0
        )
        
        assert eligible is True
        assert new_level == "NORMAL"
        
        print("[INITIATIVE TEST] Full recovery cycle completed: NORMAL -> FROZEN -> CAUTIOUS -> NORMAL")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
