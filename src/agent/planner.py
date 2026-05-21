"""
planner.py

The 'Prefrontal Cortex' of the Agent.
Decides WHAT to do based on BeliefState.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
from ..reasoning.belief_state import BeliefState

@dataclass
class Action:
    """A single atomic operation to be executed by a Tool."""
    tool_name: str
    command: str
    params: Dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""

from .goal.schema import GoalPlan

class GoalPlanner(ABC):
    """
    Phase R.1 Planner.
    Takes a structured GoalPlan -> Returns a sequence of Actions.
    """
    @abstractmethod
    def create_plan(self, goal_plan: GoalPlan, registry: Optional[Any] = None) -> List[Action]:
        pass

class RuleBasedPlanner(GoalPlanner):
    """
    Deterministic Planner for MVP.
    """
    def create_plan(self, goal_plan: GoalPlan, registry: Optional[Any] = None) -> List[Action]:
        actions = []
        intent = goal_plan.intent
        
        if intent == "OPEN_FILE":
            filename = goal_plan.entities.get("filename", "")
            actions.append(Action("desktop_control", "hotkey", {"keys": ["win", "s"]}, "Open Search"))
            actions.append(Action("desktop_control", "type", {"text": filename}, f"Type '{filename}'"))
            actions.append(Action("desktop_control", "hotkey", {"keys": ["enter"]}, "Open File"))
            return actions
            
        elif intent == "RUN_SHELL":
            cmd = goal_plan.entities.get("command", "")
            actions.append(Action("shell_execution", "run_command", {"command": cmd}, "Execute Command"))
            return actions
            
        elif intent == "FETCH_EMAIL":
            subject = goal_plan.entities.get("subject_filter", "")
            actions.append(Action(
                tool_name="email_communication",
                command="fetch_and_download",
                params={"subject_filter": subject, "save_dir": "./downloads"}, # Relative path for safety
                reasoning="Fetch email and download attachments"
            ))
            return actions
            
        elif intent == "SEND_EMAIL":
            to = goal_plan.entities.get("to", "")
            subject = goal_plan.entities.get("subject", "No Subject")
            body = goal_plan.entities.get("body", "")
            actions.append(Action(
                tool_name="email_communication",
                command="send_email",
                params={"to": to, "subject": subject, "body": body},
                reasoning="Send email via API"
            ))
            return actions

        elif intent == "UPDATE_EXCEL":
            master_path = goal_plan.entities.get("master_path")
            source_pattern = goal_plan.entities.get("source_pattern")
            # Construct full source path (Assumption: Downloads folder)
            source_path = f"./downloads/{source_pattern}"
            
            actions.append(Action(
                tool_name="excel_processing",
                command="append_to_master",
                params={"source_path": source_path, "master_path": master_path},
                reasoning="Append downloaded data to master sheet"
            ))
            return actions

        elif intent == "GENERATE_REPORT":
            master_path = goal_plan.entities.get("input_path") # Mapped from interpreter
            output_path = goal_plan.entities.get("output_path")
            
            actions.append(Action(
                tool_name="excel_processing",
                command="generate_report",
                params={"master_path": master_path, "output_path": output_path},
                reasoning="Generate summary report from master data"
            ))
            return actions
            
        elif intent == "SCREENSHOT":
            actions.append(Action("screen_vision", "capture", {}, "Take Screenshot"))
            return actions
            
        elif intent == "BROWSE_WEB":
            url = goal_plan.entities.get("url")
            search_query = goal_plan.entities.get("search_query")
            
            if search_query and not url:
                url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"
            
            if url:
                actions.append(Action(
                    tool_name="browser_control",
                    command="open_url",
                    params={"url": url},
                    reasoning=f"Navigate to {url}"
                ))
            actions.append(Action(
                tool_name="browser_control",
                command="scan_page",
                params={},
                reasoning="Scan page structure for perception"
            ))
            return actions

        # Fallback
        actions.append(Action("shell_execution", "run_command", {"command": f"echo 'No plan for intent: {intent}'"}, "Fallback"))
        return actions

# Deprecated: HeuristicPlanner
