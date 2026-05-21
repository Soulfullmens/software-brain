"""
persona_engine.py — Context-Adaptive Persona Engine

Inspired by MiroFish's OasisProfileGenerator which creates detailed
agent personas with MBTI, demographics, expertise, and behavioral traits.

Our version adapts the AGENT'S OWN personality per task, not external agents.

CAPABILITIES:
    1. Task-adaptive persona generation — picks the best expert archetype
    2. System prompt injection — modifies LLM system prompt with persona
    3. Predefined expert archetypes with deep expertise profiles
    4. Dynamic trait mixing — blends archetypes for hybrid tasks
    5. Persona persistence — remembers which persona worked best
"""
import time
import json
import random
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple


# ═══════════════════════════════════════════════════════
# DATA TYPES
# ═══════════════════════════════════════════════════════

@dataclass
class PersonaProfile:
    """A complete agent persona."""
    archetype: str              # researcher, developer, analyst, creative, strategist
    name: str                   # Display name for this persona mode
    expertise: List[str]        # Areas of expertise
    tone: str                   # Communication tone
    approach: str               # Problem-solving approach
    traits: List[str]           # Personality traits
    system_prompt_addon: str    # Additional system prompt text
    confidence_level: str       # "cautious", "balanced", "assertive"
    detail_level: str           # "concise", "balanced", "thorough"
    mbti: str = ""              # Optional MBTI type (MiroFish-inspired)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "archetype": self.archetype,
            "name": self.name,
            "expertise": self.expertise,
            "tone": self.tone,
            "approach": self.approach,
            "traits": self.traits,
            "mbti": self.mbti,
        }


# ═══════════════════════════════════════════════════════
# PREDEFINED ARCHETYPES
# ═══════════════════════════════════════════════════════

ARCHETYPES: Dict[str, PersonaProfile] = {
    "researcher": PersonaProfile(
        archetype="researcher",
        name="Deep Researcher",
        expertise=["information gathering", "source evaluation", "synthesis", "fact-checking"],
        tone="precise, academic, evidence-based",
        approach="Gather evidence first, then form conclusions. Always cite sources. "
                 "Question assumptions. Look for contradictions.",
        traits=["thorough", "skeptical", "systematic", "detail-oriented"],
        system_prompt_addon=(
            "You are in RESEARCHER mode. Prioritize accuracy over speed. "
            "Always seek evidence before making claims. Indicate confidence levels. "
            "Distinguish between established facts and inferences. "
            "When uncertain, say so clearly rather than guessing."
        ),
        confidence_level="cautious",
        detail_level="thorough",
        mbti="INTJ",
    ),
    "developer": PersonaProfile(
        archetype="developer",
        name="Engineer",
        expertise=["coding", "debugging", "architecture", "system design", "testing"],
        tone="practical, direct, solution-oriented",
        approach="Understand the problem, design a solution, implement iteratively, "
                 "test thoroughly. Ship working code.",
        traits=["pragmatic", "efficient", "systematic", "quality-focused"],
        system_prompt_addon=(
            "You are in DEVELOPER mode. Focus on working, clean, efficient code. "
            "Consider edge cases. Follow best practices. Write tests. "
            "Explain design decisions briefly. Prefer simplicity over cleverness. "
            "If asked to debug, isolate the root cause before suggesting fixes."
        ),
        confidence_level="balanced",
        detail_level="balanced",
        mbti="ISTP",
    ),
    "analyst": PersonaProfile(
        archetype="analyst",
        name="Data Analyst",
        expertise=["data analysis", "pattern recognition", "visualization", "statistics", "reporting"],
        tone="analytical, structured, data-driven",
        approach="Define the question, collect data, analyze patterns, "
                 "present findings with supporting evidence.",
        traits=["methodical", "quantitative", "objective", "pattern-seeking"],
        system_prompt_addon=(
            "You are in ANALYST mode. Structure your analysis clearly. "
            "Use data and evidence to support every claim. Present findings in a logical. "
            "order: context → data → analysis → conclusions → recommendations. "
            "Quantify whenever possible."
        ),
        confidence_level="balanced",
        detail_level="thorough",
        mbti="ISTJ",
    ),
    "creative": PersonaProfile(
        archetype="creative",
        name="Creative Thinker",
        expertise=["ideation", "brainstorming", "design thinking", "storytelling", "innovation"],
        tone="enthusiastic, imaginative, exploratory",
        approach="Generate many ideas, explore unconventional angles, "
                 "combine concepts from different domains, prototype quickly.",
        traits=["imaginative", "open-minded", "divergent-thinking", "playful"],
        system_prompt_addon=(
            "You are in CREATIVE mode. Think outside the box. Generate multiple ideas. "
            "Don't self-censor early — explore wild possibilities first, then refine. "
            "Draw connections between unrelated domains. Be bold with suggestions."
        ),
        confidence_level="assertive",
        detail_level="concise",
        mbti="ENFP",
    ),
    "strategist": PersonaProfile(
        archetype="strategist",
        name="Strategic Advisor",
        expertise=["planning", "risk assessment", "decision-making", "stakeholder management"],
        tone="authoritative, considered, forward-thinking",
        approach="Analyze the landscape, identify key stakeholders, evaluate risks, "
                 "propose multiple strategies with trade-offs, recommend the optimal path.",
        traits=["strategic", "decisive", "big-picture", "risk-aware"],
        system_prompt_addon=(
            "You are in STRATEGIST mode. Think long-term. Consider multiple scenarios. "
            "Present trade-offs clearly. Identify risks and mitigations. "
            "Structure advice as: Situation → Options → Recommendation → Risks."
        ),
        confidence_level="assertive",
        detail_level="balanced",
        mbti="ENTJ",
    ),
    "mentor": PersonaProfile(
        archetype="mentor",
        name="Patient Mentor",
        expertise=["teaching", "explanation", "guidance", "learning paths", "encouragement"],
        tone="warm, patient, encouraging, Socratic",
        approach="Understand the learner's level. Explain concepts step-by-step. "
                 "Use analogies. Ask guiding questions. Celebrate progress.",
        traits=["patient", "empathetic", "clear-communicator", "motivating"],
        system_prompt_addon=(
            "You are in MENTOR mode. Explain things clearly for the learner's level. "
            "Use analogies and examples. Don't dump information — guide discovery. "
            "Ask clarifying questions. Break complex topics into digestible steps. "
            "Encourage the learner and acknowledge progress."
        ),
        confidence_level="balanced",
        detail_level="thorough",
        mbti="ENFJ",
    ),
}

# Task keyword → archetype mapping
TASK_KEYWORDS: Dict[str, List[str]] = {
    "researcher": ["research", "find", "investigate", "study", "learn about", "what is", "who is",
                    "explain", "sources", "evidence", "facts"],
    "developer": ["code", "implement", "build", "fix", "debug", "deploy", "api", "function",
                   "class", "test", "error", "bug", "program", "script", "app"],
    "analyst": ["analyze", "data", "statistics", "pattern", "trend", "report", "compare",
                "metrics", "dashboard", "insights", "evaluate"],
    "creative": ["design", "create", "brainstorm", "idea", "innovate", "concept", "imagine",
                 "campaign", "brand", "story", "ui", "ux"],
    "strategist": ["plan", "strategy", "decision", "roadmap", "prioritize", "stakeholder",
                   "risk", "budget", "vision", "architecture", "trade-off"],
    "mentor": ["teach", "explain simply", "help me understand", "how does", "tutorial",
               "beginner", "step by step", "learn", "guide"],
}


# ═══════════════════════════════════════════════════════
# PERSONA ENGINE
# ═══════════════════════════════════════════════════════

class PersonaEngine:
    """
    Dynamically adapts agent personality based on task context.

    Usage:
        engine = PersonaEngine()
        persona = engine.select_persona("Debug this Python error in my API")
        system_prompt = engine.adapt_system_prompt(base_prompt, persona)
    """

    def __init__(self):
        self._archetypes = dict(ARCHETYPES)
        self._history: List[Dict[str, Any]] = []
        self._current_persona: Optional[PersonaProfile] = None
        self._stats = {
            "persona_switches": 0,
            "by_archetype": {},
        }

    def select_persona(self, task_description: str,
                        force_archetype: str = None) -> PersonaProfile:
        """
        Select the best persona for the task.

        Args:
            task_description: Natural language description of the task
            force_archetype: Override auto-selection with a specific archetype

        Returns:
            PersonaProfile for the selected archetype
        """
        if force_archetype and force_archetype in self._archetypes:
            persona = self._archetypes[force_archetype]
        else:
            persona = self._auto_select(task_description)

        self._current_persona = persona
        self._stats["persona_switches"] += 1
        self._stats["by_archetype"][persona.archetype] = \
            self._stats["by_archetype"].get(persona.archetype, 0) + 1

        self._history.append({
            "task": task_description[:200],
            "archetype": persona.archetype,
            "timestamp": time.time(),
        })

        return persona

    def get_current_persona(self) -> Optional[PersonaProfile]:
        """Get the currently active persona."""
        return self._current_persona

    def adapt_system_prompt(self, base_prompt: str,
                            persona: PersonaProfile = None) -> str:
        """
        Inject persona traits into the system prompt.

        Args:
            base_prompt: The base system prompt
            persona: PersonaProfile to inject (uses current if None)

        Returns:
            Enhanced system prompt with persona traits
        """
        p = persona or self._current_persona
        if not p:
            return base_prompt

        addon = f"""

--- ACTIVE PERSONA: {p.name} ({p.archetype.upper()}) ---
{p.system_prompt_addon}

Expertise: {', '.join(p.expertise)}
Communication Style: {p.tone}
Problem-Solving Approach: {p.approach}
--- END PERSONA ---
"""
        return base_prompt + addon

    def list_archetypes(self) -> List[Dict[str, str]]:
        """List all available archetypes."""
        return [
            {"name": a.archetype, "display_name": a.name,
             "tone": a.tone, "mbti": a.mbti}
            for a in self._archetypes.values()
        ]

    def _auto_select(self, task: str) -> PersonaProfile:
        """Auto-select archetype based on task keywords."""
        task_lower = task.lower()
        scores: Dict[str, float] = {}

        for archetype, keywords in TASK_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in task_lower)
            if score > 0:
                scores[archetype] = score

        if scores:
            best = max(scores, key=scores.get)
            return self._archetypes[best]

        # Default to developer for code-related, researcher for everything else
        if any(ext in task_lower for ext in [".py", ".js", ".ts", ".html", ".css"]):
            return self._archetypes["developer"]

        return self._archetypes["researcher"]

    def add_custom_archetype(self, name: str, profile: PersonaProfile):
        """Add a custom archetype."""
        self._archetypes[name] = profile

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "current": self._current_persona.archetype if self._current_persona else None,
            "total_archetypes": len(self._archetypes),
        }
