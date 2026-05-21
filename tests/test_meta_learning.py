"""
Phase 15: Meta-Learning & Self-Critique Verification

Proves that:
1. Pattern detector identifies recurring failures
2. Heuristic stats track performance
3. Self-critique generates reflective insights
"""

import pytest
from datetime import datetime, timedelta
from src.system.bootstrap import boot_agent
from src.learning.pattern_detector import PatternDetector, HeuristicStats
from src.learning.self_critique import SelfCritiqueEngine, CritiqueType


@pytest.fixture
def temp_brain_dir(tmp_path):
    path = tmp_path / "brain_data"
    path.mkdir()
    yield path


class TestPatternDetector:
    
    def test_heuristic_tracking(self):
        detector = PatternDetector()
        
        # Record some decisions
        detector.record_decision_outcome("low_coherence", success=True, decision_id="d1")
        detector.record_decision_outcome("low_coherence", success=True, decision_id="d2")
        detector.record_decision_outcome("low_coherence", success=False, decision_id="d3")
        
        stats = detector.heuristic_stats["low_coherence"]
        assert stats.usage_count == 3
        assert stats.success_count == 2
        assert stats.failure_count == 1
        assert stats.success_rate == 2/3
        
    def test_contradiction_cycle_detection(self):
        detector = PatternDetector()
        
        # Same entity causes contradictions repeatedly
        for _ in range(5):
            detector.record_contradiction("problematic_entity")
            
        patterns = detector.get_active_patterns()
        assert len(patterns) >= 1
        
        cycle_pattern = patterns[0]
        assert cycle_pattern.pattern_type == "contradiction_cycle"
        assert "problematic_entity" in cycle_pattern.description
        
    def test_goal_starvation_detection(self):
        detector = PatternDetector()
        
        # Goal repeatedly starves
        for _ in range(4):
            detector.record_goal_starvation("goal_123", "Learn Python")
            
        patterns = detector.get_active_patterns()
        assert len(patterns) >= 1
        assert any(p.pattern_type == "goal_starvation" for p in patterns)


class TestSelfCritique:
    
    def test_critique_from_pattern(self):
        engine = SelfCritiqueEngine()
        
        critique = engine.critique_from_pattern(
            pattern_type="contradiction_cycle",
            description="Entity X keeps conflicting",
            severity=0.7,
            pattern_id="p1"
        )
        
        assert critique.critique_type == CritiqueType.PATTERN_RECURRENCE
        assert critique.severity == 0.7
        assert "p1" in critique.related_patterns
        assert critique.suggested_action is not None
        
    def test_coherence_drift_detection(self):
        engine = SelfCritiqueEngine()
        
        # Establish high baseline (first 5 observations set _last_coherence)
        for v in [0.9, 0.9, 0.85, 0.8, 0.8]:
            engine.observe_coherence(v)
        
        # Now simulate sudden drop - check each return
        critique = None
        for v in [0.4, 0.3, 0.3, 0.3, 0.3]:
            result = engine.observe_coherence(v)
            if result is not None:
                critique = result
                break
        
        # Drift should have been detected
        assert critique is not None
        assert critique.critique_type == CritiqueType.COHERENCE_DRIFT
        
    def test_heuristic_warning_critique(self):
        engine = SelfCritiqueEngine()
        
        critique = engine.critique_from_heuristic_warning(
            heuristic_id="gather_evidence",
            warning_type="low_success_rate",
            stats={"success_rate": 0.25, "confidence": 0.4}
        )
        
        assert critique.critique_type == CritiqueType.PLANNING_BIAS
        assert "gather_evidence" in critique.message


class TestIntegratedMetaLearning:
    
    def test_full_introspection_loop(self, temp_brain_dir):
        """
        End-to-end test of the meta-learning system.
        """
        agent = boot_agent(temp_brain_dir, "Introspector")
        
        # 1. Simulate repeated failures
        for i in range(5):
            agent.patterns.record_decision_outcome(
                heuristic_id="resolve_contradiction",
                success=False,
                decision_id=f"fail_{i}"
            )
            
        # 2. Check heuristic health
        warnings = agent.patterns.analyze_heuristic_health()
        assert len(warnings) >= 1
        assert warnings[0]["warning"] == "low_success_rate"
        
        # 3. Generate critique from warning
        for w in warnings:
            agent.critique.critique_from_heuristic_warning(
                w["heuristic"],
                w["warning"],
                w
            )
            
        # 4. Verify critiques exist
        critiques = agent.critique.get_recent_critiques()
        assert len(critiques) >= 1
        
        # 5. Summary should reflect state
        pattern_summary = agent.patterns.summary()
        critique_summary = agent.critique.summary()
        
        assert pattern_summary["heuristics_tracked"] >= 1
        assert critique_summary["total_critiques"] >= 1
        
        print(f"[SUCCESS] Pattern Summary: {pattern_summary}")
        print(f"[SUCCESS] Critique Summary: {critique_summary}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
