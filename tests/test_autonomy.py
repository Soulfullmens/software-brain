"""
Phase 16: Autonomy Throttling & Stability Control Verification

Proves that:
1. Autonomy regulator controls action permissions
2. Budget system limits execution
3. Self-freeze triggers work
4. The agent CAN stop itself
"""

import pytest
from datetime import datetime
from src.system.bootstrap import boot_agent
from src.system.autonomy import AutonomyRegulator, AutonomyLevel, FreezeReason
from src.system.intent import IntentContext
from src.agency.action import Action, PlanProposal


@pytest.fixture
def temp_brain_dir(tmp_path):
    path = tmp_path / "brain_data"
    path.mkdir()
    yield path


class TestAutonomyRegulator:
    
    def test_budget_consumption(self):
        reg = AutonomyRegulator()
        
        initial = reg.state.execution_budget
        cost = reg.consume_budget("generate_prediction")
        
        assert cost == 10  # Default cost for this action
        assert reg.state.execution_budget == initial - cost
        
    def test_budget_exhaustion_freeze(self):
        reg = AutonomyRegulator()
        
        # Exhaust budget
        reg.state.execution_budget = 5
        
        # Try action that costs 10
        can_exec, reason = reg.can_execute("generate_prediction")
        assert can_exec is False
        assert "Insufficient budget" in reason
        
    def test_freeze_on_low_coherence(self):
        reg = AutonomyRegulator()
        
        # Evaluate with low coherence
        level = reg.evaluate_autonomy(
            coherence=0.2,  # Below 0.3 threshold
            recent_critiques=0,
            pattern_severity=0.0,
            goal_conflicts=0,
            hours_since_human=1.0
        )
        
        assert level == AutonomyLevel.FROZEN
        assert reg.state.frozen is True
        assert reg.state.freeze_reason == FreezeReason.COHERENCE_COLLAPSE
        
    def test_freeze_on_critique_overload(self):
        reg = AutonomyRegulator()
        
        level = reg.evaluate_autonomy(
            coherence=0.8,
            recent_critiques=6,  # Above 5 threshold
            pattern_severity=0.0,
            goal_conflicts=0,
            hours_since_human=1.0
        )
        
        assert level == AutonomyLevel.FROZEN
        assert reg.state.freeze_reason == FreezeReason.CRITIQUE_OVERLOAD
        
    def test_action_type_restriction(self):
        reg = AutonomyRegulator()
        
        # Set to minimal level
        reg._set_level(AutonomyLevel.MINIMAL)
        
        # Can do ask_clarification
        can_exec, _ = reg.can_execute("ask_clarification")
        assert can_exec is True
        
        # Cannot do generate_prediction
        can_exec, reason = reg.can_execute("generate_prediction")
        assert can_exec is False
        assert "not allowed" in reason


class TestAgentSelfStop:
    """The critical test: prove the agent can stop itself."""
    
    def test_agent_stops_on_critique_overload(self, temp_brain_dir):
        agent = boot_agent(temp_brain_dir, "SelfStopper")
        
        # 1. Verify agent starts healthy
        assert agent.autonomy.state.frozen is False
        assert agent.autonomy.state.level == AutonomyLevel.NORMAL
        
        # 2. Simulate many critiques (system stressed)
        for i in range(6):
            agent.critique.critique_from_pattern(
                pattern_type="contradiction_cycle",
                description=f"Issue {i}",
                severity=0.7,
                pattern_id=f"p{i}"
            )
        
        # 3. Agent evaluates its own state
        recent_critiques = len(agent.critique.get_recent_critiques())
        level = agent.autonomy.evaluate_autonomy(
            coherence=agent.belief_state.coherence_score,
            recent_critiques=recent_critiques,
            pattern_severity=0.5,
            goal_conflicts=0,
            hours_since_human=1.0
        )
        
        # 4. Agent should freeze itself
        assert level == AutonomyLevel.FROZEN
        assert agent.autonomy.state.frozen is True
        
        print(f"[SUCCESS] Agent froze itself: {agent.autonomy.state.freeze_reason.value}")
        
    def test_executor_respects_autonomy_denial(self, temp_brain_dir):
        agent = boot_agent(temp_brain_dir, "Governed")
        
        # 1. Force freeze
        agent.autonomy._freeze(FreezeReason.MANUAL_FREEZE)
        
        # 2. Try to execute an action
        action = Action("generate_prediction", "Test", "Rationale")
        proposal = PlanProposal(action, 0.8)
        ctx = IntentContext.create_agent_intent("Test execution")
        
        result = agent.executor.execute(proposal, context=ctx)
        
        # 3. Should be denied
        assert result is None
        
        # 4. Check audit log for autonomy denial
        entries = agent.executor.audit_log.entries
        last_entry = entries[-1]
        assert "Autonomy" in last_entry.denial_reason
        assert last_entry.outcome == "denied"
        
        print(f"[SUCCESS] Executor respected autonomy freeze: {last_entry.denial_reason}")


class TestBudgetDynamics:
    
    def test_budget_regeneration(self):
        reg = AutonomyRegulator()
        
        # Consume some budget
        reg.state.execution_budget = 50
        
        # Regenerate (1.0 per minute)
        regenerated = reg.regenerate_budget(minutes_elapsed=10)
        
        assert regenerated == 10
        assert reg.state.execution_budget == 60
        
    def test_critique_penalty(self):
        reg = AutonomyRegulator()
        
        initial = reg.state.execution_budget
        penalty = reg.apply_critique_penalty(severity=0.8)
        
        assert penalty == 16  # 0.8 * 20
        assert reg.state.execution_budget == initial - penalty
        
    def test_coherence_bonus(self):
        reg = AutonomyRegulator()
        
        reg.state.execution_budget = 80
        bonus = reg.apply_coherence_bonus(coherence=0.95)
        
        assert bonus > 0  # Should get a bonus
        assert reg.state.execution_budget > 80


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
