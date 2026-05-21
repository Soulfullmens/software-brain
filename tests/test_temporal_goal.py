"""
Phase 14: Temporal Self-Model & Goal Pressure Verification

Proves that:
1. Timeline tracks agent life
2. Goals generate pressure
3. DecisionTrace includes temporal and goal context
"""

import pytest
from datetime import datetime, timedelta
from src.system.bootstrap import boot_agent
from src.system.intent import IntentContext
from src.cognition.belief_state import ContradictionRef

@pytest.fixture
def temp_brain_dir(tmp_path):
    path = tmp_path / "brain_data"
    path.mkdir()
    yield path


class TestAgentTimeline:
    
    def test_timeline_tracks_sessions(self, temp_brain_dir):
        agent = boot_agent(temp_brain_dir, "Temporal")
        
        # Should be session 1
        assert agent.timeline.session_count == 1
        assert agent.timeline.current_session_start is not None
        
        # Age should be positive (birth = identity created_at)
        age = agent.timeline.get_age()
        assert age >= timedelta(0)
        
        # Session duration should exist
        session_dur = agent.timeline.get_session_duration()
        assert session_dur is not None
        assert session_dur >= timedelta(0)
        
    def test_timeline_records_events(self, temp_brain_dir):
        agent = boot_agent(temp_brain_dir, "Temporal")
        
        # Boot event should be recorded
        events = agent.timeline.events
        assert len(events) >= 1
        assert events[0].category == "boot"


class TestGoalPressure:
    
    def test_goal_creation_and_pressure(self, temp_brain_dir):
        agent = boot_agent(temp_brain_dir, "Motivated")
        
        # Create a goal
        goal = agent.goals.add_goal("Learn Python", expected_value=0.8)
        assert goal.id is not None
        
        # Calculate utility
        pressure = agent.goals.calculate_utility(goal)
        assert pressure.utility_score > 0
        assert pressure.base_value <= 0.8
        
    def test_stagnating_goal_increases_pressure(self, temp_brain_dir):
        agent = boot_agent(temp_brain_dir, "Motivated")
        
        # Create goal and immediately check pressure
        # Create goal and immediately check utility
        goal = agent.goals.add_goal("Old Goal", expected_value=0.5)
        initial_pressure = agent.goals.calculate_utility(goal)
        
        # Simulate time passage by backdating creation
        goal.created_at = datetime.now() - timedelta(hours=48)
        # Urgency is currently derived from deadline, or stagnation? 
        # New engine derives urgency ONLY if deadline exists.
        # If no deadline, urgency is 0. 
        # So backdating creation without deadline WON'T increase pressure in new engine.
        # I should add a deadline to test urgency.
        goal.deadline = datetime.now() + timedelta(hours=1) # High urgency now
        
        later_pressure = agent.goals.calculate_utility(goal)
        
        # Utility should be higher due to urgency
        assert later_pressure.urgency_bonus > initial_pressure.urgency_bonus
        assert later_pressure.utility_score >= initial_pressure.utility_score


class TestTemporalDecisionTrace:
    
    def test_trace_includes_temporal_context(self, temp_brain_dir):
        agent = boot_agent(temp_brain_dir, "Tracer")
        
        # Add a contradiction to trigger decision
        c_ref = ContradictionRef(
            id="c1", belief_a="b1", belief_b="b2", urgency=0.8, blocking=True
        )
        agent.belief_state.add_contradiction(c_ref)
        
        # Add a goal
        agent.goals.add_goal("Resolve issues", expected_value=0.9)
        
        # Planner propose with context
        proposal = agent.planner.propose(
            agent.belief_state,
            timeline=agent.timeline,
            goals=agent.goals
        )
        
        assert proposal is not None
        trace = proposal.trace
        
        # Temporal fields should be populated
        assert trace.agent_age is not None
        assert trace.session_duration is not None
        
        # Goal fields should be populated
        assert len(trace.goal_pressures) == 1
        assert trace.highest_pressure_goal == "Resolve issues"
        
        print(f"[SUCCESS] Temporal Trace: age={trace.agent_age}, session={trace.session_duration}")
        print(f"[SUCCESS] Goal Pressures: {trace.goal_pressures}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
