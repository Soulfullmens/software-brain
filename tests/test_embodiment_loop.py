"""
Phase 10: Embodiment Loop Verification

Tests that the agent can:
1. Propose an action (Intent)
2. Execute it via a Body (Effect)
3. Perceive the result (Feedback)
"""

import pytest
from src.system.bootstrap import boot_agent
from src.agency.action import Action, PlanProposal
from src.cognition.integration import integrate_claim
from src.system.intent import IntentContext


@pytest.fixture
def temp_brain_dir(tmp_path):
    path = tmp_path / "brain_data"
    path.mkdir()
    yield path


def test_embodiment_loop_execution_feedback(temp_brain_dir):
    """
    Verify the full action loop:
    Intent -> Execution -> Feedback -> Perception -> Belief
    """
    
    # 1. BOOT
    agent = boot_agent(temp_brain_dir, "Walker")
    
    # 2. PROPOSE ACTION (Simulated Planner Output)
    # We force a proposal that the body CAN execute.
    # ConsoleBody supports 'generate_prediction'.
    action = Action(
        id="generate_prediction",
        description="Test prediction generation",
        rationale="Testing loop",
        target="test_target_1"
    )
    proposal = PlanProposal(action=action, confidence=0.9)
    
    # 3. EXECUTE (Executor -> Body)
    print(f"\n[INTENT] Executing action: {action.id}")
    ctx = IntentContext.create_agent_intent("Loop Test Verification")
    feedback_event = agent.executor.execute(proposal, context=ctx)
    
    # 4. VERIFY FEEDBACK (Body -> InputEvent)
    assert feedback_event is not None
    assert feedback_event.source == agent.body.embodiment_id
    assert feedback_event.payload["type"] == "entity"
    assert feedback_event.payload["target_id"] == "test_target_1"
    
    print(f"[FEEDBACK] Received event from {feedback_event.source}")
    
    # 5. PERCEIVE (InputEvent -> Claim)
    claims = agent.perceiver.perceive(feedback_event)
    assert len(claims) == 1
    claim = claims[0]
    assert claim.target_id == "test_target_1"
    assert "executed successfully" in claim.content
    
    # 6. INTEGRATE (Claim -> Belief)
    # This closes the cognitive loop.
    integrate_claim(agent.belief_state, claim)
    
    # Verify belief exists
    entity = agent.belief_state.get_entity("test_target_1")
    assert entity is not None
    # Confidence is 0.5 because 'console_v0' is an untrusted source by default
    assert entity.confidence >= 0.5
    
    print("[SUCCESS] Action executed and result integrated into belief state.")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
