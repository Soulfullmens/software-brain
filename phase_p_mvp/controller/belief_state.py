"""
Belief State - The actual intelligence.

This is NOT a list of facts. This is:
1. Aggregated beliefs with confidence from multiple sources
2. Conflict detection when sources disagree
3. Evidence-based confidence updates (not max())
4. Support for hypothesis testing
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from enum import Enum
import math

class BeliefStatus(Enum):
    UNCONFIRMED = "unconfirmed"  # Initial state, weak evidence
    SUPPORTED = "supported"      # Multiple sources agree
    CONFLICTED = "conflicted"    # Sources disagree
    CONFIRMED = "confirmed"      # High confidence, strong evidence

@dataclass
class Evidence:
    """A single piece of evidence supporting or contradicting a belief."""
    source: str           # chunk_id
    claim: str            # The actual claim text
    confidence: float     # Worker's confidence in this claim
    evidence_text: str    # Raw code/text that supports this
    supports: bool = True # True = supports belief, False = contradicts

@dataclass
class Belief:
    """A belief about the codebase with aggregated evidence."""
    statement: str
    confidence: float = 0.0
    status: BeliefStatus = BeliefStatus.UNCONFIRMED
    evidence: List[Evidence] = field(default_factory=list)
    contradictions: List[Evidence] = field(default_factory=list)
    sources: Set[str] = field(default_factory=set)
    
    def update_confidence(self):
        """
        Calculate confidence using evidence fusion.
        Formula: 1 - Π(1 - evidence_confidence) for supporting evidence
        Penalized by contradictions.
        """
        if not self.evidence:
            self.confidence = 0.0
            return
        
        # Combine supporting evidence
        # confidence = 1 - (1 - c1)(1 - c2)...(1 - cn)
        combined = 1.0
        for e in self.evidence:
            combined *= (1.0 - e.confidence)
        
        base_confidence = 1.0 - combined
        
        # Penalize for contradictions
        if self.contradictions:
            # Each contradiction reduces confidence
            penalty = 0.0
            for c in self.contradictions:
                penalty += c.confidence * 0.3  # 30% penalty per contradiction
            base_confidence = max(0.0, base_confidence - penalty)
        
        # Boost for independent sources
        num_sources = len(self.sources)
        if num_sources > 1:
            # Multiple sources slightly boost confidence
            base_confidence = min(0.95, base_confidence + (num_sources - 1) * 0.05)
        
        self.confidence = round(base_confidence, 3)
        
        # Update status
        if self.contradictions:
            self.status = BeliefStatus.CONFLICTED
        elif self.confidence >= 0.8:
            self.status = BeliefStatus.CONFIRMED
        elif self.confidence >= 0.5:
            self.status = BeliefStatus.SUPPORTED
        else:
            self.status = BeliefStatus.UNCONFIRMED

class BeliefState:
    """
    The belief state of the controller.
    Maintains aggregated beliefs, handles evidence fusion, detects conflicts.
    """
    
    def __init__(self):
        self.beliefs: Dict[str, Belief] = {}  # key = normalized statement
        self.all_sources: Set[str] = set()
        self.conflict_count: int = 0
    
    def _normalize_statement(self, statement: str) -> str:
        """Normalize a statement for comparison."""
        # Simple normalization: lowercase, strip, remove extra spaces
        return ' '.join(statement.lower().strip().split())
    
    def _find_similar_belief(self, statement: str) -> Optional[str]:
        """Find an existing belief that's similar to this statement."""
        normalized = self._normalize_statement(statement)
        
        # Exact match
        if normalized in self.beliefs:
            return normalized
        
        # Check for partial overlap (simple heuristic)
        words = set(normalized.split())
        for key in self.beliefs:
            key_words = set(key.split())
            overlap = len(words & key_words) / max(len(words), len(key_words))
            if overlap > 0.7:  # 70% word overlap
                return key
        
        return None
    
    def add_evidence(self, source: str, claim: dict, supports_existing: Optional[str] = None):
        """
        Add evidence to the belief state.
        
        Args:
            source: chunk_id
            claim: dict with statement, evidence, confidence, claim_type
            supports_existing: if provided, this evidence supports/contradicts this belief
        """
        self.all_sources.add(source)
        
        statement = claim.get("statement", str(claim))
        evidence_text = claim.get("evidence", "")
        confidence = claim.get("confidence", 0.5)
        
        evidence = Evidence(
            source=source,
            claim=statement,
            confidence=confidence,
            evidence_text=evidence_text,
            supports=True
        )
        
        # Find or create belief
        similar_key = self._find_similar_belief(statement)
        
        if similar_key:
            belief = self.beliefs[similar_key]
            # Check if this is supporting or contradicting
            # Simple heuristic: if same source, it's additional evidence
            # If different source says similar thing, it's corroboration
            belief.evidence.append(evidence)
            belief.sources.add(source)
            belief.update_confidence()
        else:
            # New belief
            normalized = self._normalize_statement(statement)
            belief = Belief(
                statement=statement,
                evidence=[evidence],
                sources={source}
            )
            belief.update_confidence()
            self.beliefs[normalized] = belief
    
    def add_contradiction(self, source: str, claim: dict, contradicts: str):
        """Add evidence that contradicts an existing belief."""
        normalized_contradicts = self._normalize_statement(contradicts)
        
        if normalized_contradicts not in self.beliefs:
            return
        
        belief = self.beliefs[normalized_contradicts]
        
        contradiction = Evidence(
            source=source,
            claim=claim.get("statement", str(claim)),
            confidence=claim.get("confidence", 0.5),
            evidence_text=claim.get("evidence", ""),
            supports=False
        )
        
        belief.contradictions.append(contradiction)
        belief.update_confidence()
        self.conflict_count += 1
    
    def get_overall_confidence(self) -> float:
        """Get overall confidence across all beliefs."""
        if not self.beliefs:
            return 0.0
        
        # Average confidence weighted by evidence count
        total_weight = 0
        weighted_confidence = 0.0
        
        for belief in self.beliefs.values():
            weight = len(belief.evidence)
            weighted_confidence += belief.confidence * weight
            total_weight += weight
        
        if total_weight == 0:
            return 0.0
        
        return round(weighted_confidence / total_weight, 3)
    
    def get_top_beliefs(self, n: int = 5) -> List[Belief]:
        """Get top N beliefs by confidence."""
        sorted_beliefs = sorted(
            self.beliefs.values(),
            key=lambda b: (b.confidence, len(b.evidence)),
            reverse=True
        )
        return sorted_beliefs[:n]
    
    def get_conflicts(self) -> List[Belief]:
        """Get all beliefs that have conflicts."""
        return [b for b in self.beliefs.values() if b.status == BeliefStatus.CONFLICTED]
    
    def to_dict(self) -> dict:
        """Serialize belief state for logging."""
        return {
            "num_beliefs": len(self.beliefs),
            "num_sources": len(self.all_sources),
            "conflict_count": self.conflict_count,
            "overall_confidence": self.get_overall_confidence(),
            "top_beliefs": [
                {
                    "statement": b.statement[:100],
                    "confidence": b.confidence,
                    "status": b.status.value,
                    "num_evidence": len(b.evidence),
                    "num_contradictions": len(b.contradictions)
                }
                for b in self.get_top_beliefs(5)
            ]
        }
    
    def synthesize_answer(self) -> dict:
        """
        Synthesize a final answer from beliefs.
        Returns high-confidence beliefs as facts, low-confidence as uncertainties.
        """
        facts = []
        uncertainties = []
        conflicts = []
        
        for belief in self.beliefs.values():
            if belief.status == BeliefStatus.CONFIRMED:
                facts.append({
                    "statement": belief.statement,
                    "confidence": belief.confidence,
                    "sources": list(belief.sources)
                })
            elif belief.status == BeliefStatus.CONFLICTED:
                conflicts.append({
                    "statement": belief.statement,
                    "confidence": belief.confidence,
                    "num_supporting": len(belief.evidence),
                    "num_contradicting": len(belief.contradictions)
                })
            elif belief.status == BeliefStatus.SUPPORTED:
                facts.append({
                    "statement": belief.statement,
                    "confidence": belief.confidence,
                    "sources": list(belief.sources)
                })
            else:  # UNCONFIRMED
                uncertainties.append({
                    "statement": belief.statement,
                    "confidence": belief.confidence
                })
        
        return {
            "facts": facts,
            "uncertainties": uncertainties,
            "conflicts": conflicts,
            "overall_confidence": self.get_overall_confidence()
        }
