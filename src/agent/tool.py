"""
tool.py

Abstract Base Class for all Agent Tools + ToolResult data class.
Tools are the effectors of the agent (Hands, Eyes, Voice).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ────────────────────────────────────────────────────────
#  Tool Result
# ────────────────────────────────────────────────────────

@dataclass
class ToolResult:
    """
    Standard result returned by every tool execution.
    success  — did the action complete without error?
    output   — human-readable output / data payload
    error    — error message (if success is False)
    metadata — optional extra data (timings, certificates, etc.)
    """
    success: bool
    output: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ────────────────────────────────────────────────────────
#  Tool ABC
# ────────────────────────────────────────────────────────

class Tool(ABC):
    """
    Abstract interface for a tool.
    Each tool must define a name, description, and a run method.
    """

    def __init__(self, name: str = "unnamed_tool",
                 description: str = "No description provided."):
        self.name = name
        self.description = description

    @abstractmethod
    def run(self, action: str, **kwargs) -> Any:
        """
        Execute the tool with the provided action and arguments.
        Returns ToolResult or any serialisable data.
        """
        pass

    def validate(self, **kwargs) -> bool:
        """Optional: Validate arguments before execution."""
        return True

    def get_schema(self) -> Dict:
        """Optional: Return JSON-Schema for the tool's parameters."""
        return {}
