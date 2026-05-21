"""
core.py

The Agent Body.
Orchestrates the Phase R.1 Loop:
Interpreter -> Planner -> Executor
"""
import time
import traceback
from typing import Dict, List, Optional, Any
from ..reasoning.belief_state import BeliefState, Evidence
from .tool import Tool
from .tools.email import EmailTool
from .tools.excel import ExcelTool
from .tools.browser import BrowserControlTool
from .tools.world_monitor import WorldMonitorTool
from .planner import GoalPlanner, Action
from .goal.interpreter import GoalInterpreter
from .observability.logger import WorkflowLogger
from .storage.registry import ProcessedRegistry
from .evaluator import StateEvaluator

class Agent:
    def __init__(self, planner: GoalPlanner, tools: List[Tool] = None):
        self.planner = planner
        if tools is None:
            from .tools.desktop import DesktopTool
            from .tools.screen import ScreenTool
            from .tools.shell import ShellTool
            self.tools = {
                t.name: t for t in [
                    DesktopTool(),
                    ScreenTool(),
                    ShellTool(),
                    EmailTool(backend_type="mock"),
                    ExcelTool(),
                    BrowserControlTool(headless=True),
                    WorldMonitorTool(backend_type="mock")
                ]
            }
        else:
            self.tools = {t.name: t for t in tools}
        self.belief = BeliefState()
        self.interpreter = GoalInterpreter()
        self.logger = WorkflowLogger()
        self.registry = ProcessedRegistry()
        self.evaluator = StateEvaluator() # Now integrated
        
    def set_goal(self, goal: str):
        self.belief.goal = goal
        self.belief.iteration = 0
        self.belief.action_history = []
        
    def run(self, goal_str: str) -> List[Dict[str, Any]]:
        """
        Execute a goal string end-to-end (Production Loop).
        """
        run_id = self.logger.start_run(goal_str)
        results_log = []
        
        try:
            # 1. Interpret
            print(f"\n[Agent] Interpreting: '{goal_str}'")
            goal_plan = self.interpreter.interpret(goal_str)
            self.belief.goal = goal_str
            self.belief.goal_plan = goal_plan
            
            self.logger.log_step("Interpret", "GoalInterpreter", "SUCCESS", goal_plan.__dict__)
            
            if goal_plan.requires_approval:
                 print(f"[Agent] WARNING: Plan requires approval (Mock: Auto-approving for MVP)")
            
            # 2. Plan (Deterministic)
            actions = self.planner.create_plan(goal_plan)
            print(f"[Agent] Plan Generated: {len(actions)} steps")
            self.logger.log_step("Plan", "GoalPlanner", "SUCCESS", [a.__dict__ for a in actions])
            
            # 3. Execute Loop
            for i, action in enumerate(actions):
                self.belief.iteration += 1
                print(f"\n[Agent] Step {i+1}: {action.tool_name} -> {action.command}")
                
                # Check Tool
                tool = self.tools.get(action.tool_name)
                if not tool:
                    error_msg = f"Tool {action.tool_name} not found"
                    self.logger.log_error(f"Step {i+1}", error_msg)
                    results_log.append({"action": action, "result": {"error": error_msg}, "evaluation": None})
                    break
                    
                # Execute
                try:
                    result = tool.run(action.command, **action.params)
                except Exception as e:
                    result = {"error": str(e)}
                    print(f"  Result: ERROR - {e}")
                    self.logger.log_error(f"Step {i+1}", str(e))
                else:
                    print(f"  Result: {str(result)[:100]}...")
                    
                self.logger.log_step(f"Execute {i+1}", action.tool_name, "COMPLETED", result)
                
                # 4. Evaluate
                verdict = self.evaluator.evaluate(goal_plan, action, result, self.belief)
                print(f"  Evaluation: Success={verdict.success} Reason={verdict.failure_reason}")
                self.logger.log_step(f"Evaluate {i+1}", "StateEvaluator", 
                                     "SUCCESS" if verdict.success else "FAILURE", 
                                     verdict.__dict__)
                
                # Update Belief
                self.belief.last_success = verdict.success
                self.belief.last_failure_reason = verdict.failure_reason
                
                # 5. Idempotency Registration (Side Effect)
                if verdict.success and action.command == "fetch_and_download":
                    if isinstance(result, dict):
                        email_id = result.get("email_id")
                        files = result.get("files", [])
                        for f in files:
                            self.registry.mark_processed(email_id, f)
                            print(f"[Agent] Registry: Marked '{f}' from '{email_id}' as processed.")
                
                results_log.append({"action": action, "result": result, "evaluation": verdict})
                
                if verdict.terminal:
                    print(f"[Agent] Terminating due to failure: {verdict.failure_reason}")
                    self.logger.end_run("FAILED", [str(r) for r in results_log])
                    return results_log

            # 6. Final Status
            self.logger.end_run("SUCCESS", [str(r) for r in results_log])
            return results_log
            
        except Exception as e:
            traceback.print_exc()
            self.logger.log_error("Global", str(e))
            self.logger.end_run("CRASHED")
            return results_log
