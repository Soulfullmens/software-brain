"""
Phase 9: Identity Persistence Verification

Propoves that the agent:
1. Maintains identity across restarts
2. Remembers what it learned (Policy)
3. Remembers what happened (Memory)
"""

import pytest
import shutil
from pathlib import Path
from datetime import datetime

from src.system.bootstrap import boot_agent
from src.learning.signals import LearningSignal


@pytest.fixture
def temp_brain_dir(tmp_path):
    """Temporary directory for brain data."""
    path = tmp_path / "brain_data"
    path.mkdir()
    yield path
    # Cleanup done by tmp_path fixture usually


def test_agent_survives_reboot(temp_brain_dir):
    """
    Test the full lifecycle:
    Born -> Learns -> Dies (Save) -> Reborn (Load) -> Remembers
    """
    
    # 1. FIRST LIFE (Genesis)
    print("\n[GENESIS] Booting agent...")
    agent_v1 = boot_agent(
        data_dir=temp_brain_dir,
        agent_name="TestSubject",
        owner_id="admin"
    )
    
    id_v1 = agent_v1.identity.agent_id
    print(f"Agent Created: {id_v1}")
    
    # Check boot memory
    episodes_v1 = agent_v1.memory.get_recent_episodes(limit=10)
    assert len(episodes_v1) >= 1
    assert "System boot complete" in episodes_v1[0].content
    
    # 2. EXPERIENCE & LEARNING
    # Simulate a failure that changes policy
    initial_bias = agent_v1.learning.policy.prediction_bias
    
    # Learn from a failure signal
    signal = LearningSignal.prediction_failure(0.9, "test_source")
    agent_v1.learning.learn(signal)
    
    # Verify change
    new_bias = agent_v1.learning.policy.prediction_bias
    assert new_bias < initial_bias
    
    # 3. DEATH (Shutdown & Persistence)
    # We must explicitly save policy (Bootstrap loads it, but learning engine might not auto-save on learn)
    agent_v1.learning.save()
    
    # 4. REBIRTH (Reboot)
    print("[REBOOT] Restarting system...")
    agent_v2 = boot_agent(
        data_dir=temp_brain_dir,
        agent_name="TestSubject", # Same name/owner implies same identity logic in load_or_create
        owner_id="admin"
    )
    
    # 5. VERIFICATION
    
    # A. Identity Continuity
    assert agent_v2.identity.agent_id == id_v1
    assert agent_v2.identity.created_at == agent_v1.identity.created_at
    
    # B. Memory Continuity
    # Should have 2 boot events now (one from v1, one from v2)
    episodes_v2 = agent_v2.memory.get_recent_episodes(limit=10)
    assert len(episodes_v2) >= 2
    # Newest is first
    assert "System boot complete" in episodes_v2[0].content
    assert "System boot complete" in episodes_v2[1].content
    
    # C. Policy Continuity (Learning Persistence)
    # The bias in v2 should match the *modified* bias of v1, not the default
    assert agent_v2.learning.policy.prediction_bias == new_bias
    assert agent_v2.learning.policy.prediction_bias < initial_bias
    
    print("[SUCCESS] Agent survived reboot with Identity, Memory, and Wisdom intact.")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
