"""
Hypothesis Layer - The reasoning engine.

This is NOT search. This is:
1. Form hypotheses BEFORE exploring
2. Track what evidence is MISSING (gaps)
3. Track what would FALSIFY each hypothesis
4. Drive recursion by gaps, not keywords
5. Generate DISCRIMINATING PROBES to tell hypotheses apart
6. Adjust confidence UP and DOWN based on evidence presence/absence
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from enum import Enum


class HypothesisStatus(Enum):
    PENDING = "pending"          # Not yet tested
    INVESTIGATING = "investigating"  # Actively gathering evidence
    SUPPORTED = "supported"      # Evidence leans toward confirmation
    REJECTED = "rejected"        # Evidence contradicts it
    CONFIRMED = "confirmed"      # Strong evidence, no contradictions


@dataclass
class EvidenceLink:
    """Links a belief to a hypothesis."""
    belief_statement: str
    relevance: str        # HOW this belief relates to the hypothesis
    supports: bool        # True = supports, False = contradicts
    strength: float       # 0.0-1.0, how strongly this evidence matters


@dataclass
class DiscriminatingProbe:
    """A specific search task that distinguishes one hypothesis from another."""
    description: str          # What we're looking for
    search_terms: List[str]   # Concrete strings to search for
    supports_hypothesis: str  # Which hypothesis this would support
    weakens_hypotheses: List[str]  # Which hypotheses this would weaken
    found: bool = False       # Has this been resolved?


@dataclass
class Hypothesis:
    """
    A hypothesis about the codebase that drives exploration.
    
    Unlike beliefs (which are observations), hypotheses are
    CLAIMS TO BE TESTED. The controller forms these BEFORE
    exploring, then seeks evidence to confirm or reject them.
    """
    statement: str
    status: HypothesisStatus = HypothesisStatus.PENDING
    confidence: float = 0.0
    
    # Evidence tracking
    supporting: List[EvidenceLink] = field(default_factory=list)
    contradicting: List[EvidenceLink] = field(default_factory=list)
    
    # Gap tracking - what we NEED but DON'T HAVE
    missing_evidence: List[str] = field(default_factory=list)
    
    # Falsifiability - what would prove this WRONG
    falsifiers: List[str] = field(default_factory=list)
    
    # Search guidance - where to look for evidence
    search_hints: List[str] = field(default_factory=list)
    
    # Absence penalty: confidence decreases when expected evidence is NOT found
    expected_but_missing: int = 0
    
    def add_support(self, belief_statement: str, relevance: str, strength: float = 0.5):
        """Add supporting evidence."""
        self.supporting.append(EvidenceLink(
            belief_statement=belief_statement,
            relevance=relevance,
            supports=True,
            strength=strength
        ))
        self._update_confidence()
    
    def add_contradiction(self, belief_statement: str, relevance: str, strength: float = 0.5):
        """Add contradicting evidence."""
        self.contradicting.append(EvidenceLink(
            belief_statement=belief_statement,
            relevance=relevance,
            supports=False,
            strength=strength
        ))
        self._update_confidence()
    
    def penalize_absence(self, description: str):
        """
        Called when expected discriminating evidence was NOT found.
        This WEAKENS the hypothesis.
        """
        self.expected_but_missing += 1
        self._update_confidence()
    
    def resolve_gap(self, gap: str):
        """Mark a gap as resolved (evidence found)."""
        if gap in self.missing_evidence:
            self.missing_evidence.remove(gap)
    
    def _update_confidence(self):
        """Update confidence based on evidence balance AND absence penalty."""
        if not self.supporting and not self.contradicting:
            self.confidence = 0.0
            self.status = HypothesisStatus.PENDING
            return
        
        # Sum of supporting strength
        support_total = sum(e.strength for e in self.supporting)
        # Sum of contradicting strength
        contra_total = sum(e.strength for e in self.contradicting)
        
        total = support_total + contra_total
        if total == 0:
            self.confidence = 0.0
            return
        
        # Net confidence: support / total
        raw_confidence = support_total / total
        
        # Penalize for unresolved gaps (0.1 per gap)
        gap_penalty = len(self.missing_evidence) * 0.1
        
        # Penalize for expected but missing evidence (0.15 per absence)
        absence_penalty = self.expected_but_missing * 0.15
        
        self.confidence = max(0.0, min(1.0, raw_confidence - gap_penalty - absence_penalty))
        
        # Update status
        if contra_total > support_total:
            self.status = HypothesisStatus.REJECTED
        elif self.confidence >= 0.8 and len(self.missing_evidence) == 0:
            self.status = HypothesisStatus.CONFIRMED
        elif self.supporting:
            self.status = HypothesisStatus.SUPPORTED
        else:
            self.status = HypothesisStatus.INVESTIGATING
    
    def get_gaps(self) -> List[str]:
        """What evidence is still missing?"""
        return self.missing_evidence.copy()
    
    def to_dict(self) -> dict:
        return {
            "statement": self.statement,
            "status": self.status.value,
            "confidence": round(self.confidence, 3),
            "num_supporting": len(self.supporting),
            "num_contradicting": len(self.contradicting),
            "num_gaps": len(self.missing_evidence),
            "gaps": self.missing_evidence[:5],
            "falsifiers": self.falsifiers[:3],
            "absence_penalty": self.expected_but_missing
        }


# ============================================================
# HYPOTHESIS GENERATION
# ============================================================

def generate_hypotheses(question: str) -> List[Hypothesis]:
    """
    Generate initial hypotheses from a question.
    Rule-based generator for MVP.
    """
    q_lower = question.lower()
    hypotheses = []
    
    # Pattern: "Which files enforce X?"
    if "which files" in q_lower and "enforce" in q_lower:
        target = _extract_target(question)
        
        hypotheses.append(Hypothesis(
            statement=f"{target} is enforced in dedicated mode/policy files",
            missing_evidence=[
                f"A file that defines {target}",
                f"Code that checks {target} before allowing operations",
                f"A default value assignment for {target}"
            ],
            falsifiers=[
                f"{target} is never checked at runtime",
                f"{target} has no default assignment"
            ],
            search_hints=["mode", "policy", "learning", "config", "default"]
        ))
        
        hypotheses.append(Hypothesis(
            statement=f"{target} is enforced via guard checks in multiple modules",
            missing_evidence=[
                f"if-statements that check {target}",
                f"Multiple files importing {target}",
                f"Blocking/gating logic tied to {target}"
            ],
            falsifiers=[
                f"Only one file references {target}",
                f"{target} is checked but never blocks anything"
            ],
            search_hints=["guard", "check", "block", "gate", "if"]
        ))
    
    # Pattern: "Under what conditions does X transition to Y?"
    elif "condition" in q_lower and ("transition" in q_lower or "change" in q_lower or "switch" in q_lower):
        parts = _extract_transition(question)
        from_state = parts.get("from", "unknown")
        to_state = parts.get("to", "unknown")
        
        # === ADVERSARIAL HYPOTHESES ===
        # These are MUTUALLY EXCLUSIVE structural claims.
        # If H1 is true, H2 and H3 must be weaker or false.
        
        hypotheses.append(Hypothesis(
            statement=f"{from_state} to {to_state} is driven by a centralized safety governor in a single authority module",
            missing_evidence=[
                "A single module that mediates ALL freeze transitions",
                "Other modules delegate to this authority rather than freezing directly",
                "A centralized _freeze() method that all paths converge to"
            ],
            falsifiers=[
                "Multiple modules call _freeze() independently without routing through a central authority",
                "More than half of _freeze() calls originate outside the primary authority module",
                "No single module consistently mediates freezes"
            ],
            search_hints=["autonomy", "_freeze", "governor", "authority", "centralized"]
        ))
        
        hypotheses.append(Hypothesis(
            statement=f"{from_state} to {to_state} is driven by distributed local triggers across multiple independent modules",
            missing_evidence=[
                "Multiple independent modules that each call _freeze() for different reasons",
                "No single authority module that all freeze paths route through",
                "At least 3 distinct modules with independent freeze logic"
            ],
            falsifiers=[
                "All _freeze() calls are routed through a single authority layer",
                "One file dominates all transition decisions",
                "Only one module ever calls _freeze() directly"
            ],
            search_hints=["_freeze", "adjustment", "recovery", "policy", "killproof", "distributed"]
        ))
        
        hypotheses.append(Hypothesis(
            statement=f"{from_state} to {to_state} is primarily initiated by manual or higher-level authorization with automated triggers as secondary",
            missing_evidence=[
                "Explicit permission or authority check before _freeze() calls",
                "Human-initiated freeze mechanism (manual freeze, operator override)",
                "Majority of freeze paths require external authorization"
            ],
            falsifiers=[
                "Majority of _freeze() calls are fully automatic with no permission check",
                "No explicit permission checks precede most freezes",
                "No manual freeze mechanism exists in the codebase"
            ],
            search_hints=["manual", "MANUAL_FREEZE", "permission", "authorize", "override", "operator"]
        ))
    
    # Pattern: "How does X work?"
    elif "how" in q_lower:
        target = _extract_target(question)
        
        hypotheses.append(Hypothesis(
            statement=f"{target} works through a dedicated class/module",
            missing_evidence=[
                f"Class or module definition for {target}",
                f"Methods/functions that implement {target} behavior",
                f"Integration points where {target} connects to other components"
            ],
            falsifiers=[
                f"{target} has no dedicated module",
                f"{target} behavior is spread across files with no clear owner"
            ],
            search_hints=[target.lower().replace(" ", "_")]
        ))
    
    # Fallback
    if not hypotheses:
        target = _extract_target(question)
        hypotheses.append(Hypothesis(
            statement=f"The answer involves {target} and its related modules",
            missing_evidence=[
                f"Definition or declaration of {target}",
                f"Usage of {target} in operational code",
                f"Constraints or rules governing {target}"
            ],
            falsifiers=[
                f"{target} does not exist in the codebase"
            ],
            search_hints=[target.lower()]
        ))
    
    return hypotheses


# ============================================================
# DISCRIMINATING PROBES
# ============================================================

def generate_discriminating_probes(hypotheses: List[Hypothesis]) -> List[DiscriminatingProbe]:
    """
    Generate probes that DISTINGUISH between hypotheses.
    
    These probes test STRUCTURAL PROPERTIES of the codebase.
    Each probe, when resolved, should strengthen one hypothesis
    and weaken at least one other.
    """
    probes = []
    
    # Only generate probes when we have competing hypotheses
    competing = [h for h in hypotheses if h.status in 
                 (HypothesisStatus.SUPPORTED, HypothesisStatus.INVESTIGATING, HypothesisStatus.PENDING)]
    
    if len(competing) < 2:
        return probes
    
    # Identify hypotheses by structural type
    centralized_h = None
    distributed_h = None
    manual_h = None
    
    for h in competing:
        stmt = h.statement.lower()
        if "centralized" in stmt or "single authority" in stmt or "governor" in stmt:
            centralized_h = h
        elif "distributed" in stmt or "multiple independent" in stmt or "local triggers" in stmt:
            distributed_h = h
        elif "manual" in stmt or "authorization" in stmt or "higher-level" in stmt:
            manual_h = h
    
    # --- STRUCTURAL PROBES ---
    # These test measurable, falsifiable properties.
    
    # Probe 1: How many distinct files call _freeze() directly?
    # If 1 -> centralized wins. If 3+ -> distributed wins.
    all_others = [h.statement for h in competing]
    if centralized_h and distributed_h:
        probes.append(DiscriminatingProbe(
            description="Count unique files that directly call _freeze() — is it 1 dominant file or many?",
            search_terms=["_freeze(", "self._freeze(", "._freeze("],
            supports_hypothesis=distributed_h.statement,
            weakens_hypotheses=[centralized_h.statement]
        ))
    
    # Probe 2: Does one module mediate all transitions?
    if centralized_h:
        probes.append(DiscriminatingProbe(
            description="Does autonomy.py act as a choke point — do other modules route through it?",
            search_terms=["autonomy._freeze", "autonomy.freeze", "self.autonomy._freeze", "import autonomy"],
            supports_hypothesis=centralized_h.statement,
            weakens_hypotheses=[distributed_h.statement] if distributed_h else []
        ))
    
    # Probe 3: Are freeze calls automatic or require permission?
    if manual_h:
        probes.append(DiscriminatingProbe(
            description="What fraction of _freeze() calls are automatic (no permission check) vs manual?",
            search_terms=["MANUAL_FREEZE", "manual_freeze", "permission", "authorize", "operator"],
            supports_hypothesis=manual_h.statement,
            weakens_hypotheses=[h.statement for h in competing if h != manual_h]
        ))
    
    # Probe 4: Do independent modules have their own freeze reasons?
    if distributed_h:
        probes.append(DiscriminatingProbe(
            description="Do multiple modules define their own independent freeze trigger conditions?",
            search_terms=["FreezeReason", "freeze_reason", "threshold", "coherence", "budget", "violation"],
            supports_hypothesis=distributed_h.statement,
            weakens_hypotheses=[centralized_h.statement] if centralized_h else []
        ))
    
    # Probe 5: Is there a FreezeReason enum with MANUAL_FREEZE?
    if manual_h and distributed_h:
        probes.append(DiscriminatingProbe(
            description="Does FreezeReason include MANUAL_FREEZE showing explicit manual freeze path?",
            search_terms=["MANUAL_FREEZE", "FreezeReason.MANUAL", "manual"],
            supports_hypothesis=manual_h.statement,
            weakens_hypotheses=[distributed_h.statement]
        ))
    
    return probes


def evaluate_probes_against_beliefs(probes: List[DiscriminatingProbe], 
                                      beliefs: dict,
                                      hypotheses: List[Hypothesis]):
    """
    Check which probes are answered by existing beliefs.
    Adjust hypothesis confidence up AND down.
    """
    hypothesis_map = {h.statement: h for h in hypotheses}
    
    for probe in probes:
        if probe.found:
            continue
        
        # Search beliefs for probe evidence
        probe_found = False
        for key, belief in beliefs.items():
            clean = _clean_belief_text(belief.statement)
            
            # Check if belief matches ANY of the probe's search terms
            matching_terms = [t for t in probe.search_terms if t.lower() in clean]
            
            if len(matching_terms) >= 2:  # Need at least 2 term matches
                probe_found = True
                probe.found = True
                
                # Strengthen the supported hypothesis
                if probe.supports_hypothesis and probe.supports_hypothesis in hypothesis_map:
                    h = hypothesis_map[probe.supports_hypothesis]
                    h.add_support(
                        belief.statement,
                        relevance=f"Discriminating probe: {probe.description}",
                        strength=belief.confidence * 0.8  # Higher weight for discriminating evidence
                    )
                
                break
        
        # If probe NOT found after searching all beliefs → penalize
        if not probe_found and probe.supports_hypothesis:
            if probe.supports_hypothesis in hypothesis_map:
                h = hypothesis_map[probe.supports_hypothesis]
                h.penalize_absence(probe.description)


# ============================================================
# CALL-SITE SEARCH
# ============================================================

def generate_callsite_targets(hypotheses: List[Hypothesis]) -> List[str]:
    """
    Extract concrete function/method names to search for call sites.
    
    Instead of vague gaps like "Conditions checked before transition",
    this produces concrete targets: ["_freeze(", "set_level(", "FROZEN"]
    """
    targets = set()
    
    for h in hypotheses:
        if h.status in (HypothesisStatus.CONFIRMED, HypothesisStatus.REJECTED):
            continue
        
        stmt = h.statement.lower()
        
        # Look for transition/freeze related hypotheses
        if "freeze" in stmt or "frozen" in stmt or "transition" in stmt:
            targets.update([
                "_freeze",
                "freeze",
                "frozen",
                "set_level",
                "freezereason",
                "_emergency_freeze",
                "manual_freeze",
                "auto_freeze",
                "min_freeze_duration",
                "freeze_reason",
                "frozen_at",
                "time_frozen",
                "bypass_freeze",
                "unfreeze",
            ])
        
        # Look for authorization related hypotheses
        if "authorization" in stmt or "authority" in stmt:
            targets.update([
                "authority",
                "permission",
                "can_freeze",
                "check_permission",
                "authorize",
                "approval",
            ])
        
        # Extract any CamelCase or UPPER terms from the statement
        for m in re.findall(r'[A-Z][a-z]+(?:[A-Z][a-z]+)+', h.statement):
            targets.add(m)
        for m in re.findall(r'[A-Z][A-Z_]{2,}', h.statement):
            targets.add(m)
    
    return list(targets)


# ============================================================
# BELIEF-HYPOTHESIS MAPPING
# ============================================================

def _extract_target(question: str) -> str:
    """Extract the main subject from a question."""
    camel = re.findall(r'[A-Z][a-z]+(?:[A-Z][a-z]+)+', question)
    if camel:
        return camel[0]
    
    quoted = re.findall(r'"([^"]+)"', question) + re.findall(r"'([^']+)'", question)
    if quoted:
        return quoted[0]
    
    upper = re.findall(r'[A-Z][A-Z_]+', question)
    if upper:
        return upper[0]
    
    stop_words = {'which', 'files', 'enforce', 'the', 'does', 'how', 'what',
                  'is', 'are', 'under', 'conditions', 'that', 'to', 'from',
                  'a', 'an', 'in', 'of', 'and', 'or', 'on', 'do', 'when'}
    words = [w for w in question.split() if w.lower() not in stop_words]
    return ' '.join(words[:3]) if words else "unknown"


def _extract_transition(question: str) -> dict:
    """Extract from/to states from a transition question."""
    match = re.search(r'from\s+(\w+)\s+to\s+(\w+)', question, re.IGNORECASE)
    if match:
        return {"from": match.group(1), "to": match.group(2)}
    
    match = re.search(r'(\w+)\s*(?:→|->)\s*(\w+)', question)
    if match:
        return {"from": match.group(1), "to": match.group(2)}
    
    states = re.findall(r'[A-Z][A-Z_]+', question)
    if len(states) >= 2:
        return {"from": states[0], "to": states[1]}
    
    return {"from": "unknown", "to": "unknown"}


def _clean_belief_text(statement: str) -> str:
    """Strip 'Code contains:' prefix and normalize for matching."""
    text = statement.lower().strip()
    if text.startswith("code contains:"):
        text = text[len("code contains:"):].strip()
    return text


def _extract_domain_terms(text: str) -> set:
    """Extract meaningful domain terms from text."""
    terms = set()
    
    for m in re.findall(r'[A-Z][a-z]+(?:[A-Z][a-z]+)+', text):
        terms.add(m.lower())
    
    for m in re.findall(r'[A-Z][A-Z_]{2,}', text):
        terms.add(m.lower())
    
    for m in re.findall(r'[a-z]+_[a-z_]+', text.lower()):
        terms.add(m)
    
    for w in text.lower().split():
        w = w.strip('(){}[],:;="\'.#')
        if len(w) > 4:
            terms.add(w)
    
    return terms


def map_beliefs_to_hypotheses(hypotheses: List[Hypothesis], beliefs: dict):
    """
    Map existing beliefs to hypotheses.
    
    Matches beliefs against:
    1. Hypothesis search hints
    2. Hypothesis gap descriptions
    3. Hypothesis statement
    4. Hypothesis falsifiers
    """
    for h in hypotheses:
        # Build hypothesis keyword set from ALL sources
        h_terms = set()
        h_terms.update(_extract_domain_terms(h.statement))
        for hint in h.search_hints:
            h_terms.add(hint.lower())
        for gap in h.missing_evidence:
            h_terms.update(_extract_domain_terms(gap))
        
        # Build falsifier terms
        falsifier_terms = set()
        for f in h.falsifiers:
            falsifier_terms.update(_extract_domain_terms(f))
        
        already_linked = {e.belief_statement for e in h.supporting}
        already_linked.update(e.belief_statement for e in h.contradicting)
        
        for key, belief in beliefs.items():
            if belief.statement in already_linked:
                continue
            
            clean_text = _clean_belief_text(belief.statement)
            b_terms = _extract_domain_terms(belief.statement)
            
            overlap = h_terms & b_terms
            
            if not overlap:
                for hint in h.search_hints:
                    if hint.lower() in clean_text:
                        overlap.add(hint)
            
            if overlap:
                falsifier_overlap = falsifier_terms & b_terms
                
                if falsifier_overlap and len(falsifier_overlap) >= 2:
                    h.add_contradiction(
                        belief.statement,
                        relevance=f"Matches falsifier terms: {falsifier_overlap}",
                        strength=belief.confidence * 0.6
                    )
                else:
                    h.add_support(
                        belief.statement,
                        relevance=f"Matching terms: {overlap}",
                        strength=belief.confidence * 0.7
                    )
                
                # Resolve gaps
                for gap in h.missing_evidence.copy():
                    gap_terms = _extract_domain_terms(gap)
                    if gap_terms & b_terms:
                        h.resolve_gap(gap)


def get_exploration_targets(hypotheses: List[Hypothesis]) -> List[str]:
    """
    Convert hypothesis gaps into search hints for chunk selection.
    Now also includes call-site targets for concrete function searches.
    """
    hints = set()
    
    for h in hypotheses:
        if h.status in (HypothesisStatus.PENDING, HypothesisStatus.INVESTIGATING,
                        HypothesisStatus.SUPPORTED):
            hints.update(h.search_hints)
            
            for gap in h.missing_evidence:
                words = gap.lower().split()
                for w in words:
                    if len(w) > 4:
                        hints.add(w)
    
    # Add concrete call-site targets
    callsite_targets = generate_callsite_targets(hypotheses)
    for t in callsite_targets:
        hints.add(t.lower())
    
    return list(hints)
