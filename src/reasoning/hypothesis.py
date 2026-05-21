"""
hypothesis.py

Core Hypothesis Data Structure (Phase R Edition).
Represents a belief that can be tested.
"""
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

class HypothesisStatus(Enum):
    PENDING = "pending"
    TESTING = "testing"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    STALLED = "stalled"

@dataclass
class Hypothesis:
    statement: str
    confidence: float = 0.5
    status: HypothesisStatus = HypothesisStatus.PENDING
    
    # Evidence chains
    missing_evidence: List[str] = field(default_factory=list)
    falsifiers: List[str] = field(default_factory=list)
    search_hints: List[str] = field(default_factory=list)
    
    # Metadata
    source: str = "unknown"
    _is_synthetic: bool = False
