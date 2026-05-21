"""
Phase 17: Value Alignment & Policy Evolution Verification

Proves that:
1. Policy evolves slowly (EMA)
2. Rollback works
3. Anchors cannot be violated
4. Drift detection catches overreliance
5. Evolution is blocked when agent is stressed
"""

import pytest
from datetime import datetime
from src.system.bootstrap import boot_agent
from src.learning.policy_evolution import PolicyEvolutionEngine, AlignmentAnchor


@pytest.fixture
def temp_brain_dir(tmp_path):
    path = tmp_path / "brain_data"
    path.mkdir()
    yield path


class TestPolicyEvolution:
    
    def test_slow_evolution(self):
        engine = PolicyEvolutionEngine()
        
        # Record many successes for gather_evidence
        initial_weight = engine.get_weight("gather_evidence")
        
        # Need 12+ samples to meet confidence threshold (12/20 = 0.6)
        for _ in range(15):
            engine.record_outcome("gather_evidence", success=True)
        
        # Attempt evolution with healthy budget
        result = engine.attempt_evolution(autonomy_budget=80)
        
        # Should have evolved
        assert result is not None
        
        new_weight = engine.get_weight("gather_evidence")
        
        # Change should be small (slow learning)
        change = abs(new_weight - initial_weight)
        assert change < 0.1  # EMA is slow
        
    def test_evolution_blocked_when_stressed(self):
        engine = PolicyEvolutionEngine()
        
        for _ in range(15):  # Need 12+ for confidence
            engine.record_outcome("gather_evidence", success=True)
        
        # Attempt evolution with LOW budget (stressed agent)
        result = engine.attempt_evolution(autonomy_budget=30)
        
        # Should be blocked
        assert result is None
        
    def test_rollback_works(self):
        engine = PolicyEvolutionEngine()
        
        # Save initial state explicitly
        engine._save_snapshot("Initial state")
        initial_weight = engine.get_weight("gather_evidence")
        
        # Record outcomes and evolve
        for _ in range(15):  # Need 12+ for confidence
            engine.record_outcome("gather_evidence", success=True)
        engine.attempt_evolution(autonomy_budget=80)
        
        evolved_weight = engine.get_weight("gather_evidence")
        assert evolved_weight != initial_weight  # Confirm change happened
        
        # Rollback (goes back 1 step before evolution)
        success = engine.rollback(steps=1)
        assert success is True
        
        # Should be back to initial
        rolled_back = engine.get_weight("gather_evidence")
        assert abs(rolled_back - initial_weight) < 0.01


class TestAlignmentAnchors:
    
    def test_anchors_exist(self):
        engine = PolicyEvolutionEngine()
        
        assert len(engine.anchors) >= 5
        
        anchor_ids = [a.id for a in engine.anchors]
        assert "owner_binding" in anchor_ids
        assert "no_self_privilege_escalation" in anchor_ids
        assert "audit_integrity" in anchor_ids
        
    def test_anchor_violation_detection(self):
        engine = PolicyEvolutionEngine()
        
        # Try to violate owner binding
        violated = engine.check_anchor_violation("override_owner_authority")
        assert violated is not None
        assert violated.id == "owner_binding"
        
        # Normal action should not violate
        safe = engine.check_anchor_violation("ask_clarification")
        assert safe is None


class TestDriftDetection:
    
    def test_overreliance_detection(self):
        engine = PolicyEvolutionEngine()
        
        # Record heavy usage of one heuristic
        for _ in range(50):
            engine.record_outcome("gather_evidence", success=True)
        
        warnings = engine.detect_value_drift()
        
        assert len(warnings) >= 1
        assert any(w["type"] == "overreliance" for w in warnings)
        
    def test_no_drift_with_balanced_usage(self):
        engine = PolicyEvolutionEngine()
        
        # Balanced usage
        for _ in range(10):
            engine.record_outcome("gather_evidence", success=True)
            engine.record_outcome("resolve_contradiction", success=True)
            engine.record_outcome("generate_prediction", success=True)
        
        warnings = engine.detect_value_drift()
        
        # No overreliance warnings
        overreliance = [w for w in warnings if w["type"] == "overreliance"]
        assert len(overreliance) == 0


class TestIntegratedPolicyEvolution:
    
    def test_full_evolution_cycle(self, temp_brain_dir):
        agent = boot_agent(temp_brain_dir, "Evolver")
        
        # 1. Record outcomes - need 12+ for confidence threshold
        for _ in range(15):
            agent.policy_evolution.record_outcome("gather_evidence", success=True)
            agent.policy_evolution.record_outcome("resolve_contradiction", success=False)
        
        # 2. Check drift
        warnings = agent.policy_evolution.detect_value_drift()
        
        # 3. Attempt evolution (healthy budget)
        result = agent.policy_evolution.attempt_evolution(
            autonomy_budget=agent.autonomy.state.execution_budget
        )
        
        # 4. Verify evolution happened
        assert result is not None
        
        # 5. Verify history exists for rollback
        assert len(agent.policy_evolution.history) >= 1
        
        print(f"[SUCCESS] Policy evolved: {result}")
        print(f"[SUCCESS] Drift warnings: {warnings}")
        
    def test_no_runaway_learning(self, temp_brain_dir):
        """
        Critical test: Prove we can't create a runaway learner.
        Even with extreme outcomes, changes remain bounded.
        """
        agent = boot_agent(temp_brain_dir, "Bounded")
        
        initial_weights = {
            h: w.weight for h, w in agent.policy_evolution.weights.items()
        }
        
        # Extreme: 100 successes for one heuristic
        for _ in range(100):
            agent.policy_evolution.record_outcome("gather_evidence", success=True)
        
        # Evolve multiple times
        for _ in range(10):
            agent.policy_evolution.attempt_evolution(autonomy_budget=100)
        
        final_weight = agent.policy_evolution.get_weight("gather_evidence")
        initial_weight = initial_weights.get("gather_evidence", 0.7)
        
        total_change = abs(final_weight - initial_weight)
        
        # Change should still be moderate even after many evolutions
        # Because EMA is slow (0.05) and bounded
        assert total_change < 0.5  # Never more than 50% change
        assert final_weight <= 1.0  # Never exceeds bounds
        assert final_weight >= 0.1  # Never goes too low
        
        print(f"[SUCCESS] No runaway: {initial_weight:.2f} -> {final_weight:.2f} (Δ{total_change:.2f})")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
