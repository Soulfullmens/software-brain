"""
Semantic Memory (SM)

PURPOSE: "What seems true"

Examples:
- "Owner prefers dark mode"
- "Project name is software-brain"
- "Owner's coding speed is faster than expected"

PROPERTIES:
- Confidence-based (NOT truth-based)
- Actively contradicted
- Updated, not overwritten
- Decays faster than episodic (λ = 0.05 per day)

CRITICAL RULE:
- These are BELIEFS, not facts
- They can be WRONG
- World Model decides what to believe, not this layer
"""

from __future__ import annotations

import math
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


# Default decay rate for semantic memory (per day) - faster than episodic
SEMANTIC_DECAY_RATE = 0.05

# Confidence threshold below which memory is "inactive"
INACTIVE_THRESHOLD = 0.2


@dataclass
class Fact:
    """
    A semantic memory entry representing a believed fact.
    
    IMPORTANT: This is what the agent BELIEVES to be true,
    not what IS true. Facts can be wrong.
    """
    id: str
    statement: str              # The believed fact
    confidence: float           # 0.0 - 1.0, how certain
    decay_rate: float           # λ per day
    created_at: datetime
    last_reinforced: datetime
    last_accessed: datetime
    contradiction_count: int    # Times this was contradicted
    source: str                 # Where this belief came from
    
    @classmethod
    def create(
        cls,
        statement: str,
        source: str,
        confidence: float = 0.7,
        decay_rate: float = SEMANTIC_DECAY_RATE,
    ) -> Fact:
        """Create a new fact belief."""
        now = datetime.now()
        return cls(
            id=str(uuid.uuid4()),
            statement=statement,
            confidence=confidence,
            decay_rate=decay_rate,
            created_at=now,
            last_reinforced=now,
            last_accessed=now,
            contradiction_count=0,
            source=source,
        )
    
    def is_active(self) -> bool:
        """Check if this belief is still active."""
        return self.confidence >= INACTIVE_THRESHOLD
    
    def is_reliable(self) -> bool:
        """Check if this belief is reliable (high confidence, low contradictions)."""
        return self.confidence >= 0.6 and self.contradiction_count < 3
    
    def decay(self, current_time: Optional[datetime] = None) -> float:
        """Apply exponential decay."""
        current_time = current_time or datetime.now()
        delta_days = (current_time - self.last_reinforced).total_seconds() / 86400
        self.confidence = self.confidence * math.exp(-self.decay_rate * delta_days)
        return self.confidence
    
    def reinforce(self, strength: float = 0.2) -> float:
        """Reinforce this belief (evidence supports it)."""
        self.confidence = self.confidence + strength * (1.0 - self.confidence)
        self.last_reinforced = datetime.now()
        return self.confidence
    
    def contradict(self, penalty: float = 0.2) -> float:
        """Contradict this belief (evidence against it)."""
        self.confidence = max(0.0, self.confidence - penalty)
        self.contradiction_count += 1
        return self.confidence
    
    def access(self) -> None:
        """Mark as accessed."""
        self.last_accessed = datetime.now()


class SemanticMemory:
    """
    Persistent storage for semantic memories (believed facts).
    
    These are things the agent believes to be true about the world.
    They can be wrong, contradicted, and decay over time.
    """
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS semantic_memory (
                    id TEXT PRIMARY KEY,
                    statement TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    decay_rate REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    last_reinforced TEXT NOT NULL,
                    last_accessed TEXT NOT NULL,
                    contradiction_count INTEGER NOT NULL,
                    source TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sm_confidence 
                ON semantic_memory(confidence)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sm_last_reinforced 
                ON semantic_memory(last_reinforced)
            """)
            conn.commit()
    
    def store(self, fact: Fact) -> None:
        """Store a fact to the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO semantic_memory 
                (id, statement, confidence, decay_rate,
                 created_at, last_reinforced, last_accessed,
                 contradiction_count, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fact.id,
                fact.statement,
                fact.confidence,
                fact.decay_rate,
                fact.created_at.isoformat(),
                fact.last_reinforced.isoformat(),
                fact.last_accessed.isoformat(),
                fact.contradiction_count,
                fact.source,
            ))
            conn.commit()
    
    def get(self, fact_id: str) -> Optional[Fact]:
        """Retrieve a fact by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM semantic_memory WHERE id = ?",
                (fact_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_fact(row)
        return None
    
    def find_by_content(self, search_term: str, limit: int = 10) -> list[Fact]:
        """Find facts containing the search term."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT * FROM semantic_memory 
                WHERE statement LIKE ? AND confidence >= ?
                ORDER BY confidence DESC
                LIMIT ?
            """, (f"%{search_term}%", INACTIVE_THRESHOLD, limit))
            return [self._row_to_fact(row) for row in cursor.fetchall()]
    
    def get_reliable(self, limit: int = 50) -> list[Fact]:
        """Get the most reliable facts (high confidence, low contradictions)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT * FROM semantic_memory 
                WHERE confidence >= 0.6 AND contradiction_count < 3
                ORDER BY confidence DESC
                LIMIT ?
            """, (limit,))
            return [self._row_to_fact(row) for row in cursor.fetchall()]
    
    def get_active(self, limit: int = 100) -> list[Fact]:
        """Get all active facts."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT * FROM semantic_memory 
                WHERE confidence >= ?
                ORDER BY confidence DESC
                LIMIT ?
            """, (INACTIVE_THRESHOLD, limit))
            return [self._row_to_fact(row) for row in cursor.fetchall()]
    
    def update(self, fact: Fact) -> None:
        """Update an existing fact."""
        self.store(fact)
    
    def reinforce(self, fact_id: str, strength: float = 0.2) -> Optional[Fact]:
        """Reinforce a fact by ID."""
        fact = self.get(fact_id)
        if fact:
            fact.reinforce(strength)
            self.store(fact)
        return fact
    
    def contradict(self, fact_id: str, penalty: float = 0.2) -> Optional[Fact]:
        """Contradict a fact by ID."""
        fact = self.get(fact_id)
        if fact:
            fact.contradict(penalty)
            self.store(fact)
        return fact
    
    def decay_all(self, current_time: Optional[datetime] = None) -> int:
        """Apply decay to all facts. Returns count of newly inactive facts."""
        current_time = current_time or datetime.now()
        became_inactive = 0
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM semantic_memory")
            facts = [self._row_to_fact(row) for row in cursor.fetchall()]
        
        for fact in facts:
            was_active = fact.is_active()
            fact.decay(current_time)
            if was_active and not fact.is_active():
                became_inactive += 1
            self.store(fact)
        
        return became_inactive
    
    def count_active(self) -> int:
        """Count active facts."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM semantic_memory WHERE confidence >= ?",
                (INACTIVE_THRESHOLD,)
            )
            return cursor.fetchone()[0]
    
    def count_total(self) -> int:
        """Count total facts (including inactive)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM semantic_memory")
            return cursor.fetchone()[0]
    
    def _row_to_fact(self, row: tuple) -> Fact:
        """Convert a database row to a Fact object."""
        return Fact(
            id=row[0],
            statement=row[1],
            confidence=row[2],
            decay_rate=row[3],
            created_at=datetime.fromisoformat(row[4]),
            last_reinforced=datetime.fromisoformat(row[5]),
            last_accessed=datetime.fromisoformat(row[6]),
            contradiction_count=row[7],
            source=row[8],
        )
