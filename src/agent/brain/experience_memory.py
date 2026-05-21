"""
experience_memory.py

Persistent Experience Memory — Phase R.4+.
The agent's long-term learning system.

This is HOW the agent gets smarter over time without needing Claude.

It stores:
- Successful task patterns (what worked)
- Failed approaches (what didn't work)
- Site reliability scores (which sites work best)
- Selector reliability scores (which selectors are stable)
- Strategy effectiveness (which recovery methods succeed)
- Time estimates (how long tasks actually take)

Over time, the agent learns:
- "Google Flights is more reliable than SkyScanner for flight search"
- "The 'Sign In' button selector breaks on Amazon; use 'sign in button' instead"
- "Research tasks need 4 subgoals on average"
- "YouTube search always succeeds, Google search fails 12% of the time"
"""
import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List
from datetime import datetime


@dataclass
class TaskExperience:
    """A single completed task experience."""
    id: str
    timestamp: str
    goal: str
    intent: str                        # Detected intent (search, book, navigate, etc.)
    
    # Execution
    total_steps: int = 0
    status: str = ""                   # completed, failed, stuck, needs_human
    duration_seconds: float = 0.0
    
    # Plan
    subgoal_count: int = 0
    subgoals_completed: int = 0
    subgoals_failed: int = 0
    
    # Key data
    sites_visited: List[str] = field(default_factory=list)
    selectors_used: List[str] = field(default_factory=list)
    selectors_failed: List[str] = field(default_factory=list)
    strategies_tried: List[str] = field(default_factory=list)
    strategies_succeeded: List[str] = field(default_factory=list)
    
    # Errors
    errors: List[str] = field(default_factory=list)
    
    # Success factors
    success_factors: List[str] = field(default_factory=list)
    failure_factors: List[str] = field(default_factory=list)


@dataclass
class SiteProfile:
    """Reliability profile for a website."""
    domain: str
    total_visits: int = 0
    successful_visits: int = 0
    failed_visits: int = 0
    avg_load_time: float = 0.0
    reliable_selectors: List[str] = field(default_factory=list)
    fragile_selectors: List[str] = field(default_factory=list)
    best_strategies: List[str] = field(default_factory=list)
    
    @property
    def reliability_score(self) -> float:
        if self.total_visits == 0:
            return 0.5
        return self.successful_visits / self.total_visits


@dataclass
class PatternTemplate:
    """A learned task pattern that can be reused."""
    intent: str
    goal_keywords: List[str]
    subgoal_sequence: List[Dict[str, str]]  # [{tool, command, description}]
    success_rate: float = 0.0
    times_used: int = 0
    avg_steps: float = 0.0


class ExperienceMemory:
    """
    Persistent experience store.
    Learns from every task execution.
    
    This is the core of the agent's intelligence advantage:
    - After 10 tasks: knows which sites work
    - After 50 tasks: knows optimal strategies
    - After 100 tasks: outperforms static planning
    """
    
    MEMORY_FILE = "agent_experience.json"
    
    def __init__(self, storage_dir: str = "./agent_data"):
        self.storage_dir = storage_dir
        self.experiences: List[TaskExperience] = []
        self.site_profiles: Dict[str, SiteProfile] = {}
        self.patterns: List[PatternTemplate] = []
        self.strategy_scores: Dict[str, Dict[str, float]] = {}  # strategy -> {successes, attempts}
        self.selector_scores: Dict[str, Dict[str, float]] = {}  # selector -> {successes, attempts}
        
        # Load from disk
        self._load()
    
    def record_experience(self, exp: TaskExperience):
        """Record a completed task experience."""
        self.experiences.append(exp)
        
        # Update site profiles
        for site in exp.sites_visited:
            self._update_site_profile(site, exp.status == "completed")
        
        # Update selector scores
        for sel in exp.selectors_used:
            self._update_selector(sel, success=True)
        for sel in exp.selectors_failed:
            self._update_selector(sel, success=False)
        
        # Update strategy scores
        for strat in exp.strategies_tried:
            succeeded = strat in exp.strategies_succeeded
            self._update_strategy(strat, succeeded)
        
        # Extract patterns from successful experiences
        if exp.status == "completed":
            self._extract_pattern(exp)
        
        # Persist
        self._save()
    
    def get_best_strategy(self, tool: str, command: str) -> Optional[str]:
        """Get the historically most successful strategy for a tool/command combo."""
        key = f"{tool}.{command}"
        if key in self.strategy_scores:
            scores = self.strategy_scores[key]
            if scores.get("attempts", 0) > 0:
                return f"Success rate: {scores['successes'] / scores['attempts']:.0%}"
        return None
    
    def get_site_reliability(self, domain: str) -> float:
        """Get reliability score for a site (0-1)."""
        profile = self.site_profiles.get(domain)
        return profile.reliability_score if profile else 0.5
    
    def get_best_selector(self, element_type: str) -> Optional[str]:
        """Get the historically most reliable selector for an element type."""
        best_score = 0.0
        best_selector = None
        
        for selector, scores in self.selector_scores.items():
            if element_type.lower() in selector.lower():
                attempts = scores.get("attempts", 0)
                if attempts > 0:
                    score = scores["successes"] / attempts
                    if score > best_score:
                        best_score = score
                        best_selector = selector
        
        return best_selector
    
    def get_similar_experience(self, goal: str) -> Optional[TaskExperience]:
        """Find the most similar past experience."""
        goal_words = set(goal.lower().split())
        best_match = None
        best_overlap = 0
        
        for exp in self.experiences:
            exp_words = set(exp.goal.lower().split())
            overlap = len(goal_words & exp_words)
            if overlap > best_overlap:
                best_overlap = overlap
                best_match = exp
        
        return best_match if best_overlap >= 2 else None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get overall learning statistics."""
        total = len(self.experiences)
        if total == 0:
            return {"total_tasks": 0, "success_rate": 0.0}
        
        successful = sum(1 for e in self.experiences if e.status == "completed")
        avg_steps = sum(e.total_steps for e in self.experiences) / total
        
        # Most reliable sites
        reliable_sites = sorted(
            self.site_profiles.values(),
            key=lambda s: s.reliability_score,
            reverse=True
        )[:5]
        
        return {
            "total_tasks": total,
            "success_rate": successful / total,
            "avg_steps": avg_steps,
            "known_sites": len(self.site_profiles),
            "learned_patterns": len(self.patterns),
            "top_sites": [
                {"domain": s.domain, "reliability": f"{s.reliability_score:.0%}"}
                for s in reliable_sites
            ]
        }
    
    def _update_site_profile(self, url: str, success: bool):
        """Update site reliability profile."""
        from urllib.parse import urlparse
        try:
            domain = urlparse(url).netloc or url
        except Exception:
            domain = url
        
        if domain not in self.site_profiles:
            self.site_profiles[domain] = SiteProfile(domain=domain)
        
        profile = self.site_profiles[domain]
        profile.total_visits += 1
        if success:
            profile.successful_visits += 1
        else:
            profile.failed_visits += 1
    
    def _update_selector(self, selector: str, success: bool):
        if selector not in self.selector_scores:
            self.selector_scores[selector] = {"successes": 0.0, "attempts": 0.0}
        self.selector_scores[selector]["attempts"] += 1
        if success:
            self.selector_scores[selector]["successes"] += 1
    
    def _update_strategy(self, strategy: str, success: bool):
        if strategy not in self.strategy_scores:
            self.strategy_scores[strategy] = {"successes": 0.0, "attempts": 0.0}
        self.strategy_scores[strategy]["attempts"] += 1
        if success:
            self.strategy_scores[strategy]["successes"] += 1
    
    def _extract_pattern(self, exp: TaskExperience):
        """Extract reusable pattern from successful experience."""
        # Simple pattern: same intent → same subgoal count works
        existing = [p for p in self.patterns if p.intent == exp.intent]
        if existing:
            pattern = existing[0]
            pattern.times_used += 1
            pattern.success_rate = (
                (pattern.success_rate * (pattern.times_used - 1) + 1.0) / pattern.times_used
            )
            pattern.avg_steps = (
                (pattern.avg_steps * (pattern.times_used - 1) + exp.total_steps) / pattern.times_used
            )
        else:
            self.patterns.append(PatternTemplate(
                intent=exp.intent,
                goal_keywords=exp.goal.lower().split()[:5],
                subgoal_sequence=[],
                success_rate=1.0,
                times_used=1,
                avg_steps=float(exp.total_steps)
            ))
    
    def _save(self):
        """Save to disk."""
        os.makedirs(self.storage_dir, exist_ok=True)
        path = os.path.join(self.storage_dir, self.MEMORY_FILE)
        
        data = {
            "experiences": [asdict(e) for e in self.experiences[-100:]],  # Keep last 100
            "site_profiles": {k: asdict(v) for k, v in self.site_profiles.items()},
            "patterns": [asdict(p) for p in self.patterns],
            "strategy_scores": self.strategy_scores,
            "selector_scores": self.selector_scores,
        }
        
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    
    def record_feedback(self, goal: str, correction: str):
        """Record manual user feedback/correction for a specific task goal.
        
        This allows the agent to learn from its mistakes immediately when a user
        corrects its perception or logic.
        """
        timestamp = datetime.now().isoformat()
        feedback = {
            "timestamp": timestamp,
            "goal": goal,
            "correction": correction,
            "type": "user_correction"
        }
        
        # Store as a special 'Correction' experience
        # We can also update a 'CorrectionsLog' or similar
        try:
            feedback_file = os.path.join(self.storage_dir, "user_feedback.json")
            existing = []
            if os.path.exists(feedback_file):
                with open(feedback_file, "r") as f:
                    existing = json.load(f)
            
            existing.append(feedback)
            with open(feedback_file, "w") as f:
                json.dump(existing, f, indent=4)
                
            # Also add to experiences list for RAG retrieval
            self.experiences.append(TaskExperience(
                id=f"corr_{int(time.time())}",
                timestamp=timestamp,
                goal=goal,
                intent="user_correction",
                status="correction_recorded",
                errors=[correction]
            ))
            self._save()
        except Exception:
            pass

    def _load(self):
        """Load from disk."""
        path = os.path.join(self.storage_dir, self.MEMORY_FILE)
        if not os.path.exists(path):
            return
        
        try:
            with open(path, "r") as f:
                data = json.load(f)
            
            self.experiences = [
                TaskExperience(**e) for e in data.get("experiences", [])
            ]
            self.site_profiles = {
                k: SiteProfile(**v) for k, v in data.get("site_profiles", {}).items()
            }
            self.patterns = [
                PatternTemplate(**p) for p in data.get("patterns", [])
            ]
            self.strategy_scores = data.get("strategy_scores", {})
            self.selector_scores = data.get("selector_scores", {})
        except Exception:
            pass
