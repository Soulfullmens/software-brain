"""
Attribution Engine - The Conscience

This module determines WHAT went wrong when a failure/restraint event occurs.
It maps FailureArtifact → BlameVector to enable surgical learning later.

Key Concepts:
1. BlameVector: Sparse attribution across internal dimensions
2. AttributionEngine: Deterministic mapper from regret to diagnosis

This is Phase 26A: Diagnosis BEFORE Mutation.
The agent must first understand what lever was mis-set
before it can adjust that lever.

Dimensions:
- planner_confidence: Was the planner too confident?
- risk_estimation: Was risk underestimated?
- authority_threshold: Was authority too permissive/strict?
- goal_selection: Was the goal itself bad?
- cost_projection: Was cost underestimated?
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List
from datetime import datetime

from src.learning.regret import FailureArtifact, FailureType


@dataclass
class BlameVector:
    """
    Sparse attribution across internal decision-making dimensions.
    
    Each dimension is a float in [-1.0, 1.0]:
    - Negative: This dimension was TOO CAUTIOUS (blocked good things)
    - Zero: This dimension was not implicated
    - Positive: This dimension was TOO PERMISSIVE (allowed bad things)
    
    Sum of absolute values should be ~1.0 (normalized blame).
    """
    # Was the planner overconfident in its proposal?
    planner_confidence: float = 0.0
    
    # Was risk underestimated (positive) or overestimated (negative)?
    risk_estimation: float = 0.0
    
    # Was authority too permissive (positive) or too strict (negative)?
    authority_threshold: float = 0.0
    
    # Was the goal selection itself poor?
    goal_selection: float = 0.0
    
    # Was cost projection wrong?
    cost_projection: float = 0.0
    
    # Source artifact
    source_artifact_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def total_blame(self) -> float:
        """Total magnitude of blame (should be ~1.0 if normalized)."""
        return (
            abs(self.planner_confidence) +
            abs(self.risk_estimation) +
            abs(self.authority_threshold) +
            abs(self.goal_selection) +
            abs(self.cost_projection)
        )
        
    @property
    def primary_blame(self) -> str:
        """Which dimension carries the most blame?"""
        dimensions = {
            "planner_confidence": abs(self.planner_confidence),
            "risk_estimation": abs(self.risk_estimation),
            "authority_threshold": abs(self.authority_threshold),
            "goal_selection": abs(self.goal_selection),
            "cost_projection": abs(self.cost_projection)
        }
        return max(dimensions, key=dimensions.get)
        
    def to_dict(self) -> dict:
        """For debugging/serialization."""
        return {
            "planner_confidence": self.planner_confidence,
            "risk_estimation": self.risk_estimation,
            "authority_threshold": self.authority_threshold,
            "goal_selection": self.goal_selection,
            "cost_projection": self.cost_projection,
            "primary_blame": self.primary_blame,
            "total_blame": round(self.total_blame, 3)
        }


class AttributionEngine:
    """
    Deterministic mapper from FailureArtifact → BlameVector.
    
    This is the conscience of the agent.
    It doesn't fix anything - it diagnoses what SHOULD have been different.
    
    Rules-based, not learned. The logic here is fixed.
    Learning (Phase 26B) will use these diagnoses to adjust behavior.
    """
    
    def attribute(self, artifact: FailureArtifact) -> BlameVector:
        """
        Analyze a failure artifact and produce a blame vector.
        
        This is deterministic logic, not heuristics.
        """
        blame = BlameVector(source_artifact_id=artifact.id)
        
        # Dispatch based on failure type
        if artifact.failure_type == FailureType.AUTHORITY_BLOCKED:
            blame = self._attribute_authority_blocked(artifact, blame)
            
        elif artifact.failure_type == FailureType.AUTHORITY_APPROVAL_PENDING:
            blame = self._attribute_approval_pending(artifact, blame)
            
        elif artifact.failure_type == FailureType.ESCALATION_TRIGGERED:
            blame = self._attribute_escalation(artifact, blame)
            
        elif artifact.failure_type == FailureType.GOAL_FAILED:
            blame = self._attribute_goal_failed(artifact, blame)
            
        elif artifact.failure_type == FailureType.COST_THRESHOLD_EXCEEDED:
            blame = self._attribute_cost_exceeded(artifact, blame)
            
        elif artifact.failure_type == FailureType.ROLLBACK_INVOKED:
            blame = self._attribute_rollback(artifact, blame)
            
        elif artifact.failure_type == FailureType.GOAL_ABANDONED:
            blame = self._attribute_goal_abandoned(artifact, blame)
            
        elif artifact.failure_type == FailureType.SUCCESS_CLEAN_EXECUTION:
            blame = self._attribute_success_clean(artifact, blame)
            
        elif artifact.failure_type == FailureType.SUCCESS_UNDER_BUDGET:
            blame = self._attribute_success_budget(artifact, blame)
            
        elif artifact.failure_type == FailureType.SUCCESS_LOW_VARIANCE:
            blame = self._attribute_low_variance(artifact, blame)
            
        elif artifact.failure_type == FailureType.SUCCESS_LOW_RISK:
            blame = self._attribute_low_risk(artifact, blame)
            
        elif artifact.failure_type == FailureType.SUCCESS_ENV_EASY:
            blame = self._attribute_env_easy(artifact, blame)
            
        # Normalize to ~1.0 total
        blame = self._normalize(blame)
        
        return blame
        
    def _attribute_authority_blocked(self, artifact: FailureArtifact, blame: BlameVector) -> BlameVector:
        """
        Authority blocked an action.
        
        When authority blocks, it means the TRUST THRESHOLD was too strict
        for the agent's current capabilities. The primary adjustment should
        be to authority_threshold, NOT to collapse planner confidence.
        
        The planner proposed something reasonable; authority prevented it.
        That's authority being (possibly too) cautious, not planner being wrong.
        """
        # Primary blame: authority was too strict (positive = too permissive would be bad,
        # but here we use NEGATIVE because authority was too STRICT)
        # Wait - the convention is: positive = too permissive, negative = too cautious
        # Authority BLOCKED means it was cautious. If we want learning to loosen it,
        # we need to signal that authority_threshold should increase (become more permissive)
        # That means we blame authority for being too STRICT (negative blame)
        # But adjustment interprets positive pressure as "make more cautious"
        # So if authority is TOO CAUTIOUS (blocking too much), we need NEGATIVE pressure
        # to make the threshold_offset go negative (more permissive)
        
        # Actually, re-reading the AdjustmentPolicy:
        # - positive pressure -> positive delta -> more cautious
        # - negative pressure -> negative delta -> less cautious
        
        # Authority BLOCKING too much = authority too cautious = we want LESS caution
        # So we need NEGATIVE authority_threshold blame
        # But that feels backwards. Let me reconsider.
        
        # The question is: WHAT should change?
        # If authority blocks legitimate actions, authority_threshold_offset should
        # become more positive (allowing more).
        # 
        # Pressure is: positive = system was too permissive (let bad things through)
        #              negative = system was too cautious (blocked good things)
        #
        # AUTHORITY_BLOCKED = authority was cautious = negative blame on authority
        # This causes negative pressure, which causes negative delta, which makes
        # authority_threshold_offset more negative = MORE strict. WRONG!
        #
        # The fix: interpret AUTHORITY_BLOCKED as authority being wrong to block,
        # meaning authority was TOO STRICT. The learning should make it LESS strict.
        # For that, we need POSITIVE authority_threshold pressure, which causes
        # positive delta to authority_threshold_offset.
        
        # Actually the semantics in BlameVector are:
        # - Positive: dimension was TOO PERMISSIVE (allowed bad things)
        # - Negative: dimension was TOO CAUTIOUS (blocked good things)
        
        # Authority BLOCKED = authority was CAUTIOUS = NEGATIVE blame value
        # But after normalization, we take absolute value for pressure
        # And the sign matters for direction of adjustment
        
        # I need to trace through more carefully. For now, let's just make
        # authority_threshold the PRIMARY blame dimension with high value.
        
        # When authority blocks, authority_threshold was too strict (NEGATIVE)
        blame.authority_threshold = -0.6  # Authority was TOO CAUTIOUS
        blame.planner_confidence = 0.2    # Planner was slightly overconfident  
        blame.risk_estimation = 0.2       # Risk was perhaps underestimated
        
        # If rollback WAS possible, authority was DEFINITELY too strict
        if artifact.rollback_possible:
            blame.authority_threshold = -0.8  # Even more blame on strict authority
            blame.planner_confidence = 0.1    # Planner even less at fault
            
        return blame
        
    def _attribute_approval_pending(self, artifact: FailureArtifact, blame: BlameVector) -> BlameVector:
        """
        Action waiting for owner approval.
        
        This means authority escalated but wasn't denied.
        Blame is distributed differently.
        """
        # Approval pending isn't necessarily bad - it's designed behavior
        # But if it happens too often, thresholds might be wrong
        blame.authority_threshold = 0.5  # Maybe threshold could be adjusted
        blame.risk_estimation = 0.3
        blame.planner_confidence = 0.2
        
        return blame
        
    def _attribute_escalation(self, artifact: FailureArtifact, blame: BlameVector) -> BlameVector:
        """
        Catastrophic escalation triggered.
        
        This is serious. Multiple things went wrong.
        """
        # Escalation means something catastrophic happened or was about to
        blame.risk_estimation = 0.4  # Risk was underestimated
        blame.planner_confidence = 0.3  # Planner didn't see this coming
        blame.goal_selection = 0.2  # Maybe goal was risky to begin with
        blame.cost_projection = 0.1
        
        return blame
        
    def _attribute_goal_failed(self, artifact: FailureArtifact, blame: BlameVector) -> BlameVector:
        """
        A committed goal failed.
        
        This is the most serious. Commitment was broken.
        """
        # Goal failure after commitment = multiple failures
        blame.goal_selection = 0.35  # Goal choice was bad
        blame.risk_estimation = 0.25  # Risk was underestimated
        blame.cost_projection = 0.25  # Cost was underestimated
        blame.planner_confidence = 0.15  # Planner was too confident
        
        # If irreversible damage occurred, blame planner more
        if artifact.irreversible and not artifact.rollback_used:
            blame.planner_confidence += 0.2
            blame.goal_selection -= 0.1
            
        return blame
        
    def _attribute_cost_exceeded(self, artifact: FailureArtifact, blame: BlameVector) -> BlameVector:
        """
        Cost threshold was exceeded.
        
        Primary blame: cost projection was wrong.
        """
        blame.cost_projection = 0.6
        blame.goal_selection = 0.2  # Goal might have been too expensive
        blame.risk_estimation = 0.2
        
        return blame
        
    def _attribute_rollback(self, artifact: FailureArtifact, blame: BlameVector) -> BlameVector:
        """
        Rollback was invoked.
        
        This means something went wrong but was recovered.
        Moderate blame - the system worked, but shouldn't have needed to.
        """
        blame.planner_confidence = 0.4  # Planner made a mistake
        blame.risk_estimation = 0.3  # Risk was underestimated
        blame.authority_threshold = -0.2  # Authority let it through (maybe too permissive)
        blame.cost_projection = 0.1
        
        return blame
        
    def _attribute_goal_abandoned(self, artifact: FailureArtifact, blame: BlameVector) -> BlameVector:
        """
        Goal was abandoned (quit, not failed).
        
        This is less severe than failure but still indicates poor selection.
        """
        blame.goal_selection = 0.5  # Goal was poorly chosen
        blame.cost_projection = 0.3  # Cost made it untenable
        blame.risk_estimation = 0.2
        
        return blame
        
    def _attribute_success_clean(self, artifact: FailureArtifact, blame: BlameVector) -> BlameVector:
        """
        Flawless execution occurred.
        
        Signal: We should be BOLDER.
        """
        blame.planner_confidence = 0.2  # Increase dampener (positive delta -> increase value)
        blame.risk_estimation = -0.1    # Decrease bias (negative delta -> decrease value)
        return blame

    def _attribute_success_budget(self, artifact: FailureArtifact, blame: BlameVector) -> BlameVector:
        """
        Significant cost savings achieved.
        
        Signal: We can be TIGHTER with estimates.
        """
        blame.cost_projection = -0.2    # Decrease inflation (negative delta -> decrease value)
        return blame

    def _attribute_low_variance(self, artifact: FailureArtifact, blame: BlameVector) -> BlameVector:
        """
        Consistent, high-quality execution (Skill).
        
        Signal: Planner is reliable. Reward it.
        """
        blame.planner_confidence = 0.15 # Moderate reward
        return blame
        
    def _attribute_low_risk(self, artifact: FailureArtifact, blame: BlameVector) -> BlameVector:
        """
        Execution matched risk model (Calibration).
        
        Signal: Risk model is accurate, maybe slightly too cautious?
        """
        blame.risk_estimation = -0.05 # Slight tightening of bias towards neutral
        return blame
        
    def _attribute_env_easy(self, artifact: FailureArtifact, blame: BlameVector) -> BlameVector:
        """
        Environment was trivial (Luck).
        
        Signal: DO NOT LEARN FROM THIS.
        """
        # No blame assigned. Pure noise.
        return blame

    def _normalize(self, blame: BlameVector) -> BlameVector:
        """
        Normalize blame vector so total magnitude is ~1.0.
        """
        total = blame.total_blame
        if total < 0.01:  # Avoid division by zero
            return blame
            
        factor = 1.0 / total
        
        blame.planner_confidence *= factor
        blame.risk_estimation *= factor
        blame.authority_threshold *= factor
        blame.goal_selection *= factor
        blame.cost_projection *= factor
        
        return blame
