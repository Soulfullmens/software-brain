"""
tool_protocol.py

Claude-Style Agentic Tool Use Protocol.

This is the KEY module that makes this agent behave like Claude's tool use.
It implements the full agentic loop:

    User Message → LLM thinks → LLM calls tool(s) → Results fed back
    → LLM thinks again → More tool calls OR final answer

Claude's Tool Use Architecture:
1. Tools are defined with JSON Schema (name, description, parameters)
2. LLM decides whether to call tools or respond directly
3. Multiple tools can be called in parallel
4. Tool results are injected back into conversation
5. Loop continues until LLM produces a final text response
6. The LLM sees ALL tool results in context

This module bridges between the existing Tool base class and the
LLM router's tool calling capability.
"""
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .llm_router import (
    LLMRouter, LLMRequest, LLMResponse, Message, Role,
    ToolDefinition, ToolCall,
)
from .tool import Tool
from .conversation_manager import ConversationManager


# ────────────────────────────────────────────────────────
#  Tool Registry — Converts existing tools to Claude format
# ────────────────────────────────────────────────────────

@dataclass
class RegisteredTool:
    """A tool registered for LLM use with full schema."""
    definition: ToolDefinition
    handler: Callable[..., Any]
    requires_approval: bool = False
    risk_level: str = "low"  # low, medium, high, critical


class ToolRegistry:
    """
    Converts existing Tool instances into Claude-style tool definitions
    and manages execution.
    """

    def __init__(self):
        self.tools: Dict[str, RegisteredTool] = {}

    def register(self, name: str, description: str,
                 parameters: Dict[str, Any],
                 handler: Callable[..., Any],
                 requires_approval: bool = False,
                 risk_level: str = "low"):
        """Register a tool for LLM use."""
        self.tools[name] = RegisteredTool(
            definition=ToolDefinition(
                name=name,
                description=description,
                parameters=parameters,
            ),
            handler=handler,
            requires_approval=requires_approval,
            risk_level=risk_level,
        )

    def register_from_tool(self, tool: Tool, commands: Dict[str, Dict]):
        """
        Register an existing Tool instance's commands.

        commands: {
            "open_url": {
                "description": "Navigate browser to a URL",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The URL to open"}
                    },
                    "required": ["url"]
                },
                "risk_level": "low"
            }
        }
        """
        for cmd_name, cmd_info in commands.items():
            full_name = f"{tool.name}__{cmd_name}"

            def make_handler(t, c):
                """Closure to capture tool and command."""
                def handler(**kwargs):
                    return t.run(c, **kwargs)
                return handler

            self.register(
                name=full_name,
                description=cmd_info.get("description", f"{tool.name}.{cmd_name}"),
                parameters=cmd_info.get("parameters", {"type": "object", "properties": {}}),
                handler=make_handler(tool, cmd_name),
                requires_approval=cmd_info.get("requires_approval", False),
                risk_level=cmd_info.get("risk_level", "low"),
            )

    def get_definitions(self) -> List[ToolDefinition]:
        """Get all tool definitions for the LLM."""
        return [t.definition for t in self.tools.values()]

    def execute(self, tool_call: ToolCall) -> Dict[str, Any]:
        """Execute a tool call and return the result."""
        reg = self.tools.get(tool_call.name)
        if not reg:
            return {"error": f"Unknown tool: {tool_call.name}", "success": False}

        try:
            result = reg.handler(**tool_call.arguments)
            # Normalize result to dict
            if isinstance(result, dict):
                return {**result, "success": True}
            elif isinstance(result, str):
                return {"result": result, "success": True}
            else:
                return {"result": str(result), "success": True}
        except Exception as e:
            return {"error": str(e), "success": False}


# ────────────────────────────────────────────────────────
#  Agentic Tool Use Loop
# ────────────────────────────────────────────────────────

@dataclass
class ToolUseStep:
    """A single step in the agentic tool use loop."""
    step_number: int
    tool_calls: List[ToolCall]
    tool_results: List[Dict[str, Any]]
    llm_text: str = ""
    thinking: str = ""
    latency_ms: float = 0.0


@dataclass
class AgentLoopResult:
    """Complete result of an agentic tool use session."""
    final_response: str
    steps: List[ToolUseStep] = field(default_factory=list)
    total_tool_calls: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    status: str = "completed"  # completed, max_steps, error, needs_approval


class AgentToolLoop:
    """
    The core agentic loop — like Claude's tool use.

    This is the beating heart of the agent. It:
    1. Sends messages + tool definitions to the LLM
    2. If LLM returns tool_calls → execute them
    3. Feed tool results back to LLM
    4. Repeat until LLM returns final text (no tool calls)

    Usage:
        registry = ToolRegistry()
        registry.register("search", "Search the web", {...}, search_fn)
        registry.register("calculator", "Do math", {...}, calc_fn)

        loop = AgentToolLoop(llm=router, tools=registry)
        result = loop.run(
            user_message="What's the weather in Tokyo?",
            system="You are a helpful assistant with access to tools."
        )
        print(result.final_response)
    """

    def __init__(self, llm: LLMRouter, tools: ToolRegistry,
                 conversation: Optional[ConversationManager] = None,
                 max_steps: int = 25,
                 approval_callback: Optional[Callable[[str, Dict], bool]] = None):
        self.llm = llm
        self.tools = tools
        self.conversation = conversation
        self.max_steps = max_steps
        self.approval_callback = approval_callback

    def run(self, user_message: str, system: str = "",
            session_id: Optional[str] = None,
            provider: Optional[str] = None,
            **kwargs) -> AgentLoopResult:
        """
        Run the full agentic tool use loop.

        The LLM will call tools as needed and iterate until it
        produces a final text response.
        """
        result = AgentLoopResult()
        t0 = time.time()

        # Build initial messages
        if session_id and self.conversation:
            self.conversation.add_user_message(session_id, user_message)
            messages = self.conversation.get_context_messages(session_id)
            system = system or self.conversation.get_system_prompt(session_id)
        else:
            messages = [Message(Role.USER, user_message)]

        tool_defs = self.tools.get_definitions()

        for step_num in range(1, self.max_steps + 1):
            # Call LLM with tools
            response = self.llm.chat_with_tools(
                messages=messages,
                tools=tool_defs,
                system=system,
                provider=provider,
                **kwargs,
            )
            result.total_tokens += response.input_tokens + response.output_tokens

            # If no tool calls → final answer
            if not response.tool_calls:
                result.final_response = response.content
                result.status = "completed"
                if response.content:
                    result.steps.append(ToolUseStep(
                        step_number=step_num,
                        tool_calls=[],
                        tool_results=[],
                        llm_text=response.content,
                    ))
                break

            # Execute tool calls
            step = ToolUseStep(
                step_number=step_num,
                tool_calls=response.tool_calls,
                tool_results=[],
                llm_text=response.content,
            )

            # Add assistant message with tool calls
            messages.append(Message(
                Role.ASSISTANT,
                content=response.content or "",
                tool_calls=[{
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    }
                } for tc in response.tool_calls],
            ))

            # Execute each tool call
            for tc in response.tool_calls:
                # Check approval for high-risk tools
                reg = self.tools.tools.get(tc.name)
                if reg and reg.requires_approval and self.approval_callback:
                    approved = self.approval_callback(tc.name, tc.arguments)
                    if not approved:
                        tool_result = {
                            "error": "User denied permission for this action.",
                            "success": False,
                        }
                        step.tool_results.append(tool_result)
                        messages.append(Message(
                            Role.TOOL,
                            content=json.dumps(tool_result),
                            tool_call_id=tc.id,
                            name=tc.name,
                        ))
                        continue

                # Execute
                tool_result = self.tools.execute(tc)
                step.tool_results.append(tool_result)
                result.total_tool_calls += 1

                # Truncate large results to prevent context overflow
                result_str = json.dumps(tool_result, default=str)
                if len(result_str) > 10000:
                    result_str = result_str[:10000] + "... [truncated]"

                messages.append(Message(
                    Role.TOOL,
                    content=result_str,
                    tool_call_id=tc.id,
                    name=tc.name,
                ))

            step.latency_ms = (time.time() - t0) * 1000
            result.steps.append(step)

        else:
            result.status = "max_steps"
            result.final_response = (
                "I've reached the maximum number of steps. "
                "Here's what I've done so far:\n" +
                "\n".join(
                    f"Step {s.step_number}: Called {len(s.tool_calls)} tools"
                    for s in result.steps
                )
            )

        result.total_latency_ms = (time.time() - t0) * 1000

        # Save to conversation history
        if session_id and self.conversation and result.final_response:
            self.conversation.add_assistant_message(session_id, result.final_response)

        return result

    def run_with_thinking(self, user_message: str, system: str = "",
                          thinking_budget: int = 10,
                          **kwargs) -> AgentLoopResult:
        """
        Extended run with explicit thinking steps before tool use.
        The agent reasons first, then acts — like Claude's extended thinking.
        """
        # Phase 1: Think about the approach
        thinking_prompt = (
            f"Before taking any action, think carefully about this request:\n\n"
            f"{user_message}\n\n"
            f"Consider:\n"
            f"1. What information do I need?\n"
            f"2. What tools are available?\n"
            f"3. What's the most efficient approach?\n"
            f"4. What could go wrong?\n"
            f"5. What's the expected output?\n\n"
            f"Think step by step, then proceed with tool calls."
        )

        return self.run(thinking_prompt, system=system, **kwargs)


# ────────────────────────────────────────────────────────
#  Default Tool Definitions for Existing Tools
# ────────────────────────────────────────────────────────

BROWSER_COMMANDS = {
    "open_url": {
        "description": "Navigate the browser to a specific URL",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to navigate to"}
            },
            "required": ["url"],
        },
        "risk_level": "low",
    },
    "find_and_click": {
        "description": "Find an element on the page by description and click it",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Natural language description of the element to click"}
            },
            "required": ["description"],
        },
        "risk_level": "low",
    },
    "find_and_type": {
        "description": "Find an input element and type text into it",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Description of the input field"},
                "text": {"type": "string", "description": "Text to type"},
            },
            "required": ["description", "text"],
        },
        "risk_level": "low",
    },
    "scan_page": {
        "description": "Scan the current page and extract all visible elements",
        "parameters": {"type": "object", "properties": {}},
        "risk_level": "low",
    },
    "get_page_model": {
        "description": "Get a structured model of the current page content",
        "parameters": {"type": "object", "properties": {}},
        "risk_level": "low",
    },
    "screenshot": {
        "description": "Take a screenshot of the current page",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Filename to save screenshot as"}
            },
            "required": ["filename"],
        },
        "risk_level": "low",
    },
    "back": {
        "description": "Go back to the previous page",
        "parameters": {"type": "object", "properties": {}},
        "risk_level": "low",
    },
    "extract_text": {
        "description": "Extract all text content from the current page",
        "parameters": {"type": "object", "properties": {}},
        "risk_level": "low",
    },
}

EMAIL_COMMANDS = {
    "read_unread": {
        "description": "Read unread emails, optionally filtered by subject",
        "parameters": {
            "type": "object",
            "properties": {
                "subject_filter": {"type": "string", "description": "Filter emails by subject (optional)"}
            },
        },
        "risk_level": "low",
    },
    "send_email": {
        "description": "Send an email to a recipient",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body content"},
            },
            "required": ["to", "subject", "body"],
        },
        "risk_level": "medium",
        "requires_approval": True,
    },
}

SHELL_COMMANDS = {
    "run_command": {
        "description": "Execute a shell command and return the output",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
            },
            "required": ["command"],
        },
        "risk_level": "high",
        "requires_approval": True,
    },
}

FILE_COMMANDS = {
    "read_file": {
        "description": "Read the contents of a file",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read"},
            },
            "required": ["path"],
        },
        "risk_level": "low",
    },
    "write_file": {
        "description": "Write content to a file",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
        "risk_level": "medium",
        "requires_approval": True,
    },
    "list_directory": {
        "description": "List files and folders in a directory",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path"},
            },
            "required": ["path"],
        },
        "risk_level": "low",
    },
}


def create_default_registry(tools: Dict[str, Tool]) -> ToolRegistry:
    """Create a ToolRegistry with all default tool commands registered."""
    registry = ToolRegistry()

    command_maps = {
        "browser_control": BROWSER_COMMANDS,
        "email_communication": EMAIL_COMMANDS,
        "shell_execution": SHELL_COMMANDS,
    }

    for tool_name, commands in command_maps.items():
        tool = tools.get(tool_name)
        if tool:
            registry.register_from_tool(tool, commands)

    # Register file system tools directly (not from Tool class)
    for cmd_name, cmd_info in FILE_COMMANDS.items():
        registry.register(
            name=f"filesystem__{cmd_name}",
            description=cmd_info["description"],
            parameters=cmd_info["parameters"],
            handler=_make_fs_handler(cmd_name),
            requires_approval=cmd_info.get("requires_approval", False),
            risk_level=cmd_info.get("risk_level", "low"),
        )

    return registry


def _make_fs_handler(command: str):
    """Create file system handlers."""
    import os

    def read_file(path: str) -> Dict:
        if not os.path.exists(path):
            return {"error": f"File not found: {path}"}
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"content": content, "size": len(content)}

    def write_file(path: str, content: str) -> Dict:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"written": len(content), "path": path}

    def list_directory(path: str) -> Dict:
        if not os.path.isdir(path):
            return {"error": f"Not a directory: {path}"}
        entries = os.listdir(path)
        return {"entries": entries, "count": len(entries)}

    handlers = {
        "read_file": read_file,
        "write_file": write_file,
        "list_directory": list_directory,
    }
    return handlers.get(command, lambda **kw: {"error": "Unknown command"})
