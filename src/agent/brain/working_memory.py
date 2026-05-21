"""
working_memory.py

Short-Term Working Memory for the Executive Brain.
Phase R.3: Tracks context across the Goal→Act→Observe loop.

This is the agent's 'scratch pad' — what it knows RIGHT NOW
about the current task, what it has tried, and what happened.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class MemoryEntry:
    """A single step in the agent's working memory."""
    step: int
    timestamp: str
    action_tool: str
    action_command: str
    action_params: Dict[str, Any]
    result_summary: str       # Abbreviated result
    success: bool
    observation: str = ""     # What the agent noticed


@dataclass
class WorkingMemory:
    """
    The agent's short-term memory for a single task execution.
    
    Contains:
    - Original goal
    - Step-by-step history
    - Current page/environment state
    - Error log
    - Constraints
    """
    # Goal
    goal: str = ""
    goal_decomposition: List[str] = field(default_factory=list)
    
    # Step History
    steps: List[MemoryEntry] = field(default_factory=list)
    current_step: int = 0
    max_steps: int = 20       # Safety limit
    
    # Environment State
    current_url: str = ""
    current_page_type: str = ""
    current_page_summary: str = ""
    available_elements: int = 0
    
    # Task State
    completed_subtasks: List[str] = field(default_factory=list)
    pending_subtasks: List[str] = field(default_factory=list)
    
    # Errors
    consecutive_failures: int = 0
    error_log: List[str] = field(default_factory=list)
    
    # Constraints
    user_constraints: Dict[str, Any] = field(default_factory=dict)
    
    def record_step(self, tool: str, command: str, params: Dict, 
                    result: Any, success: bool, observation: str = ""):
        """Record an executed step."""
        self.current_step += 1
        
        # Summarize result (truncate for memory efficiency)
        if isinstance(result, dict):
            result_summary = str({k: str(v)[:80] for k, v in list(result.items())[:5]})
        else:
            result_summary = str(result)[:200]
        
        self.steps.append(MemoryEntry(
            step=self.current_step,
            timestamp=datetime.now().strftime("%H:%M:%S"),
            action_tool=tool,
            action_command=command,
            action_params=params,
            result_summary=result_summary,
            success=success,
            observation=observation
        ))
        
        # Track failures
        if success:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1
            self.error_log.append(f"Step {self.current_step}: {result_summary[:100]}")
    
    def update_environment(self, url: str = "", page_type: str = "", 
                           summary: str = "", elements: int = 0):
        """Update the current environment state."""
        if url:
            self.current_url = url
        if page_type:
            self.current_page_type = page_type
        if summary:
            self.current_page_summary = summary
        self.available_elements = elements
    
    def mark_subtask_complete(self, subtask: str):
        """Mark a subtask as completed."""
        if subtask in self.pending_subtasks:
            self.pending_subtasks.remove(subtask)
        if subtask not in self.completed_subtasks:
            self.completed_subtasks.append(subtask)
    
    def is_stuck(self) -> bool:
        """Check if the agent is stuck (3+ consecutive failures)."""
        return self.consecutive_failures >= 3
    
    def is_over_limit(self) -> bool:
        """Check if max steps exceeded."""
        return self.current_step >= self.max_steps
    
    def to_context_string(self) -> str:
        """
        Produce a concise context summary for the LLM prompt.
        This is what the Brain 'sees' when deciding what to do next.
        """
        lines = [
            f"GOAL: {self.goal}",
            f"STEP: {self.current_step}/{self.max_steps}",
            f"URL: {self.current_url or 'N/A'}",
            f"PAGE TYPE: {self.current_page_type or 'N/A'}",
            f"PAGE SUMMARY: {self.current_page_summary or 'N/A'}",
            f"ELEMENTS: {self.available_elements}",
        ]
        
        if self.completed_subtasks:
            lines.append(f"COMPLETED: {', '.join(self.completed_subtasks)}")
        if self.pending_subtasks:
            lines.append(f"PENDING: {', '.join(self.pending_subtasks)}")
        
        # Last 3 steps
        if self.steps:
            lines.append("\nRECENT ACTIONS:")
            for entry in self.steps[-3:]:
                status = "✓" if entry.success else "✗"
                lines.append(
                    f"  {status} Step {entry.step}: {entry.action_tool}.{entry.action_command} "
                    f"-> {entry.result_summary[:80]}"
                )
        
        if self.error_log:
            lines.append(f"\nERRORS: {'; '.join(self.error_log[-2:])}")
        
        return "\n".join(lines)
