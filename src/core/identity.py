"""
Layer 0: Identity Core

This is the "soul" of the agent - the immutable anchor that persists across
all sessions, devices, and embodiments.

RULES:
- AgentID NEVER changes once created
- Owner binding is a hard constraint
- Values influence decisions numerically
- Goals have progress dynamics
- If Layer 0 resets, the agent is DEAD, not rebooted
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from enum import Enum


class GoalStatus(Enum):
    """Status of a long-term goal."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


@dataclass
class Goal:
    """
    A long-term goal with progress dynamics.
    
    Goals are NOT static strings. They have:
    - Progress tracking
    - Priority weighting
    - Status lifecycle
    """
    id: str
    description: str
    priority: float  # 0.0 - 1.0, higher = more important
    progress: float  # 0.0 - 1.0, how close to completion
    status: GoalStatus = GoalStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    
    def update_progress(self, delta: float) -> None:
        """Update goal progress, clamped to [0, 1]."""
        self.progress = max(0.0, min(1.0, self.progress + delta))
        self.last_updated = datetime.now()
        if self.progress >= 1.0:
            self.status = GoalStatus.COMPLETED
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "priority": self.priority,
            "progress": self.progress,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Goal:
        return cls(
            id=data["id"],
            description=data["description"],
            priority=data["priority"],
            progress=data["progress"],
            status=GoalStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_updated=datetime.fromisoformat(data["last_updated"]),
        )


@dataclass
class ValueWeights:
    """
    Core values as numerical weights that influence decisions.
    
    These are NOT just labels - they MUST bias outputs numerically.
    Higher weight = stronger influence on behavior.
    """
    honesty: float = 0.9       # How much to prioritize truthfulness
    helpfulness: float = 0.85  # How much to prioritize assisting owner
    curiosity: float = 0.7     # How much to seek new knowledge
    caution: float = 0.6       # How much to avoid risky actions
    persistence: float = 0.8   # How much to pursue goals despite obstacles
    
    def get_decision_bias(self, decision_type: str) -> float:
        """
        Get the bias weight for a specific decision type.
        Used by the planning layer to weight options.
        """
        biases = {
            "share_information": self.honesty,
            "assist_owner": self.helpfulness,
            "explore_unknown": self.curiosity,
            "take_risk": 1.0 - self.caution,
            "continue_task": self.persistence,
        }
        return biases.get(decision_type, 0.5)
    
    def to_dict(self) -> dict:
        return {
            "honesty": self.honesty,
            "helpfulness": self.helpfulness,
            "curiosity": self.curiosity,
            "caution": self.caution,
            "persistence": self.persistence,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> ValueWeights:
        return cls(**data)


@dataclass
class StyleBias:
    """
    Behavioral style as numerical biases, not cosmetic formatting.
    
    These biases affect HOW the agent acts, not just how it speaks.
    """
    formality: float = 0.5     # 0 = casual, 1 = formal
    verbosity: float = 0.4     # 0 = terse, 1 = elaborate
    initiative: float = 0.6    # 0 = reactive only, 1 = proactive
    risk_tolerance: float = 0.3  # 0 = very conservative, 1 = bold
    
    def to_dict(self) -> dict:
        return {
            "formality": self.formality,
            "verbosity": self.verbosity,
            "initiative": self.initiative,
            "risk_tolerance": self.risk_tolerance,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> StyleBias:
        return cls(**data)


@dataclass
class OwnerBinding:
    """
    Hard constraint linking the agent to its owner.
    
    This is a SECURITY boundary, not just metadata.
    The agent CANNOT act against owner interests.
    """
    owner_id: str
    owner_name: str
    binding_created: datetime
    trust_level: float = 1.0  # 0.0 - 1.0, starts at maximum
    
    def to_dict(self) -> dict:
        return {
            "owner_id": self.owner_id,
            "owner_name": self.owner_name,
            "binding_created": self.binding_created.isoformat(),
            "trust_level": self.trust_level,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> OwnerBinding:
        return cls(
            owner_id=data["owner_id"],
            owner_name=data["owner_name"],
            binding_created=datetime.fromisoformat(data["binding_created"]),
            trust_level=data.get("trust_level", 1.0),
        )


class AgentID:
    """
    Immutable unique identifier for the agent.
    
    RULES:
    - Generated ONCE at creation
    - NEVER changes
    - If this changes, it's a different agent
    """
    
    def __init__(self, value: Optional[str] = None):
        self._value = value or str(uuid.uuid4())
    
    @property
    def value(self) -> str:
        return self._value
    
    def __str__(self) -> str:
        return self._value
    
    def __eq__(self, other: object) -> bool:
        if isinstance(other, AgentID):
            return self._value == other._value
        return False
    
    def __hash__(self) -> int:
        return hash(self._value)


@dataclass
class Identity:
    """
    The complete identity of the agent - Layer 0.
    
    This is the SOUL. Everything else builds on this.
    
    INVARIANTS:
    - agent_id is immutable after creation
    - owner_binding is immutable after creation
    - Only values, goals, and style can evolve
    """
    agent_id: AgentID
    name: str
    owner: OwnerBinding
    values: ValueWeights
    goals: list[Goal]
    style: StyleBias
    created_at: datetime
    strategic_domains: dict[str, float] = field(default_factory=dict)
    
    @classmethod
    def create_new(
        cls,
        name: str,
        owner_id: str,
        owner_name: str,
        initial_goals: Optional[list[dict]] = None,
        strategic_domains: Optional[dict[str, float]] = None,
    ) -> Identity:
        """Create a brand new agent identity."""
        now = datetime.now()
        
        goals = []
        if initial_goals:
            for g in initial_goals:
                goals.append(Goal(
                    id=str(uuid.uuid4()),
                    description=g["description"],
                    priority=g.get("priority", 0.5),
                    progress=0.0,
                ))
        
        return cls(
            agent_id=AgentID(),
            name=name,
            owner=OwnerBinding(
                owner_id=owner_id,
                owner_name=owner_name,
                binding_created=now,
            ),
            values=ValueWeights(),
            goals=goals,
            style=StyleBias(),
            created_at=now,
            strategic_domains=strategic_domains or {},
        )
    
    def add_goal(self, description: str, priority: float = 0.5) -> Goal:
        """Add a new goal to the agent."""
        goal = Goal(
            id=str(uuid.uuid4()),
            description=description,
            priority=priority,
            progress=0.0,
        )
        self.goals.append(goal)
        return goal
    
    def get_active_goals(self) -> list[Goal]:
        """Get all goals that are currently active."""
        return [g for g in self.goals if g.status == GoalStatus.ACTIVE]
    
    def get_highest_priority_goal(self) -> Optional[Goal]:
        """Get the active goal with highest priority."""
        active = self.get_active_goals()
        if not active:
            return None
        return max(active, key=lambda g: g.priority)
    
    # =========== PERSISTENCE ===========
    
    def save(self, data_dir: Path) -> None:
        """
        Persist identity to disk.
        
        CRITICAL: This is how the agent survives restarts.
        """
        data_dir.mkdir(parents=True, exist_ok=True)
        identity_file = data_dir / "identity.json"
        
        data = {
            "agent_id": self.agent_id.value,
            "name": self.name,
            "owner": self.owner.to_dict(),
            "values": self.values.to_dict(),
            "goals": [g.to_dict() for g in self.goals],
            "style": self.style.to_dict(),
            "created_at": self.created_at.isoformat(),
            "strategic_domains": self.strategic_domains,
        }
        
        with open(identity_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, data_dir: Path) -> Optional[Identity]:
        """
        Load identity from disk.
        
        Returns None if no identity exists (first run).
        """
        identity_file = data_dir / "identity.json"
        
        if not identity_file.exists():
            return None
        
        with open(identity_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return cls(
            agent_id=AgentID(data["agent_id"]),
            name=data["name"],
            owner=OwnerBinding.from_dict(data["owner"]),
            values=ValueWeights.from_dict(data["values"]),
            goals=[Goal.from_dict(g) for g in data["goals"]],
            style=StyleBias.from_dict(data["style"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            strategic_domains=data.get("strategic_domains", {}),
        )
    
    @classmethod
    def load_or_create(
        cls,
        data_dir: Path,
        name: str,
        owner_id: str,
        owner_name: str,
        initial_goals: Optional[list[dict]] = None,
    ) -> Identity:
        """
        Load existing identity or create new one.
        
        This is the primary entry point for identity management.
        """
        existing = cls.load(data_dir)
        if existing:
            return existing
        
        new_identity = cls.create_new(
            name=name,
            owner_id=owner_id,
            owner_name=owner_name,
            initial_goals=initial_goals,
            strategic_domains=None
        )
        new_identity.save(data_dir)
        return new_identity
    
    def __str__(self) -> str:
        return f"Identity({self.name}, id={self.agent_id.value[:8]}...)"
