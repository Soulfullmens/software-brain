"""
Tests for Layer 0: Identity Core

These tests verify the IMMUTABLE guarantees of the identity system.
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from src.core.identity import (
    Identity,
    AgentID,
    Goal,
    GoalStatus,
    ValueWeights,
    StyleBias,
    OwnerBinding,
)


class TestAgentID:
    """Tests for the immutable AgentID."""
    
    def test_create_unique_id(self):
        """Each new AgentID should be unique."""
        id1 = AgentID()
        id2 = AgentID()
        assert id1 != id2
    
    def test_preserve_existing_id(self):
        """AgentID should preserve a given value."""
        fixed_id = "test-agent-12345"
        agent_id = AgentID(fixed_id)
        assert agent_id.value == fixed_id
    
    def test_id_equality(self):
        """Same value should be equal."""
        agent_id1 = AgentID("same-id")
        agent_id2 = AgentID("same-id")
        assert agent_id1 == agent_id2
    
    def test_id_hashable(self):
        """AgentID should be usable as dict key."""
        agent_id = AgentID("test-id")
        d = {agent_id: "value"}
        assert d[agent_id] == "value"


class TestGoal:
    """Tests for goal progress dynamics."""
    
    def test_create_goal(self):
        """Goal should be created with correct initial state."""
        goal = Goal(
            id="goal-1",
            description="Learn something new",
            priority=0.8,
            progress=0.0,
        )
        assert goal.status == GoalStatus.ACTIVE
        assert goal.progress == 0.0
    
    def test_progress_update(self):
        """Progress should update correctly."""
        goal = Goal(id="g1", description="Test", priority=0.5, progress=0.0)
        goal.update_progress(0.3)
        assert goal.progress == 0.3
    
    def test_progress_clamped(self):
        """Progress should be clamped to [0, 1]."""
        goal = Goal(id="g1", description="Test", priority=0.5, progress=0.5)
        goal.update_progress(0.7)  # Would be 1.2
        assert goal.progress == 1.0
        
        goal2 = Goal(id="g2", description="Test", priority=0.5, progress=0.2)
        goal2.update_progress(-0.5)  # Would be -0.3
        assert goal2.progress == 0.0
    
    def test_auto_complete_on_full_progress(self):
        """Goal should auto-complete when progress reaches 1.0."""
        goal = Goal(id="g1", description="Test", priority=0.5, progress=0.9)
        goal.update_progress(0.1)
        assert goal.status == GoalStatus.COMPLETED
    
    def test_goal_serialization(self):
        """Goal should serialize and deserialize correctly."""
        goal = Goal(
            id="g1",
            description="Test goal",
            priority=0.7,
            progress=0.3,
            status=GoalStatus.ACTIVE,
        )
        data = goal.to_dict()
        restored = Goal.from_dict(data)
        
        assert restored.id == goal.id
        assert restored.description == goal.description
        assert restored.priority == goal.priority
        assert restored.progress == goal.progress
        assert restored.status == goal.status


class TestValueWeights:
    """Tests for value weights that influence decisions."""
    
    def test_default_values(self):
        """Default values should be reasonable."""
        values = ValueWeights()
        assert 0.5 <= values.honesty <= 1.0
        assert 0.5 <= values.helpfulness <= 1.0
    
    def test_decision_bias(self):
        """Decision bias should use correct value weights."""
        values = ValueWeights(honesty=0.9, caution=0.8)
        
        assert values.get_decision_bias("share_information") == pytest.approx(0.9)
        assert values.get_decision_bias("take_risk") == pytest.approx(0.2)  # 1.0 - caution
    
    def test_serialization(self):
        """Values should serialize correctly."""
        values = ValueWeights(honesty=0.95, curiosity=0.6)
        data = values.to_dict()
        restored = ValueWeights.from_dict(data)
        
        assert restored.honesty == 0.95
        assert restored.curiosity == 0.6


class TestIdentity:
    """Tests for the complete identity system."""
    
    def test_create_new_identity(self):
        """Should create a valid new identity."""
        identity = Identity.create_new(
            name="TestAgent",
            owner_id="owner-123",
            owner_name="Test Owner",
        )
        
        assert identity.name == "TestAgent"
        assert identity.owner.owner_id == "owner-123"
        assert identity.agent_id is not None
    
    def test_create_with_initial_goals(self):
        """Should create identity with goals."""
        identity = Identity.create_new(
            name="TestAgent",
            owner_id="owner-123",
            owner_name="Test Owner",
            initial_goals=[
                {"description": "Goal 1", "priority": 0.9},
                {"description": "Goal 2", "priority": 0.5},
            ],
        )
        
        assert len(identity.goals) == 2
        assert identity.goals[0].priority == 0.9
    
    def test_add_goal(self):
        """Should be able to add goals after creation."""
        identity = Identity.create_new(
            name="TestAgent",
            owner_id="owner-123",
            owner_name="Test Owner",
        )
        
        goal = identity.add_goal("New goal", priority=0.7)
        assert goal in identity.goals
        assert goal.progress == 0.0
    
    def test_get_highest_priority_goal(self):
        """Should return the highest priority active goal."""
        identity = Identity.create_new(
            name="TestAgent",
            owner_id="owner-123",
            owner_name="Test Owner",
            initial_goals=[
                {"description": "Low", "priority": 0.3},
                {"description": "High", "priority": 0.9},
                {"description": "Medium", "priority": 0.5},
            ],
        )
        
        top = identity.get_highest_priority_goal()
        assert top.description == "High"
    
    def test_persistence_save_and_load(self):
        """Identity should survive save/load cycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            
            # Create and save
            original = Identity.create_new(
                name="PersistentAgent",
                owner_id="owner-456",
                owner_name="Persistent Owner",
                initial_goals=[{"description": "Survive", "priority": 1.0}],
            )
            original.save(data_dir)
            
            # Load
            loaded = Identity.load(data_dir)
            
            assert loaded is not None
            assert loaded.agent_id == original.agent_id
            assert loaded.name == original.name
            assert loaded.owner.owner_id == original.owner.owner_id
            assert len(loaded.goals) == 1
    
    def test_load_or_create_existing(self):
        """Should load existing identity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            
            # Create first
            first = Identity.create_new(
                name="First",
                owner_id="owner-1",
                owner_name="Owner 1",
            )
            first.save(data_dir)
            original_id = first.agent_id.value
            
            # Load or create should load existing
            second = Identity.load_or_create(
                data_dir=data_dir,
                name="Second",  # Different name
                owner_id="owner-2",
                owner_name="Owner 2",
            )
            
            # Should be the SAME agent
            assert second.agent_id.value == original_id
            assert second.name == "First"  # Original name preserved
    
    def test_load_or_create_new(self):
        """Should create new identity if none exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            
            identity = Identity.load_or_create(
                data_dir=data_dir,
                name="NewAgent",
                owner_id="owner-new",
                owner_name="New Owner",
            )
            
            assert identity.name == "NewAgent"
            assert (data_dir / "identity.json").exists()


class TestIdentityInvariants:
    """
    Tests for critical invariants that MUST NOT be violated.
    These are security and correctness guarantees.
    """
    
    def test_agent_id_immutable_across_saves(self):
        """AgentID must NEVER change across save/load cycles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            
            identity = Identity.create_new(
                name="Test",
                owner_id="owner",
                owner_name="Owner",
            )
            original_id = identity.agent_id.value
            
            # Save and load multiple times
            for _ in range(5):
                identity.save(data_dir)
                identity = Identity.load(data_dir)
            
            assert identity.agent_id.value == original_id
    
    def test_owner_binding_preserved(self):
        """Owner binding must be preserved exactly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            
            identity = Identity.create_new(
                name="Test",
                owner_id="secure-owner-id",
                owner_name="Secure Owner",
            )
            identity.save(data_dir)
            
            loaded = Identity.load(data_dir)
            assert loaded.owner.owner_id == "secure-owner-id"
            assert loaded.owner.owner_name == "Secure Owner"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
