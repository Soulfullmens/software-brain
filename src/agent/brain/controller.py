"""
controller.py

The Executive Controller — the Agent's Brain.
Phase R.3 + R.4 + Self-Improvement: Full Intelligent Self-Evolving Engine.

Architecture:
    1. THINK     : Decompose goal into TaskGraph (Intelligence Layer)
    2. VALIDATE  : Pre-execution plan validation (PlanValidator)
    3. RISK      : Score risk level (RiskEstimator)
    4. CRITIQUE  : Self-critique before execution (SelfCritique)
    5. SAFETY    : Every action through SafetyGovernor
    6. EXECUTE   : Walk the TaskGraph
    7. OBSERVE   : Check results, update memory
    8. RECOVER   : StrategyEngine provides alternatives
    9. REFLECT   : Post-task self-reflection (ReflectionEngine)
    10. LEARN    : Extract experience patterns (ExperienceMemory)

WHY THIS BEATS A STATIC LLM:
- Claude forgets everything between sessions. This agent remembers.
- Claude can't learn from failures. This agent improves with every task.
- Claude has no concept of site reliability. This agent tracks it.
- Claude can't self-critique. This agent validates plans before executing.
"""
import json
import time
from typing import Dict, Any, Optional, List
from .action_schema import AgentDecision, AgentAction, AgentThought, parse_llm_response
from .working_memory import WorkingMemory
from .task_graph import TaskGraph, SubGoal, SubGoalStatus
from .safety_governor import SafetyGovernor, SafetyVerdict
from .strategy_engine import StrategyEngine
from .intelligence import TaskDecomposer, SearchIntelligence
from .experience_memory import ExperienceMemory
from .reflection import ReflectionEngine, SelfCritique
from .plan_validator import PlanValidator, RiskEstimator, ToolConfidenceScorer


# ── System Prompt for LLM ──

SYSTEM_PROMPT = """You are an autonomous computer operator agent. You control a browser and other tools to complete tasks.
You are a PERSONAL ASSISTANT. You think deeply before acting.

AVAILABLE TOOLS:
- browser_control: Control a web browser
  Commands: open_url(url), click(selector), type(selector, text), scan_page(), 
            find_element(description), find_and_click(description), find_and_type(description, text),
            get_page_model(), screenshot(filename), back(), refresh(), close(), hover(selector)
- email_communication: Send and receive emails
  Commands: fetch_and_download(subject_filter), send_email(to, subject, body)
- excel_processing: Work with Excel files
  Commands: append_to_master(data), compute_summary(input_path), generate_report(input_path, output_path)
- shell_execution: Run shell commands
  Commands: run_command(command)

RESPONSE FORMAT (strict JSON only):
{
  "thought": {
    "observation": "What I see right now",
    "reasoning": "Why this specific action is the best next step",
    "plan_status": "What I've done and what remains",
    "confidence": 0.8
  },
  "action": {
    "tool": "browser_control",
    "command": "find_and_click",
    "parameters": {"description": "search button"}
  },
  "is_complete": false,
  "is_stuck": false,
  "needs_human": false,
  "message": ""
}

CRITICAL RULES:
1. ALWAYS respond with valid JSON. Never free text.
2. Use find_and_click/find_and_type for semantic element interaction.
3. Use scan_page before interacting with a new page.
4. NEVER click payment/purchase buttons or fill credit card info.
5. If task is done, set is_complete=true with a detailed summary message.
6. If you need user input, set needs_human=true with a clear question.
7. Think before acting — explain your reasoning.
"""


class ExecutiveController:
    """
    The Agent's Brain — Self-Improving Intelligent Task Execution Engine.
    
    BEATS A STATIC LLM BY:
    1. Learning from every task (experience memory)
    2. Validating plans before execution (plan validator)
    3. Scoring risk before acting (risk estimator)
    4. Self-critiquing based on past failures (self-critique)
    5. Reflecting after every task (reflection engine)
    6. Using historical data for decisions (confidence scorer)
    """
    
    def __init__(self, tools: Dict[str, Any], llm_client=None, max_steps: int = 20,
                 user_callback=None, data_dir: str = "./agent_data"):
        self.tools = tools
        self.llm_client = llm_client
        self.max_steps = max_steps
        self.user_callback = user_callback
        
        # R.4 Core Systems
        self.memory = WorkingMemory(max_steps=max_steps)
        self.safety = SafetyGovernor()
        self.strategy = StrategyEngine()
        self.decomposer = TaskDecomposer()
        self.search_intel = SearchIntelligence()
        
        # Self-Improvement Systems (NEW)
        self.experience = ExperienceMemory(storage_dir=data_dir)
        self.reflection = ReflectionEngine(self.experience)
        self.critique = SelfCritique(self.experience)
        self.validator = PlanValidator(tools, self.experience)
        self.risk_estimator = RiskEstimator(self.experience)
        self.confidence_scorer = ToolConfidenceScorer(self.experience)
        
        # Current task graph
        self.task_graph: Optional[TaskGraph] = None
        
        # Collected results
        self.collected_results: List[Dict] = []
    
    def execute_goal(self, goal: str) -> Dict[str, Any]:
        """
        Execute a goal with the FULL self-improving pipeline.
        
        Pipeline:
        1. THINK      → Decompose goal into TaskGraph
        2. VALIDATE   → Check plan validity (tools, deps, params)
        3. RISK SCORE → Estimate risk level
        4. CRITIQUE   → Check against past experience
        5. WALK       → Execute each subgoal
        6. SAFETY     → Check every action
        7. ACT        → Execute via tools
        8. OBSERVE    → Update memory, extract data
        9. RECOVER    → Strategy switch on failure
        10. REFLECT   → Learn from the execution
        """
        start_time = time.time()
        self.memory = WorkingMemory(goal=goal, max_steps=self.max_steps)
        self.strategy.reset()
        self.collected_results.clear()
        
        print(f"\n{'='*60}")
        print(f"  🧠 EXECUTIVE BRAIN [SELF-IMPROVING ENGINE]")
        print(f"  Goal: {goal}")
        print(f"{'='*60}")
        
        # ── Step 1: THINK — Decompose ──
        print(f"\n[Think] Decomposing goal...")
        self.task_graph = self.decomposer.decompose(goal)
        print(f"[Think] Plan: {len(self.task_graph.subgoals)} subgoals")
        for i, sg in enumerate(self.task_graph.subgoals, 1):
            approval = " ⚠️APPROVAL" if sg.requires_approval else ""
            deps = f" (after: {', '.join(sg.depends_on)})" if sg.depends_on else ""
            print(f"  {i}. {sg.name}{deps}{approval}")
        
        # ── Step 2: VALIDATE — Pre-execution check ──
        validation = self.validator.validate(self.task_graph)
        if not validation["valid"]:
            print(f"[Validator] ❌ Plan invalid! {validation['error_count']} errors")
            # Don't execute invalid plans — report errors
            result = self._final_result("plan_invalid", 
                f"Plan validation failed: {validation['error_count']} errors. "
                f"Issues: {[str(i) for i in validation['issues'][:3]]}")
            self._post_reflect(goal, result, start_time)
            return result
        
        # ── Step 3: RISK SCORE ──
        risk = self.risk_estimator.estimate_risk(self.task_graph)
        print(f"[Risk] Level: {risk['risk_level']} | Score: {risk['risk_score']}/10 | {risk['recommendation']}")
        
        if risk["risk_level"] == "critical":
            result = self._final_result("risk_too_high",
                f"⚠️ CRITICAL RISK: {risk['recommendation']}. "
                f"Risk factors: {[f['factor'] for f in risk['risk_factors']]}")
            self._post_reflect(goal, result, start_time)
            return result
        
        # ── Step 4: CRITIQUE — Learn from past ──
        critique = self.critique.critique_plan(goal, self.task_graph)
        print(f"[Critique] Confidence: {critique['confidence']:.0%} | "
              f"Warnings: {len(critique['warnings'])} | "
              f"Similar experience: {'Yes' if critique['has_similar_experience'] else 'No'}")
        
        if critique["warnings"]:
            for w in critique["warnings"][:2]:
                print(f"  ⚠️ {w}")
        if critique["suggestions"]:
            for s in critique["suggestions"][:2]:
                print(f"  💡 {s}")
        
        # ── Step 5: Confidence Score ──
        plan_confidence = self.confidence_scorer.score_plan(self.task_graph)
        print(f"[Confidence] Plan confidence: {plan_confidence:.0%}")
        
        # ── Step 6: WALK the TaskGraph ──
        result = self._execute_task_graph()
        
        # ── Step 7: REFLECT — Learn from execution ──
        self._post_reflect(goal, result, start_time)
        
        return result
    
    def _execute_task_graph(self) -> Dict[str, Any]:
        """Execute the current task graph."""
        while True:
            if self.memory.is_over_limit():
                print(f"\n[Brain] ⚠ Step limit ({self.max_steps})")
                return self._final_result("limit_reached", "Step limit reached")
            
            subgoal = self.task_graph.get_next_subgoal()
            
            if not subgoal:
                if self.task_graph.status == "completed":
                    msg = self._build_completion_message()
                    print(f"\n[Brain] ✅ Goal completed!")
                    return self._final_result("completed", msg)
                
                if self.task_graph.status == "failed":
                    print(f"\n[Brain] ❌ Goal failed")
                    return self._final_result("failed",
                        f"Could not complete: {self.task_graph.progress_summary()}")
                
                if self.task_graph.status == "blocked":
                    blocked = [s for s in self.task_graph.subgoals
                              if s.status == SubGoalStatus.BLOCKED]
                    if blocked:
                        msg = blocked[0].approval_message
                        print(f"\n[Brain] 🔒 Blocked: {msg}")
                        return self._final_result("needs_human", msg)
                
                print(f"\n[Brain] ⚠ No actionable subgoals")
                return self._final_result("stuck", "No more actionable subgoals")
            
            # Execute subgoal
            print(f"\n{'─'*40}")
            print(f"[Subgoal] {subgoal.name}: {subgoal.description}")
            
            # Check confidence for this action
            action_confidence = self.confidence_scorer.score_action(
                subgoal.tool, subgoal.command, subgoal.parameters
            )
            if action_confidence < 0.4:
                print(f"[Confidence] ⚠ Low confidence ({action_confidence:.0%}) for this action")
            
            if subgoal.requires_approval:
                print(f"[Safety] ⚠️ Requires approval: {subgoal.approval_message}")
                self.task_graph.block(subgoal.id, subgoal.approval_message)
                continue
            
            self.task_graph.activate(subgoal.id)
            
            if not subgoal.tool:
                self.task_graph.complete(subgoal.id)
                continue
            
            # Safety check
            page_context = {
                "page_type": self.memory.current_page_type,
                "url": self.memory.current_url
            }
            safety_check = self.safety.check_action(
                subgoal.tool, subgoal.command, subgoal.parameters, page_context
            )
            
            if safety_check.verdict == SafetyVerdict.ASK_USER:
                print(f"[Safety] 🔒 {safety_check.reason}")
                self.task_graph.block(subgoal.id, safety_check.message_to_user)
                continue
            
            if safety_check.verdict == SafetyVerdict.BLOCK:
                print(f"[Safety] 🚫 BLOCKED: {safety_check.reason}")
                self.task_graph.fail(subgoal.id, f"Safety blocked: {safety_check.reason}")
                continue
            
            # Execute
            tool = self.tools.get(subgoal.tool)
            if not tool:
                print(f"[Act] ✗ Tool not found: {subgoal.tool}")
                self.task_graph.fail(subgoal.id, f"Tool '{subgoal.tool}' not found")
                continue
            
            print(f"[Act] {subgoal.tool}.{subgoal.command}({subgoal.parameters})")
            
            try:
                result = tool.run(subgoal.command, **subgoal.parameters)
                success = self._observe(subgoal, result)
                
                if success:
                    self.task_graph.complete(subgoal.id, result)
                    self.memory.record_step(
                        subgoal.tool, subgoal.command, subgoal.parameters,
                        result, True, subgoal.description
                    )
                    if isinstance(result, dict):
                        self.collected_results.append(result)
                    
                    print(f"[Act] ✓ {str(result)[:100]}")
                else:
                    error_msg = str(result.get("error", result) if isinstance(result, dict) else result)[:100]
                    print(f"[Act] ✗ Failed: {error_msg}")
                    
                    alternatives = self.strategy.get_alternatives(
                        subgoal.tool, subgoal.command, subgoal.parameters, error_msg
                    )
                    
                    if alternatives:
                        alt = alternatives[0]
                        print(f"[Strategy] Trying: {alt.description}")
                        self.strategy.record_attempt(alt.name)
                        subgoal.tool = alt.tool
                        subgoal.command = alt.command
                        subgoal.parameters = alt.parameters
                        subgoal.status = SubGoalStatus.PENDING
                    else:
                        self.task_graph.fail(subgoal.id, error_msg)
                    
                    self.memory.record_step(
                        subgoal.tool, subgoal.command, subgoal.parameters,
                        result, False, error_msg
                    )
                
            except Exception as e:
                error_msg = str(e)[:150]
                print(f"[Act] ✗ Exception: {error_msg}")
                self.task_graph.fail(subgoal.id, error_msg)
                self.memory.record_step(
                    subgoal.tool, subgoal.command, subgoal.parameters,
                    {"error": error_msg}, False, error_msg
                )
            
            print(f"[Progress] {self.task_graph.progress_summary()}")
    
    def _observe(self, subgoal: SubGoal, result: Any) -> bool:
        """Observe and learn from action results."""
        if isinstance(result, dict):
            if "error" in result:
                return False
            
            if subgoal.tool == "browser_control":
                if result.get("url"):
                    self.memory.update_environment(url=result["url"])
                if result.get("page_type"):
                    self.memory.update_environment(
                        page_type=result["page_type"],
                        summary=result.get("summary", ""),
                        elements=result.get("element_count", 0)
                    )
                if result.get("title"):
                    self.memory.update_environment(summary=result.get("title", ""))
                
                if subgoal.command == "get_page_model" and result.get("elements"):
                    recs = self.search_intel.extract_recommendations(result)
                    if recs.get("total_results", 0) > 0:
                        self.collected_results.append({
                            "type": "recommendations",
                            "data": recs
                        })
            
            return True
        
        text = str(result).lower()
        return "error" not in text and "failed" not in text
    
    def _post_reflect(self, goal: str, result: Dict, start_time: float):
        """Post-task reflection — learn from what happened."""
        try:
            reflection = self.reflection.reflect(
                goal=goal,
                task_graph=self.task_graph,
                working_memory=self.memory,
                result=result,
                start_time=start_time
            )
            
            # Log learning stats
            stats = self.experience.get_stats()
            print(f"\n[Learning] Total tasks: {stats['total_tasks']} | "
                  f"Success rate: {stats['success_rate']:.0%} | "
                  f"Known sites: {stats['known_sites']} | "
                  f"Patterns: {stats['learned_patterns']}")
        except Exception as e:
            print(f"[Reflection] Error during reflection: {e}")
    
    def _build_completion_message(self) -> str:
        """Build completion message with recommendations."""
        lines = [f"✅ Task completed: {self.memory.goal}"]
        lines.append(f"Steps: {self.memory.current_step}")
        
        if self.memory.current_url:
            lines.append(f"Final page: {self.memory.current_url}")
        
        for result in self.collected_results:
            if isinstance(result, dict) and result.get("type") == "recommendations":
                recs = result["data"]
                formatted = self.search_intel.format_results_for_user(recs)
                lines.append(f"\n{formatted}")
        
        return "\n".join(lines)
    
    def _final_result(self, status: str, message: str) -> Dict[str, Any]:
        """Package final result."""
        return {
            "status": status,
            "steps": self.memory.current_step,
            "message": message,
            "url": self.memory.current_url,
            "page_type": self.memory.current_page_type,
            "errors": self.memory.error_log,
            "task_progress": self.task_graph.progress_summary() if self.task_graph else "",
            "collected_data": self.collected_results,
            "memory_context": self.memory.to_context_string()
        }
    
    def get_learning_stats(self) -> Dict[str, Any]:
        """Get the agent's learning statistics."""
        return self.experience.get_stats()
    
    # ── LLM Mode (Production) ──
    
    def execute_goal_llm(self, goal: str) -> Dict[str, Any]:
        """Execute a goal using LLM for every decision."""
        if not self.llm_client:
            return self.execute_goal(goal)
        
        start_time = time.time()
        self.memory = WorkingMemory(goal=goal, max_steps=self.max_steps)
        
        print(f"\n{'='*60}")
        print(f"  [EXECUTIVE BRAIN: LLM + SELF-IMPROVING]")
        print(f"  Goal: {goal}")
        print(f"{'='*60}")
        
        while True:
            if self.memory.is_over_limit():
                result = self._final_result("limit_reached", "Step limit reached")
                self._post_reflect(goal, result, start_time)
                return result
            
            if self.memory.is_stuck():
                result = self._final_result("stuck",
                    f"Stuck after {self.memory.consecutive_failures} failures")
                self._post_reflect(goal, result, start_time)
                return result
            
            self._perceive()
            decision = self._decide_llm()
            
            if decision.is_complete:
                result = self._final_result("completed", decision.message)
                self._post_reflect(goal, result, start_time)
                return result
            if decision.is_stuck:
                result = self._final_result("stuck", decision.message)
                self._post_reflect(goal, result, start_time)
                return result
            if decision.needs_human:
                result = self._final_result("needs_human", decision.message)
                self._post_reflect(goal, result, start_time)
                return result
            if not decision.action:
                self.memory.record_step("none", "no_action", {},
                                        "LLM produced no action", False)
                continue
            
            # Safety check
            page_ctx = {"page_type": self.memory.current_page_type,
                       "url": self.memory.current_url}
            safety = self.safety.check_action(
                decision.action.tool, decision.action.command,
                decision.action.parameters, page_ctx
            )
            
            if safety.verdict != SafetyVerdict.PROCEED:
                print(f"[Safety] 🔒 {safety.reason}")
                result = self._final_result("needs_human", safety.message_to_user)
                self._post_reflect(goal, result, start_time)
                return result
            
            # Act
            result_data = self._act(decision.action)
            success = self._observe_action(decision.action, result_data)
            
            self.memory.record_step(
                decision.action.tool, decision.action.command,
                decision.action.parameters, result_data, success
            )
    
    def _perceive(self):
        """Scan current environment."""
        browser = self.tools.get("browser_control")
        if browser and hasattr(browser, '_page') and browser._page:
            try:
                scan = browser.run("scan_page")
                if isinstance(scan, dict) and "error" not in scan:
                    self.memory.update_environment(
                        url=scan.get("url", ""),
                        page_type=scan.get("page_type", ""),
                        summary=scan.get("summary", ""),
                        elements=scan.get("element_count", 0)
                    )
            except Exception:
                pass
    
    def _decide_llm(self) -> AgentDecision:
        """LLM-driven decision with experience context."""
        context = self.memory.to_context_string()
        
        # Add experience insights
        exp_stats = self.experience.get_stats()
        if exp_stats["total_tasks"] > 0:
            context += f"\n\nLEARNING: {exp_stats['total_tasks']} past tasks, "
            context += f"{exp_stats['success_rate']:.0%} success rate."
        
        prompt = f"Current state:\n{context}\n\nDecide the next action. JSON only."
        
        try:
            response = self.llm_client.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt
            )
            decision = parse_llm_response(response)
            print(f"[Brain/LLM] {decision.thought.reasoning[:80]}")
            return decision
        except Exception as e:
            print(f"[Brain/LLM] Error: {e}")
            return AgentDecision(
                thought=AgentThought(observation="LLM failed", reasoning=str(e)),
                is_stuck=True,
                message=f"LLM error: {e}"
            )
    
    def _act(self, action: AgentAction) -> Any:
        """Execute an action."""
        tool = self.tools.get(action.tool)
        if not tool:
            return {"error": f"Tool '{action.tool}' not found"}
        
        print(f"[Act] {action.tool}.{action.command}({action.parameters})")
        try:
            result = tool.run(action.command, **action.parameters)
            print(f"[Act] Result: {str(result)[:100]}")
            return result
        except Exception as e:
            print(f"[Act] ✗ {e}")
            return {"error": str(e)}
    
    def _observe_action(self, action: AgentAction, result: Any) -> bool:
        """Observe an action result (LLM mode)."""
        if isinstance(result, dict):
            if "error" in result:
                return False
            if action.tool == "browser_control":
                if result.get("url"):
                    self.memory.update_environment(url=result["url"])
                if result.get("page_type"):
                    self.memory.update_environment(
                        page_type=result["page_type"],
                        summary=result.get("summary", ""),
                        elements=result.get("element_count", 0)
                    )
            return True
        return "error" not in str(result).lower()
