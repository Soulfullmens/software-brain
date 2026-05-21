"""
action_schema.py

Structured Action Schema for the Executive Brain.
Phase R.3: Forces LLM output into valid, parseable actions.

The LLM must output ONLY these structures — no free text.
This is the contract between the Brain and the Body.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
import json


@dataclass
class AgentThought:
    """
    The agent's internal reasoning before acting.
    This is the 'inner monologue'.
    """
    observation: str = ""     # What I see (page state, result of last action)
    reasoning: str = ""       # Why I'm choosing this action
    plan_status: str = ""     # Where I am in the overall plan
    confidence: float = 0.5

    
@dataclass
class AgentAction:
    """
    A single valid action the agent can take.
    This is the output format the LLM must produce.
    """
    tool: str                        # e.g., "browser_control", "email_communication"
    command: str                     # e.g., "open_url", "find_and_click", "scan_page"
    parameters: Dict[str, Any] = field(default_factory=dict)
    thought: Optional[AgentThought] = None
    

@dataclass
class AgentDecision:
    """
    Complete decision output from the Executive Brain.
    Contains thought process + chosen action + termination flag.
    """
    thought: AgentThought
    action: Optional[AgentAction] = None
    is_complete: bool = False        # Goal is satisfied
    is_stuck: bool = False           # Cannot proceed
    needs_human: bool = False        # Requires human input
    message: str = ""                # Message to user (if needs_human or is_complete)


# ── Serialization ──

def decision_to_dict(d: AgentDecision) -> dict:
    """Serialize a decision to dict (for logging)."""
    return {
        "thought": {
            "observation": d.thought.observation,
            "reasoning": d.thought.reasoning,
            "plan_status": d.thought.plan_status,
            "confidence": d.thought.confidence
        },
        "action": {
            "tool": d.action.tool,
            "command": d.action.command,
            "parameters": d.action.parameters
        } if d.action else None,
        "is_complete": d.is_complete,
        "is_stuck": d.is_stuck,
        "needs_human": d.needs_human,
        "message": d.message
    }


def parse_llm_response(raw: str) -> AgentDecision:
    """
    Parse raw LLM JSON output into an AgentDecision.
    Handles malformed output gracefully.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code blocks
        import re
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError:
                return AgentDecision(
                    thought=AgentThought(
                        observation="LLM output was not valid JSON",
                        reasoning=f"Raw: {raw[:200]}",
                        confidence=0.0
                    ),
                    is_stuck=True,
                    message="Could not parse LLM response"
                )
        else:
            return AgentDecision(
                thought=AgentThought(
                    observation="LLM output was not valid JSON",
                    reasoning=f"Raw: {raw[:200]}",
                    confidence=0.0
                ),
                is_stuck=True,
                message="Could not parse LLM response"
            )
    
    # Parse thought
    thought_data = data.get("thought", {})
    thought = AgentThought(
        observation=thought_data.get("observation", ""),
        reasoning=thought_data.get("reasoning", ""),
        plan_status=thought_data.get("plan_status", ""),
        confidence=thought_data.get("confidence", 0.5)
    )
    
    # Parse action
    action = None
    action_data = data.get("action")
    if action_data and isinstance(action_data, dict):
        action = AgentAction(
            tool=action_data.get("tool", ""),
            command=action_data.get("command", ""),
            parameters=action_data.get("parameters", {})
        )
    
    return AgentDecision(
        thought=thought,
        action=action,
        is_complete=data.get("is_complete", False),
        is_stuck=data.get("is_stuck", False),
        needs_human=data.get("needs_human", False),
        message=data.get("message", "")
    )
