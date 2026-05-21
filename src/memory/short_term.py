"""
Short-Term Memory (STM)

PURPOSE: Working context

RULES:
- Lives in RAM only
- Limited size (configurable, default 50)
- No decay (dies on shutdown)
- Cleared between sessions
- NEVER persisted

USED BY:
- Reasoning context
- Planning window
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from collections import deque


@dataclass
class STMEntry:
    """A single entry in short-term memory."""
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


class ShortTermMemory:
    """
    In-memory working context.
    
    This is NOT persisted. It dies when the process ends.
    That's intentional - STM is for immediate context only.
    """
    
    def __init__(self, max_size: int = 50):
        self._max_size = max_size
        self._buffer: deque[STMEntry] = deque(maxlen=max_size)
        self._working_facts: dict[str, Any] = {}
        self._attention_focus: list[str] = []
    
    def add(self, content: str, metadata: Optional[dict] = None) -> STMEntry:
        """Add an entry to short-term memory."""
        entry = STMEntry(
            content=content,
            metadata=metadata or {},
        )
        self._buffer.append(entry)
        return entry
    
    def get_recent(self, n: int = 10) -> list[STMEntry]:
        """Get the n most recent entries."""
        return list(self._buffer)[-n:]
    
    def get_all(self) -> list[STMEntry]:
        """Get all entries in order."""
        return list(self._buffer)
    
    def set_working_fact(self, key: str, value: Any) -> None:
        """Set a working fact for current context."""
        self._working_facts[key] = value
    
    def get_working_fact(self, key: str) -> Optional[Any]:
        """Get a working fact."""
        return self._working_facts.get(key)
    
    def set_attention(self, topics: list[str]) -> None:
        """Set current attention focus topics."""
        self._attention_focus = topics
    
    def get_attention(self) -> list[str]:
        """Get current attention focus topics."""
        return self._attention_focus.copy()
    
    def clear(self) -> None:
        """Clear all short-term memory. Called on session end."""
        self._buffer.clear()
        self._working_facts.clear()
        self._attention_focus.clear()
    
    def __len__(self) -> int:
        return len(self._buffer)
