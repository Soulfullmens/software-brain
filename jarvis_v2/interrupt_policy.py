"""
interrupt_policy.py — Fatigue-Aware Interrupt Decisions.

THE rule: LLM never decides to interrupt. Only deterministic logic can.

Key principles:
  - Max 2 interrupts per 15 minutes
  - After 2 dismissals → 30 min silence
  - Confidence threshold rises with fatigue
  - Show uncertainty when unsure ("not confident enough to warn, but...")
"""
import time
from typing import Dict, Optional, List
from dataclasses import dataclass, field


@dataclass
class InterruptDecision:
    """Result of an interrupt check."""
    should_interrupt: bool
    confidence: float
    reason: str
    is_soft: bool = False  # True = "not confident, but looks similar"
    silence_remaining: float = 0  # seconds until silence ends


class InterruptPolicy:
    """
    Controls when Jarvis speaks vs stays silent.
    
    The difference between useful and uninstallable:
      1st interruption = 8s context switch cost
      5th in 10 minutes = trust destruction
    """
    
    BASE_THRESHOLD = 0.80      # Minimum confidence to hard-interrupt
    SOFT_THRESHOLD = 0.50      # Minimum confidence for soft hint
    MAX_PER_15MIN = 2          # Hard cap on interruptions
    SILENCE_AFTER_DISMISS = 1800  # 30 min silence after 2 dismissals
    FATIGUE_WINDOW = 900       # 15 min window for fatigue tracking
    
    def __init__(self):
        self._recent_interrupts: List[float] = []
        self._recent_dismissals: List[float] = []
        self._silence_until: float = 0
        self._total_interrupts: int = 0
        self._total_dismissals: int = 0
        self._total_accepts: int = 0
    
    def check(self, confidence: float, severity_seconds: float) -> InterruptDecision:
        """
        Should Jarvis interrupt right now?
        
        Args:
            confidence: 0.0-1.0 how sure are we this will fail
            severity_seconds: estimated debug time saved if we're right
        
        Returns InterruptDecision with should_interrupt, reason, and soft hint flag.
        """
        now = time.time()
        
        # Silenced?
        if now < self._silence_until:
            remaining = self._silence_until - now
            if confidence >= 0.95:
                # Override silence ONLY for near-certain warnings
                return InterruptDecision(
                    should_interrupt=True,
                    confidence=confidence,
                    reason="Critical warning overrides silence"
                )
            return InterruptDecision(
                should_interrupt=False,
                confidence=confidence,
                reason=f"Silenced for {int(remaining)}s (you dismissed 2 warnings recently)",
                silence_remaining=remaining
            )
        
        # Count recent interrupts
        recent = [t for t in self._recent_interrupts if now - t < self.FATIGUE_WINDOW]
        
        # Hard cap
        if len(recent) >= self.MAX_PER_15MIN:
            if confidence >= self.SOFT_THRESHOLD:
                return InterruptDecision(
                    should_interrupt=False,
                    confidence=confidence,
                    reason="Rate limit hit, but this looks risky",
                    is_soft=True
                )
            return InterruptDecision(
                should_interrupt=False,
                confidence=confidence,
                reason="Rate limit: max interruptions reached"
            )
        
        # Fatigue multiplier: each recent interrupt raises threshold
        fatigue_factor = 1.0 + (len(recent) * 0.5)  # 1.0 → 1.5 → 2.0
        adjusted_threshold = min(self.BASE_THRESHOLD * fatigue_factor, 0.95)
        
        # Value calculation
        expected_value = confidence * severity_seconds
        annoyance_cost = 8 * fatigue_factor  # Base 8s × fatigue
        
        # Hard interrupt
        if confidence >= adjusted_threshold and expected_value > annoyance_cost * 2.0:
            return InterruptDecision(
                should_interrupt=True,
                confidence=confidence,
                reason=f"High confidence ({confidence:.0%}) + saves ~{severity_seconds}s"
            )
        
        # Soft hint (not a full interrupt — just a subtle indicator)
        if confidence >= self.SOFT_THRESHOLD:
            return InterruptDecision(
                should_interrupt=False,
                confidence=confidence,
                reason="Not confident enough to warn — but this looks similar to a past failure",
                is_soft=True
            )
        
        return InterruptDecision(
            should_interrupt=False,
            confidence=confidence,
            reason="Below threshold"
        )
    
    def record_interrupt(self):
        """Record that we showed an interrupt."""
        self._recent_interrupts.append(time.time())
        self._total_interrupts += 1
    
    def record_dismissal(self):
        """User dismissed our warning. Track fatigue."""
        now = time.time()
        self._recent_dismissals.append(now)
        self._total_dismissals += 1
        
        # Check if we should silence
        recent = [t for t in self._recent_dismissals if now - t < self.FATIGUE_WINDOW]
        if len(recent) >= 2:
            self._silence_until = now + self.SILENCE_AFTER_DISMISS
    
    def record_accept(self):
        """User found our warning useful."""
        self._total_accepts += 1
    
    def get_stats(self) -> Dict:
        """Interrupt effectiveness stats."""
        total = self._total_interrupts
        return {
            "total": total,
            "accepted": self._total_accepts,
            "dismissed": self._total_dismissals,
            "accept_rate": self._total_accepts / max(total, 1),
            "dismiss_rate": self._total_dismissals / max(total, 1),
            "is_silenced": time.time() < self._silence_until,
        }
    
    def reset_silence(self):
        """Manually un-silence."""
        self._silence_until = 0
