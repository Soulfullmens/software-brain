"""
Agent Timeline - Temporal Self-Model

The agent's understanding of its own existence across time.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional


@dataclass
class SignificantEvent:
    """A notable moment in the agent's life."""
    id: str
    timestamp: datetime
    category: str  # "boot", "learning", "decision", "error", "milestone"
    description: str
    importance: float  # 0.0 - 1.0


@dataclass
class AgentTimeline:
    """
    The agent's temporal self-model.
    
    Answers:
    - How long have I existed?
    - What sessions have I had?
    - What patterns recur?
    """
    
    # Birth
    created_at: datetime
    
    # Sessions
    session_count: int = 0
    current_session_start: Optional[datetime] = None
    total_uptime: timedelta = field(default_factory=lambda: timedelta(0))
    
    # Significant Events (curated, not exhaustive)
    events: List[SignificantEvent] = field(default_factory=list)
    
    # Trend Markers
    last_learning_event: Optional[datetime] = None
    last_major_decision: Optional[datetime] = None
    last_error: Optional[datetime] = None
    
    def start_session(self) -> None:
        """Mark the beginning of a new session."""
        self.session_count += 1
        self.current_session_start = datetime.now()
        self.record_event("boot", f"Session {self.session_count} started", importance=0.3)
        
    def end_session(self) -> None:
        """Mark the end of a session."""
        if self.current_session_start:
            duration = datetime.now() - self.current_session_start
            self.total_uptime += duration
            self.current_session_start = None
    
    def record_event(self, category: str, description: str, importance: float = 0.5) -> SignificantEvent:
        """Record a significant event."""
        import uuid
        event = SignificantEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            category=category,
            description=description,
            importance=importance
        )
        self.events.append(event)
        
        # Update trend markers
        if category == "learning":
            self.last_learning_event = event.timestamp
        elif category == "decision":
            self.last_major_decision = event.timestamp
        elif category == "error":
            self.last_error = event.timestamp
            
        return event
    
    def get_age(self) -> timedelta:
        """How long has the agent existed?"""
        return datetime.now() - self.created_at
    
    def get_session_duration(self) -> Optional[timedelta]:
        """How long has the current session been running?"""
        if self.current_session_start:
            return datetime.now() - self.current_session_start
        return None
    
    def get_recent_events(self, hours: int = 24, limit: int = 20) -> List[SignificantEvent]:
        """Get recent significant events."""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [e for e in self.events if e.timestamp >= cutoff][-limit:]
    
    def time_since_learning(self) -> Optional[timedelta]:
        """How long since the agent learned something?"""
        if self.last_learning_event:
            return datetime.now() - self.last_learning_event
        return None
    
    def summary(self) -> dict:
        """Summary of temporal state."""
        return {
            "age": str(self.get_age()),
            "sessions": self.session_count,
            "total_uptime": str(self.total_uptime),
            "events_recorded": len(self.events),
            "time_since_learning": str(self.time_since_learning()) if self.last_learning_event else "never"
        }
