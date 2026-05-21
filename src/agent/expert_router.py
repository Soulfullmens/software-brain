"""
expert_router.py

Dynamic Expert Persona Router — auto-selects the best expert prompt
based on query keywords. This is what makes the expert personas actually
functional instead of just sitting in .md files.

Usage:
    router = ExpertRouter()
    expert_prompt = router.select(query="review this code for SQL injection")
    # → returns the security_expert.md contents

    # Or get the full augmented system prompt:
    system = router.build_system_prompt(query, base_prompt=CLAUDE_SYSTEM_PROMPT)
"""

import os
import re
from typing import Dict, List, Optional, Tuple


class ExpertRouter:
    """
    Loads expert persona prompts from src/agent/prompts/experts/
    and routes queries to the best-matching persona based on keyword
    relevance scoring.
    """

    # ── Keyword → Expert Mapping ──────────────────────
    # Each expert gets a set of trigger keywords with weights.
    # Higher weight = stronger signal. A query can match multiple experts;
    # the highest total score wins.
    EXPERT_KEYWORDS: Dict[str, List[Tuple[str, float]]] = {
        "security_expert": [
            ("security", 2.0), ("vulnerability", 2.0), ("attack", 1.5),
            ("exploit", 2.0), ("injection", 2.0), ("xss", 2.0), ("csrf", 2.0),
            ("authentication", 1.5), ("authorization", 1.5), ("encryption", 1.5),
            ("firewall", 1.5), ("threat", 1.5), ("audit", 1.0), ("penetration", 2.0),
            ("owasp", 2.0), ("cve", 2.0), ("hardening", 1.5), ("malware", 1.5),
            ("phishing", 1.5), ("password", 1.0), ("token", 0.8), ("jwt", 1.5),
        ],
        "coding_expert": [
            ("code", 1.5), ("function", 1.0), ("class", 1.0), ("debug", 1.5),
            ("refactor", 1.5), ("bug", 1.5), ("implement", 1.0), ("algorithm", 1.5),
            ("python", 1.5), ("javascript", 1.5), ("typescript", 1.5), ("rust", 1.5),
            ("api", 1.0), ("test", 1.0), ("unittest", 1.5), ("pytest", 1.5),
            ("performance", 1.0), ("optimize", 1.0), ("regex", 1.5), ("parse", 1.0),
            ("compile", 1.0), ("runtime", 1.0), ("syntax", 1.0), ("exception", 1.0),
        ],
        "engineering_architect": [
            ("architecture", 2.0), ("system design", 2.0), ("microservice", 2.0),
            ("database design", 1.5), ("scalab", 1.5), ("distributed", 1.5),
            ("component", 1.0), ("infrastructure", 1.5), ("cloud", 1.0),
            ("kubernetes", 1.5), ("docker", 1.0), ("deployment", 1.0),
            ("migration", 1.5), ("monolith", 1.5), ("event driven", 1.5),
            ("message queue", 1.5), ("kafka", 1.5), ("grpc", 1.5),
            ("load balancer", 1.5), ("caching", 1.0),
        ],
        "strategic_planner": [
            ("plan", 1.5), ("strategy", 2.0), ("roadmap", 2.0), ("milestone", 1.5),
            ("goal", 1.0), ("objective", 1.0), ("prioritize", 1.5), ("timeline", 1.5),
            ("risk", 1.5), ("phase", 1.0), ("sprint", 1.0), ("agile", 1.0),
            ("estimate", 1.0), ("scope", 1.0), ("budget", 1.0), ("resource", 0.8),
            ("decision", 1.0), ("tradeoff", 1.5), ("trade-off", 1.5),
            ("project", 1.0), ("breakdown", 1.0),
        ],
        "medical_expert": [
            ("medical", 2.0), ("clinical", 2.0), ("diagnosis", 2.0), ("symptom", 2.0),
            ("drug", 1.5), ("pharmacol", 2.0), ("treatment", 1.5), ("disease", 1.5),
            ("patient", 1.5), ("anatomy", 1.5), ("physiology", 1.5), ("surgery", 1.5),
            ("therapy", 1.0), ("cancer", 1.5), ("cardiac", 1.5), ("neurol", 1.5),
            ("genomic", 1.5), ("crispr", 2.0), ("vaccine", 1.5), ("pathology", 1.5),
            ("health", 0.8), ("biotech", 1.5),
        ],
        "engineering_expert": [
            ("robot", 2.0), ("drone", 2.0), ("rocket", 2.0), ("aerospace", 2.0),
            ("motor", 1.5), ("sensor", 1.5), ("actuator", 1.5), ("avionics", 2.0),
            ("embedded", 1.5), ("microcontroller", 2.0), ("esp32", 2.0), ("stm32", 2.0),
            ("pid", 1.5), ("imu", 2.0), ("cad", 1.5), ("3d print", 1.5),
            ("thrust", 1.5), ("propulsion", 2.0), ("telemetry", 1.5),
            ("mechanical", 1.0), ("electrical", 1.0), ("circuit", 1.5),
            ("solder", 1.5), ("pcb", 1.5), ("fpga", 1.5),
        ],
        "creative_expert": [
            ("creative", 2.0), ("design", 1.0), ("brand", 2.0), ("marketing", 2.0),
            ("content", 1.0), ("story", 1.5), ("narrative", 1.5), ("visual", 1.0),
            ("aesthetic", 1.5), ("video", 1.0), ("thumbnail", 1.5), ("color", 1.0),
            ("typography", 1.5), ("logo", 1.5), ("campaign", 1.5), ("viral", 1.5),
            ("midjourney", 2.0), ("stable diffusion", 2.0), ("prompt engineer", 1.5),
            ("cinemat", 1.5), ("photograp", 1.0), ("illustration", 1.5),
        ],
        "research_protocol": [
            ("research", 2.5), ("paper", 2.0), ("literature", 2.5), ("study", 1.5),
            ("journal", 2.0), ("academic", 2.0), ("scholar", 2.0), ("thesis", 2.0),
            ("hypothesis", 2.0), ("methodology", 2.0), ("meta-analysis", 2.5),
            ("peer review", 2.5), ("citation", 2.0), ("abstract", 1.5),
            ("findings", 1.5), ("empirical", 2.0), ("literature review", 2.5),
            ("contradiction", 2.0), ("research gap", 2.5), ("synthesis", 1.5),
            ("evidence", 1.0), ("publication", 1.5), ("experiment", 1.0),
            ("dataset", 1.5), ("sample size", 2.0), ("p-value", 2.0),
            ("statistical", 1.5), ("replicate", 2.0), ("longitudinal", 2.0),
            ("cross-sectional", 2.0), ("qualitative", 1.5), ("quantitative", 1.5),
            ("systematic review", 2.5), ("analyze papers", 2.5), ("compare studies", 2.5),
        ],
    }

    def __init__(self, prompts_dir: Optional[str] = None):
        if prompts_dir is None:
            # Default: same package → prompts/experts/
            prompts_dir = os.path.join(
                os.path.dirname(__file__), "prompts", "experts"
            )
        self._prompts_dir = prompts_dir
        self._cache: Dict[str, str] = {}
        self._load_prompts()

    def _load_prompts(self):
        """Load all .md files from the experts directory."""
        if not os.path.isdir(self._prompts_dir):
            return
        for fname in os.listdir(self._prompts_dir):
            if fname.endswith(".md"):
                key = fname.replace(".md", "")
                path = os.path.join(self._prompts_dir, fname)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        self._cache[key] = f.read().strip()
                except Exception:
                    pass

    @property
    def available_experts(self) -> List[str]:
        """Return list of loaded expert names."""
        return sorted(self._cache.keys())

    def score_query(self, query: str) -> Dict[str, float]:
        """
        Score a query against all experts.
        Returns {expert_name: relevance_score}.
        """
        query_lower = query.lower()
        scores: Dict[str, float] = {}

        for expert, keywords in self.EXPERT_KEYWORDS.items():
            total = 0.0
            for keyword, weight in keywords:
                # Use word-boundary-aware matching for short keywords
                if len(keyword) <= 3:
                    if re.search(rf'\b{re.escape(keyword)}\b', query_lower):
                        total += weight
                else:
                    if keyword in query_lower:
                        total += weight
            scores[expert] = total

        return scores

    def select(self, query: str, threshold: float = 2.0) -> Optional[str]:
        """
        Select the best expert prompt for a query.
        Returns the expert system prompt text, or None if no expert scores
        above threshold.
        """
        scores = self.score_query(query)
        if not scores:
            return None

        best_expert = max(scores, key=scores.get)
        if scores[best_expert] < threshold:
            return None

        return self._cache.get(best_expert)

    def select_expert_name(self, query: str, threshold: float = 2.0) -> Optional[str]:
        """Return the name of the best matching expert (or None)."""
        scores = self.score_query(query)
        if not scores:
            return None
        best = max(scores, key=scores.get)
        return best if scores[best] >= threshold else None

    def get_prompt(self, expert_name: str) -> Optional[str]:
        """Get a specific expert's prompt by name."""
        return self._cache.get(expert_name)

    def build_system_prompt(self, query: str, base_prompt: str,
                            threshold: float = 2.0) -> str:
        """
        Build a composite system prompt:
          base_prompt + selected expert addendum.
        If no expert matches, returns base_prompt unchanged.
        """
        expert_prompt = self.select(query, threshold)
        if expert_prompt is None:
            return base_prompt

        expert_name = self.select_expert_name(query, threshold) or "specialist"
        return (
            f"{base_prompt}\n\n"
            f"═══ ACTIVE EXPERT MODE: {expert_name.upper().replace('_', ' ')} ═══\n\n"
            f"{expert_prompt}"
        )
