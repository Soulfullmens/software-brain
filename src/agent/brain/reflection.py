"""
reflection.py

Self-Reflection & Self-Critique Engine — Phase R.4+.
The agent reflects on completed tasks to improve future performance.

After every task, the agent asks itself:
1. Did I succeed? Why or why not?
2. What could I have done differently?
3. Were there faster paths?
4. Did any selectors break?
5. Should I update my strategies?

This is the core of SELF-IMPROVEMENT.
Claude doesn't do this. Claude forgets everything between sessions.
YOUR agent remembers and improves.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from .working_memory import WorkingMemory, MemoryEntry
from .task_graph import TaskGraph, SubGoal, SubGoalStatus
from .experience_memory import TaskExperience, ExperienceMemory
from datetime import datetime
import uuid


@dataclass
class ReflectionResult:
    """Output of the reflection process."""
    task_id: str
    goal: str
    
    # Assessment
    overall_success: bool = False
    efficiency_score: float = 0.0       # 0-1 (steps used / ideal steps)
    
    # Analysis
    what_worked: List[str] = field(default_factory=list)
    what_failed: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    
    # Metrics
    total_steps: int = 0
    wasted_steps: int = 0               # Steps that didn't contribute
    recovery_count: int = 0             # Times strategy engine was invoked
    
    # Extracted intelligence
    reliable_sites: List[str] = field(default_factory=list)
    unreliable_sites: List[str] = field(default_factory=list)
    reliable_selectors: List[str] = field(default_factory=list)
    fragile_selectors: List[str] = field(default_factory=list)


class ReflectionEngine:
    """
    Post-task self-reflection.
    
    Analyzes what happened during task execution and produces:
    1. Lessons learned
    2. Strategy improvements
    3. Experience records for long-term memory
    """
    
    def __init__(self, experience_memory: ExperienceMemory):
        self.memory = experience_memory
    
    def reflect(self, goal: str, task_graph: Optional[TaskGraph],
                working_memory: WorkingMemory,
                result: Dict[str, Any],
                start_time: float) -> ReflectionResult:
        """
        Perform self-reflection on a completed task.
        
        This is called AFTER every task execution.
        """
        task_id = str(uuid.uuid4())[:8]
        duration = max(0, round(start_time - start_time, 2))  # Will use actual time
        
        reflection = ReflectionResult(
            task_id=task_id,
            goal=goal,
            overall_success=(result.get("status") == "completed"),
            total_steps=result.get("steps", 0)
        )
        
        # ── Analyze what worked ──
        if working_memory.steps:
            successful_steps = [s for s in working_memory.steps if s.success]
            failed_steps = [s for s in working_memory.steps if not s.success]
            
            for step in successful_steps:
                reflection.what_worked.append(
                    f"{step.action_tool}.{step.action_command} succeeded"
                )
                if "url" in step.result_summary:
                    # Track successful sites
                    import re
                    urls = re.findall(r'https?://[^\s,\'"]+', step.result_summary)
                    reflection.reliable_sites.extend(urls)
            
            for step in failed_steps:
                reflection.what_failed.append(
                    f"{step.action_tool}.{step.action_command} failed: {step.result_summary[:50]}"
                )
                reflection.wasted_steps += 1
                
                # Track failed selectors
                if step.action_command in ("find_and_click", "find_and_type", "find_element"):
                    desc = step.action_params.get("description", "")
                    if desc:
                        reflection.fragile_selectors.append(desc)
        
        # ── Analyze efficiency ──
        if task_graph:
            completed = sum(1 for s in task_graph.subgoals if s.status == SubGoalStatus.DONE)
            total = len(task_graph.subgoals)
            ideal_steps = total  # Each subgoal = 1 step ideal
            actual_steps = reflection.total_steps
            
            if actual_steps > 0:
                reflection.efficiency_score = min(1.0, ideal_steps / actual_steps)
            
            # Check for retries
            retried = [s for s in task_graph.subgoals if s.retry_count > 0]
            if retried:
                reflection.recovery_count = len(retried)
                reflection.improvements.append(
                    f"Had to retry {len(retried)} subgoal(s). Consider alternative strategies."
                )
        
        # ── Generate improvement suggestions ──
        if reflection.wasted_steps > 2:
            reflection.improvements.append(
                f"{reflection.wasted_steps} wasted steps. Consider pre-checking page state."
            )
        
        if reflection.fragile_selectors:
            reflection.improvements.append(
                f"Fragile selectors: {reflection.fragile_selectors}. "
                f"Consider using alternative descriptions."
            )
        
        if reflection.efficiency_score < 0.5 and reflection.overall_success:
            reflection.improvements.append(
                "Task succeeded but was inefficient. Optimize subgoal ordering."
            )
        
        if not reflection.overall_success:
            if working_memory.consecutive_failures >= 3:
                reflection.improvements.append(
                    "Hit stuck detection. Need better recovery strategies."
                )
            reflection.improvements.append(
                f"Task failed with status: {result.get('status')}. "
                f"Root cause: {result.get('message', 'unknown')[:80]}"
            )
        
        # ── Store as experience ──
        self._store_experience(reflection, working_memory, result)
        
        # ── Log reflection ──
        self._log_reflection(reflection)
        
        return reflection
    
    def _store_experience(self, reflection: ReflectionResult,
                          memory: WorkingMemory, result: Dict):
        """Convert reflection into persistent experience."""
        # Determine intent from goal
        intent = "unknown"
        goal_lower = reflection.goal.lower()
        intent_map = {
            "search": ["search", "find", "look up", "google"],
            "navigate": ["go to", "visit", "open", "browse"],
            "youtube": ["youtube", "video", "watch"],
            "booking": ["book", "flight", "hotel"],
            "email": ["email", "mail"],
            "research": ["research", "learn", "how to", "what is"],
            "shopping": ["buy", "purchase", "cheapest"],
            "download": ["download", "install"],
        }
        
        for intent_name, keywords in intent_map.items():
            if any(kw in goal_lower for kw in keywords):
                intent = intent_name
                break
        
        experience = TaskExperience(
            id=reflection.task_id,
            timestamp=datetime.now().isoformat(),
            goal=reflection.goal,
            intent=intent,
            total_steps=reflection.total_steps,
            status=result.get("status", "unknown"),
            sites_visited=reflection.reliable_sites + reflection.unreliable_sites,
            selectors_failed=reflection.fragile_selectors,
            errors=reflection.what_failed[:5],
            success_factors=reflection.what_worked[:5],
            failure_factors=reflection.what_failed[:3]
        )
        
        self.memory.record_experience(experience)
    
    def _log_reflection(self, r: ReflectionResult):
        """Print reflection summary."""
        status = "[OK]" if r.overall_success else "[ERROR]"
        print(f"\n{'─'*40}")
        print(f"[Reflection] {status} Task: {r.goal[:50]}")
        print(f"  Steps: {r.total_steps} | Wasted: {r.wasted_steps} | "
              f"Efficiency: {r.efficiency_score:.0%}")
        
        if r.what_worked:
            print(f"  [+] Worked: {', '.join(r.what_worked[:3])}")
        if r.what_failed:
            print(f"  [-] Failed: {', '.join(r.what_failed[:3])}")
        if r.improvements:
            print(f"  [IDEA] Improve: {', '.join(r.improvements[:2])}")
        print(f"{'─'*40}")


class SelfCritique:
    """
    Pre-execution self-critique.
    
    Before executing a plan, the agent questions itself:
    - Is this plan likely to succeed?
    - Are there known issues with the chosen approach?
    - Have similar plans failed before?
    - Is there a faster/safer approach?
    """
    
    def __init__(self, experience_memory: ExperienceMemory):
        self.memory = experience_memory
    
    def critique_plan(self, goal: str, task_graph: TaskGraph) -> Dict[str, Any]:
        """
        Critique a plan before execution.
        
        Returns:
        {
            "confidence": 0.85,
            "warnings": ["..."],
            "suggestions": ["..."],
            "risk_level": "low" | "medium" | "high"
        }
        """
        warnings = []
        suggestions = []
        confidence = 0.7  # Base confidence
        
        # ── Check past experience ──
        similar = self.memory.get_similar_experience(goal)
        if similar:
            if similar.status == "completed":
                confidence += 0.15
                suggestions.append(
                    f"Similar task '{similar.goal[:40]}' succeeded in {similar.total_steps} steps."
                )
            else:
                confidence -= 0.2
                warnings.append(
                    f"Similar task '{similar.goal[:40]}' FAILED. "
                    f"Reasons: {', '.join(similar.failure_factors[:2])}"
                )
        
        # ── Check site reliability ──
        for sg in task_graph.subgoals:
            url = sg.parameters.get("url", "")
            if url:
                from urllib.parse import urlparse
                try:
                    domain = urlparse(url).netloc
                    reliability = self.memory.get_site_reliability(domain)
                    if reliability < 0.5 and reliability > 0:
                        warnings.append(f"Site '{domain}' has low reliability ({reliability:.0%})")
                        confidence -= 0.1
                except Exception:
                    pass
        
        # ── Check selector reliability ──
        for sg in task_graph.subgoals:
            desc = sg.parameters.get("description", "")
            if desc:
                best = self.memory.get_best_selector(desc)
                if best and best != desc:
                    suggestions.append(f"Consider using '{best}' instead of '{desc}'")
        
        # ── Check plan complexity ──
        approval_count = sum(1 for s in task_graph.subgoals if s.requires_approval)
        if approval_count > 2:
            warnings.append(f"Plan requires {approval_count} user approvals — may be slow.")
        
        if len(task_graph.subgoals) > 8:
            warnings.append(f"Complex plan ({len(task_graph.subgoals)} subgoals). Higher failure risk.")
            confidence -= 0.1
        
        # ── Determine risk level ──
        has_payment = any(s.requires_approval and "payment" in s.approval_message.lower() 
                         for s in task_graph.subgoals)
        
        if has_payment:
            risk_level = "high"
        elif warnings:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        confidence = max(0.1, min(1.0, confidence))
        
        return {
            "confidence": round(confidence, 2),
            "warnings": warnings,
            "suggestions": suggestions,
            "risk_level": risk_level,
            "has_similar_experience": similar is not None,
        }
