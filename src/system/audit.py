"""
Audit System

Immutable record of all execution attempts.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Any
from pathlib import Path
import json

from src.system.intent import IntentContext


@dataclass(frozen=True)
class AuditEntry:
    """
    A single record in the audit log.
    Includes context, action, and outcome.
    """
    timestamp: datetime
    context: IntentContext
    action_id: str
    target: Optional[str]
    allowed: bool
    denial_reason: Optional[str]
    body_id: str
    outcome: str # "success", "failed", "denied"
    decision_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "origin": self.context.origin,
            "authority": self.context.authority.name,
            "reason": self.context.reason,
            "action": self.action_id,
            "target": self.target,
            "allowed": self.allowed,
            "denial_reason": self.denial_reason,
            "body": self.body_id,
            "outcome": self.outcome,
            "decision_id": self.decision_id
        }


class AuditLog:
    """
    Append-only log of executions.
    """
    
    def __init__(self, log_path: Optional[Path] = None):
        self.entries: List[AuditEntry] = []
        self.log_path = log_path
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            
    def log(self, entry: AuditEntry):
        """Record an entry."""
        self.entries.append(entry)
        if self.log_path:
            self._persist(entry)
            
    def _persist(self, entry: AuditEntry):
        """Append to disk."""
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")
