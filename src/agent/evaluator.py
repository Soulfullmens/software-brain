"""
evaluator.py

The 'Reality Check' of the Agent.
Determines if an action actually succeeded.
Deterministic, Brutal, and Domain-Specific.
"""
from dataclasses import dataclass
from typing import Optional, Any
from .goal.schema import GoalPlan
from .planner import Action
from ..reasoning.belief_state import BeliefState

@dataclass
class EvaluationResult:
    success: bool
    confidence: float
    failure_reason: Optional[str] = None
    terminal: bool = False # Should execution stop?

class StateEvaluator:
    def evaluate(self, goal_plan: GoalPlan, action: Action, result: str, belief: BeliefState) -> EvaluationResult:
        intent = goal_plan.intent
        
        # Route by Intent (Domain Specific Rules)
        if intent == "RUN_SHELL":
            return self._eval_shell(result)
            
        if intent == "SCREENSHOT":
            return self._eval_screenshot(result)
            
        if intent == "OPEN_FILE":
            return self._eval_open_file(result)
            
        if intent == "FETCH_EMAIL":
            return self._eval_fetch_email(result)
            
        if intent == "SEND_EMAIL":
            return self._eval_send_email(result)
            
        if intent == "UPDATE_EXCEL":
            return self._eval_update_excel(result)
            
        if intent == "GENERATE_REPORT":
            return self._eval_generate_report(result)
            
        if intent == "BROWSE_WEB":
            return self._eval_browse_web(result)
            
        # Default / Fallback
        return EvaluationResult(
            success=False, 
            confidence=0.0, 
            failure_reason=f"No evaluator for intent {intent}",
            terminal=True
        )

    def _eval_browse_web(self, result: Any) -> EvaluationResult:
        if isinstance(result, dict):
            if "error" in result:
                return EvaluationResult(False, 0.9, f"Browser Error: {result['error']}", False)
            if result.get("status") == "opened" or result.get("page_type"):
                return EvaluationResult(True, 1.0, None, False)
            if result.get("element_count", 0) > 0:
                return EvaluationResult(True, 0.9, None, False)
        return EvaluationResult(True, 0.5, None, False)  # Permissive for browsing

    def _eval_shell(self, result: str) -> EvaluationResult:
        text = str(result).lower()
        
        # Failure Indicators
        errors = [
            "error", "not recognized", "denied", "failed", 
            "cannot find", "file not found", "no such file", 
            "directory does not exist"
        ]
        
        if any(err in text for err in errors):
            return EvaluationResult(
                success=False,
                confidence=0.9,
                failure_reason=f"Shell Error: {result[:50]}...",
                terminal=True
            )
            
        if len(text.strip()) == 0:
            return EvaluationResult(
                success=False,
                confidence=0.6,
                failure_reason="Empty output from shell command",
                terminal=False # Maybe retriable?
            )
            
        # Success
        return EvaluationResult(
            success=True,
            confidence=0.9,
            failure_reason=None,
            terminal=False
        )

    def _eval_screenshot(self, result: str) -> EvaluationResult:
        text = str(result).lower()
        if "error" in text or "failed" in text:
            return EvaluationResult(False, 0.9, f"Screenshot failed: {result}", True)
            
        # Heuristic: Result usually contains path "Saved to ..."
        if "saved to" in text or ".png" in text:
            return EvaluationResult(True, 0.95, None, False)
            
        return EvaluationResult(False, 0.5, "Unknown screenshot result format", False)

    def _eval_open_file(self, result: str) -> EvaluationResult:
        text = str(result).lower()
        if "error" in text:
            return EvaluationResult(False, 0.9, f"Open File failed: {result}", True)
            
        return EvaluationResult(True, 0.5, None, False) # Low confidence without visual confirm

    def _eval_fetch_email(self, result: Any) -> EvaluationResult:
        # Result is a Dict from fetch_and_download
        if isinstance(result, dict):
            if "error" in result:
                return EvaluationResult(False, 0.9, f"Fetch failed: {result['error']}", True)
            if "files" in result:
                return EvaluationResult(True, 1.0, None, False)
        
        text = str(result).lower()
        if "error" in text:
            return EvaluationResult(False, 0.9, f"Fetch failed: {result}", True)
            
        return EvaluationResult(True, 0.7, None, False)
        
    def _eval_send_email(self, result: Any) -> EvaluationResult:
        # Result is Dict
        if isinstance(result, dict):
            if result.get("status") == "sent":
                return EvaluationResult(True, 1.0, None, False)
            if "error" in result:
                return EvaluationResult(False, 0.9, f"Send failed: {result['error']}", True)
                
        text = str(result).lower()
        if "error" in text:
            return EvaluationResult(False, 0.9, f"Send failed: {result}", True)
            
        return EvaluationResult(False, 0.5, "Unknown send result", False)

    def _eval_update_excel(self, result: Any) -> EvaluationResult:
        if isinstance(result, dict):
            if "error" in result:
                 return EvaluationResult(False, 0.9, f"Excel Error: {result['error']}", True)
            if result.get("rows_added", 0) > 0:
                 return EvaluationResult(True, 1.0, None, False)
        return EvaluationResult(False, 0.8, "No rows added or unknown result", False)

    def _eval_generate_report(self, result: Any) -> EvaluationResult:
        if isinstance(result, dict):
             if "error" in result:
                 return EvaluationResult(False, 0.9, f"Report Error: {result['error']}", True)
             if "report_path" in result:
                 return EvaluationResult(True, 1.0, None, False)
        return EvaluationResult(False, 0.8, "No report path returned", False)
