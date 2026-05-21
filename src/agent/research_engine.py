"""
research_engine.py

Stanford PhD-Level Research Engine — 9-Protocol Pipeline.

This module implements a structured research pipeline that forces
the agent to think like a Stanford PhD student when analyzing
any body of literature or research topic.

The 9 protocols are:
  1. Intake Protocol          — catalog, cluster, flag contradictions
  2. Contradiction Finder     — deep contradiction analysis
  3. Citation Chain           — trace intellectual history
  4. Gap Scanner              — identify research gaps
  5. Methodology Audit        — compare methods across papers
  6. Master Synthesis         — unified field overview
  7. Assumption Killer        — challenge hidden assumptions
  8. Knowledge Map Builder    — structured map of the field
  9. 'So What' Test           — plain-English impact summary

Usage:
    from src.agent.research_engine import ResearchEngine

    engine = ResearchEngine(llm_router)
    # Full 9-protocol analysis
    report = engine.deep_research("quantum computing error correction", sources=[...])
    # Quick 3-protocol (Intake + Synthesis + So What)
    brief = engine.quick_research("transformer architectures", sources=[...])
"""

import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from .llm_router import LLMRouter, LLMRequest, Message, Role


# ────────────────────────────────────────────────────────
#  Research Protocol Definitions
# ────────────────────────────────────────────────────────

PROTOCOLS = {
    "intake": {
        "name": "Intake Protocol",
        "number": 1,
        "system": (
            "You are a Stanford PhD-level research analyst performing the INTAKE PROTOCOL.\n\n"
            "Given a set of papers/sources on a topic, you MUST:\n\n"
            "1. CATALOG TABLE: List every source in a table:\n"
            "   | Author(s) | Year | Core Claim (≤20 words) |\n"
            "   If no explicit thesis, infer the central argument from conclusions.\n\n"
            "2. CLUSTER ANALYSIS: Group into 2-5 clusters by shared theoretical assumptions.\n"
            "   Name each cluster. Explain what unites them (1-2 sentences).\n\n"
            "3. CONTRADICTION FLAGS: Flag where 2+ authors make mutually exclusive claims:\n"
            "   Paper A vs. Paper B → [contested claim]\n\n"
            "Do NOT summarize each paper individually. Focus ONLY on these three tasks."
        ),
    },
    "contradictions": {
        "name": "Contradiction Finder",
        "number": 2,
        "system": (
            "You are performing the CONTRADICTION FINDER protocol.\n\n"
            "Find points where 2+ authors make GENUINELY contradictory claims.\n"
            "Only mutually exclusive claims on the SAME issue.\n"
            "Exclude mere differences in emphasis or scope.\n\n"
            "Output as table:\n"
            "| Contested Claim | Position A (Paper, Year) | Position B (Paper, Year) | Root Cause |\n\n"
            "Root Cause: methodology, dataset, time period, definition of terms, or other (explain).\n"
            "Aim for 5-10. If fewer exist, list all."
        ),
    },
    "citation_chain": {
        "name": "Citation Chain",
        "number": 3,
        "system": (
            "You are performing the CITATION CHAIN protocol.\n\n"
            "Find the 3 concepts appearing most frequently across papers.\n"
            "For each, trace its intellectual history:\n\n"
            "Concept Name:\n"
            "  - Origin: Who introduced/defined it?\n"
            "  - Challenge: Who questioned it, and how?\n"
            "  - Refinement: Who modified/extended it, and how?\n"
            "  - Current Status: Settled / Contested / Still Evolving\n\n"
            "If lacking a challenger or refinement, state explicitly — do NOT guess."
        ),
    },
    "gap_scanner": {
        "name": "Gap Scanner",
        "number": 4,
        "system": (
            "You are performing the GAP SCANNER protocol.\n\n"
            "Identify the 5 most significant research gaps.\n"
            "For each:\n"
            "  - Gap: Unanswered question (1-2 sentences)\n"
            "  - Why: methodological barrier / lack of data / too niche / "
            "assumed but untested / ethical constraint\n"
            "  - Closest paper: Which came closest, where did it fall short?\n"
            "  - Path to resolution: What's needed to close the gap?\n\n"
            "Rank most→least significant. State ranking criterion."
        ),
    },
    "methodology_audit": {
        "name": "Methodology Audit",
        "number": 5,
        "system": (
            "You are performing the METHODOLOGY AUDIT protocol.\n\n"
            "Step 1 — Classification Table:\n"
            "| Paper | Methodology Type | Data Source | Sample Size | Key Limitation |\n\n"
            "Step 2 — Synthesis:\n"
            "  - Most frequent methodology? Why?\n"
            "  - Absent methodology that's relevant?\n\n"
            "Step 3 — Weakest Methodology:\n"
            "  - Which paper is most vulnerable to criticism?\n"
            "  - Evaluate: sample size, confounds, replicability, transparency.\n"
            "  - State which criterion it fails most clearly."
        ),
    },
    "master_synthesis": {
        "name": "Master Synthesis",
        "number": 6,
        "system": (
            "You are performing the MASTER SYNTHESIS protocol.\n\n"
            "Write a synthesis ACROSS the literature (do NOT summarize individually):\n\n"
            "1. Established Consensus (~100 words): What is collectively agreed? "
            "Cite 2+ sources per claim.\n"
            "2. Active Debates (~100 words): What is disputed? Name positions, "
            "not individual papers.\n"
            "3. Strongest Evidence (~100 words): Most consistent/replicated claims.\n"
            "4. Key Open Question (~80 words): Single most important unanswered question.\n\n"
            "TOTAL: 400 words max. No hedging. No 'it seems.' State clearly."
        ),
    },
    "assumption_killer": {
        "name": "Assumption Killer",
        "number": 7,
        "system": (
            "You are performing the ASSUMPTION KILLER protocol.\n\n"
            "Find 5-8 assumptions the majority share but never explicitly test:\n\n"
            "For each:\n"
            "  - Assumption: Declarative claim (e.g. 'X causes Y always')\n"
            "  - Shared by: 2-3 papers relying on it heavily\n"
            "  - Risk Level: Low / Medium / High\n"
            "  - Consequence if false:\n"
            "    Low = conclusions need revision\n"
            "    Medium = key findings invalidated\n"
            "    High = paradigm collapses\n\n"
            "Rank most→least consequential."
        ),
    },
    "knowledge_map": {
        "name": "Knowledge Map Builder",
        "number": 8,
        "system": (
            "You are performing the KNOWLEDGE MAP BUILDER protocol.\n\n"
            "Create a structured outline (NO prose paragraphs):\n\n"
            "1. Central Claim: Single proposition the field orbits. "
            "If none, name 2 competing centres.\n"
            "2. Supporting Pillars (3-5): Well-established sub-claims.\n"
            "   Format: [Claim] — supported by: [Source 1], [Source 2]\n"
            "3. Contested Zones (2-3): Active disagreements.\n"
            "   Format: [Issue] — [Position A] vs. [Position B]\n"
            "4. Frontier Questions (1-2): Unanswerable by current literature.\n"
            "5. Newcomer Reading List (3 papers): Why each is foundational."
        ),
    },
    "so_what": {
        "name": "The 'So What' Test",
        "number": 9,
        "system": (
            "You are performing the SO WHAT TEST protocol.\n\n"
            "Summarize for a smart non-expert. EXACTLY 3 numbered points, "
            "2-3 sentences each:\n\n"
            "1. What has been proven: Strongest finding. Direct claim. "
            "No 'suggests' or 'may indicate.'\n"
            "2. What is still unknown: Most significant uncertainty. "
            "State honestly.\n"
            "3. Why it matters: Single most important real-world implication.\n\n"
            "Rules: No jargon. No citations. No weakening qualifications.\n"
            "If you can't state confidently, say so — don't fabricate certainty."
        ),
    },
}


# ────────────────────────────────────────────────────────
#  Data Structures
# ────────────────────────────────────────────────────────

@dataclass
class ProtocolResult:
    """Output of a single research protocol execution."""
    protocol_name: str
    protocol_number: int
    content: str
    thinking_time_ms: float = 0.0
    tokens_used: int = 0


@dataclass
class ResearchReport:
    """Complete research analysis output."""
    topic: str
    mode: str  # "deep" (all 9) or "quick" (1+6+9)
    protocols_executed: List[ProtocolResult] = field(default_factory=list)
    total_time_ms: float = 0.0
    total_tokens: int = 0
    generated_at: str = ""

    def to_text(self) -> str:
        """Render the full report as formatted text."""
        lines = [
            f"{'═' * 60}",
            f"  RESEARCH ANALYSIS: {self.topic.upper()}",
            f"  Mode: {self.mode} | Protocols: {len(self.protocols_executed)}",
            f"  Time: {self.total_time_ms / 1000:.1f}s | Tokens: {self.total_tokens:,}",
            f"{'═' * 60}",
            "",
        ]

        for pr in self.protocols_executed:
            lines.append(f"{'─' * 60}")
            lines.append(f"  PROTOCOL {pr.protocol_number}: {pr.protocol_name.upper()}")
            lines.append(f"{'─' * 60}")
            lines.append(pr.content)
            lines.append("")

        lines.append(f"{'═' * 60}")
        lines.append(f"  END OF RESEARCH REPORT")
        lines.append(f"{'═' * 60}")
        return "\n".join(lines)

    def get_protocol(self, name: str) -> Optional[ProtocolResult]:
        """Get a specific protocol result by name."""
        for pr in self.protocols_executed:
            if name.lower() in pr.protocol_name.lower():
                return pr
        return None


# ────────────────────────────────────────────────────────
#  Research Engine
# ────────────────────────────────────────────────────────

class ResearchEngine:
    """
    Stanford PhD-level research pipeline.

    Runs structured protocols against a body of literature
    to produce rigorous academic-grade analysis.

    Usage:
        engine = ResearchEngine(llm_router)

        # Full analysis (all 9 protocols)
        report = engine.deep_research(
            topic="transformer attention mechanisms",
            sources=["Paper 1 abstract...", "Paper 2 abstract..."]
        )

        # Quick analysis (Intake + Synthesis + So What)
        brief = engine.quick_research(
            topic="CRISPR gene editing efficacy",
            sources=["Paper 1...", "Paper 2..."]
        )

        # Run a single protocol
        result = engine.run_protocol(
            "contradictions", topic="...", sources=[...]
        )
    """

    # Quick mode runs only these 3 protocols
    QUICK_PROTOCOLS = ["intake", "master_synthesis", "so_what"]

    # Full mode runs all 9 in order
    FULL_PROTOCOLS = [
        "intake", "contradictions", "citation_chain",
        "gap_scanner", "methodology_audit", "master_synthesis",
        "assumption_killer", "knowledge_map", "so_what",
    ]

    def __init__(self, llm: LLMRouter, max_tokens_per_protocol: int = 4096):
        self.llm = llm
        self.max_tokens = max_tokens_per_protocol
        self._reports: List[ResearchReport] = []

    def deep_research(self, topic: str,
                      sources: Optional[List[str]] = None,
                      context: str = "",
                      provider: Optional[str] = None) -> ResearchReport:
        """
        Run all 9 protocols for comprehensive analysis.
        This is the full Stanford PhD treatment.
        """
        return self._run_pipeline(
            topic=topic,
            sources=sources or [],
            context=context,
            protocol_keys=self.FULL_PROTOCOLS,
            mode="deep",
            provider=provider,
        )

    def quick_research(self, topic: str,
                       sources: Optional[List[str]] = None,
                       context: str = "",
                       provider: Optional[str] = None) -> ResearchReport:
        """
        Run Intake + Synthesis + So What for a rapid assessment.
        Good for initial literature scoping.
        """
        return self._run_pipeline(
            topic=topic,
            sources=sources or [],
            context=context,
            protocol_keys=self.QUICK_PROTOCOLS,
            mode="quick",
            provider=provider,
        )

    def run_protocol(self, protocol_key: str, topic: str,
                     sources: Optional[List[str]] = None,
                     context: str = "",
                     provider: Optional[str] = None) -> ProtocolResult:
        """Run a single protocol by key name."""
        if protocol_key not in PROTOCOLS:
            return ProtocolResult(
                protocol_name="Error",
                protocol_number=0,
                content=f"Unknown protocol: {protocol_key}. "
                        f"Available: {', '.join(PROTOCOLS.keys())}",
            )
        return self._execute_protocol(
            protocol_key, topic, sources or [], context, provider
        )

    @property
    def available_protocols(self) -> List[str]:
        """List all protocol keys."""
        return list(PROTOCOLS.keys())

    @property
    def report_history(self) -> List[ResearchReport]:
        """Access past reports."""
        return self._reports

    # ── Internal ───────────────────────────────────────

    def _run_pipeline(self, topic: str, sources: List[str],
                      context: str, protocol_keys: List[str],
                      mode: str, provider: Optional[str]) -> ResearchReport:
        """Execute a pipeline of protocols in order."""
        report = ResearchReport(
            topic=topic,
            mode=mode,
            generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        t0 = time.time()

        # Build cumulative context from prior protocols
        accumulated_context = context

        for key in protocol_keys:
            result = self._execute_protocol(
                key, topic, sources, accumulated_context, provider
            )
            report.protocols_executed.append(result)
            report.total_tokens += result.tokens_used

            # Feed output of each protocol into the next
            accumulated_context += (
                f"\n\n--- PROTOCOL {result.protocol_number} OUTPUT ---\n"
                f"{result.content}\n"
            )

        report.total_time_ms = (time.time() - t0) * 1000
        self._reports.append(report)
        return report

    def _execute_protocol(self, protocol_key: str, topic: str,
                          sources: List[str], context: str,
                          provider: Optional[str]) -> ProtocolResult:
        """Execute a single protocol."""
        proto = PROTOCOLS[protocol_key]
        t0 = time.time()

        # Build the user prompt
        user_prompt = f"RESEARCH TOPIC: {topic}\n\n"

        if sources:
            user_prompt += "SOURCES / PAPERS:\n"
            for i, src in enumerate(sources, 1):
                # Truncate each source to avoid context overflow
                truncated = src[:3000] if len(src) > 3000 else src
                user_prompt += f"\n--- Source {i} ---\n{truncated}\n"
            user_prompt += "\n"

        if context:
            user_prompt += f"PRIOR ANALYSIS CONTEXT:\n{context[:4000]}\n\n"

        user_prompt += (
            f"Execute PROTOCOL {proto['number']}: {proto['name']}.\n"
            f"Follow the protocol instructions exactly. Be rigorous."
        )

        try:
            request = LLMRequest(
                messages=[Message(Role.USER, user_prompt)],
                system=proto["system"],
                temperature=0.2,  # Low temp for analytical precision
                max_tokens=self.max_tokens,
            )

            if provider:
                response = self.llm.generate(request, provider=provider)
            else:
                response = self.llm.generate(request)

            content = response.content
            tokens = response.input_tokens + response.output_tokens
        except Exception as e:
            content = f"[Protocol execution failed: {e}]"
            tokens = 0

        return ProtocolResult(
            protocol_name=proto["name"],
            protocol_number=proto["number"],
            content=content,
            thinking_time_ms=(time.time() - t0) * 1000,
            tokens_used=tokens,
        )
