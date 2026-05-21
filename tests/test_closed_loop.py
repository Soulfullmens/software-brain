"""
Phase 8.2: Closed Loop Verification

This test proves the system is "alive" by verifying the complete cycle:
Input -> Perception -> Belief -> Prediction -> Verification -> Learning

No new logic is introduced here. This is pure wiring verification.
"""

import pytest
from datetime import datetime, timedelta

from src.perception.input_event import InputEvent
from src.perception.text_perceiver import TextPerceiver
from src.cognition.belief_state import BeliefState
from src.cognition.integration import integrate_claim
from src.cognition.prediction_manager import PredictionManager
from src.learning.learning_engine import LearningEngine
from src.learning.policy import LearningPolicy


def test_closed_loop_prediction_failure_learns():
    """
    Scenario: The system learns from being wrong.
    
    1. Owner asserts an entity exists (Input -> Perception -> Belief)
    2. System creates a prediction about it (Prediction)
    3. Reality contradicts prediction (Resolution -> Signal)
    4. Learning engine consumes signal (Learning)
    5. Policy is updated (Adaptation)
    """
    
    # 0. Initialize components
    # We use a shared policy state if integration needs to read it
    # LearningEngine owns the policy.
    learner = LearningEngine()
    
    # Integration needs to read the policy
    # PredictionManager needs state
    state = BeliefState.create_empty()
    pm = PredictionManager(state)
    perceiver = TextPerceiver()
    
    # 1. Input: owner asserts entity
    event = InputEvent(
        source="owner",
        modality="text",
        timestamp=datetime.now(),
        payload={
            "type": "entity",
            "target_id": "e_box",
            "confidence": 0.9,
            "content": "Box exists",
            "entity_type": "object"
        }
    )

    # PERCEPTION
    claims = perceiver.perceive(event)
    assert len(claims) == 1
    
    # INTEGRATION (using learner's policy)
    integrate_claim(state, claims[0], learner.policy)
    
    assert state.entity_count() == 1
    assert state.get_entity("e_box").confidence > 0.4
    
    # 2. PREDICTION (Manually created for now, Planner would do this in Layer 7)
    pred = pm.create_prediction(
        statement="Box will still exist",
        probability=0.9,
        expected_by=datetime.now() + timedelta(minutes=1)
    )
    
    initial_bias = learner.policy.prediction_bias
    
    # 3. REALITY CONTRADICTS (Resolution)
    # Use PredictionManager to resolve as denied
    # This emits a LearningSignal
    success, signal = pm.resolve_prediction(pred.id, "denied")
    
    assert success
    assert signal is not None
    assert signal.type == "prediction_failure"
    assert signal.magnitude == 0.9
    
    # 4. LEARNING
    learner.learn(signal)
    
    # 5. ADAPTATION
    # Bias should be lowered (became more conservative)
    assert learner.policy.prediction_bias < initial_bias
    
    # Verify exact drop: 0.9 * 0.05 = 0.045
    expected_bias = initial_bias - (0.9 * 0.05)
    assert learner.policy.prediction_bias == pytest.approx(expected_bias)
    
    print("\n[SUCCESS] Closed loop verified: Failure -> Adaptation occurred.")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
