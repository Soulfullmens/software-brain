"""
react_loop.py — ReACT Reasoning Loop (Think → Act → Observe → Reflect)

Inspired by MiroFish's ReportAgent which uses a ReACT pattern for
every chapter: Think about what info is needed → Call tools → Process results → Reflect.

CAPABILITIES:
    1. Structured reasoning cycle: Think → Act → Observe → Reflect
    2. Multi-tool orchestration — picks the best tool per step
    3. Self-critique — reflects on gathered info quality
    4. Configurable max iterations with early-stop
    5. Full execution trace for debugging
    6. Integrates with existing tool_protocol.py

MiroFish's ReACT in report_agent.py:
    - MAX_TOOL_CALLS_PER_SECTION = 5
    - MAX_REFLECTION_ROUNDS = 3
    - Tools: insight_forge, panorama_search, quick_search, interview_agents

Our version generalizes this to work with ANY set of tools.
"""
import time
import json
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Tuple
from enum import Enum


# ═══════════════════════════════════════════════════════
# DATA TYPES
# ═══════════════════════════════════════════════════════

class StepType(Enum):
    THINK = "think"
    ACT = "act"
    OBSERVE = "observe"
    REFLECT = "reflect"


@dataclass
class ReACTStep:
    """A single step in the ReACT cycle."""
    step_number: int
    step_type: StepType
    content: str                        # The thought, action, observation, or reflection
    tool_name: str = ""                 # If ACT step
    tool_params: Dict[str, Any] = field(default_factory=dict)
    tool_result: str = ""               # If OBSERVE step
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step_number,
            "type": self.step_type.value,
            "content": self.content[:500],
            "tool": self.tool_name,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ReACTResult:
    """Complete result of a ReACT reasoning loop."""
    goal: str
    conclusion: str                     # Final answer/conclusion
    steps: List[ReACTStep] = field(default_factory=list)
    total_rounds: int = 0
    tool_calls: int = 0
    total_time_ms: float = 0
    success: bool = True
    stop_reason: str = ""               # "complete", "max_rounds", "no_tools", "error"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "conclusion": self.conclusion[:1000],
            "total_rounds": self.total_rounds,
            "tool_calls": self.tool_calls,
            "total_time_ms": round(self.total_time_ms, 1),
            "success": self.success,
            "stop_reason": self.stop_reason,
            "steps": [s.to_dict() for s in self.steps],
        }

    def get_trace(self) -> str:
        """Human-readable execution trace."""
        lines = [f"ReACT Loop: {self.goal}", "=" * 50]
        for step in self.steps:
            icon = {"think": "🤔", "act": "⚡", "observe": "👁️", "reflect": "💭"}.get(step.step_type.value, "")
            lines.append(f"\n{icon} [{step.step_type.value.upper()}] (Step {step.step_number})")
            lines.append(f"  {step.content[:300]}")
            if step.tool_name:
                lines.append(f"  Tool: {step.tool_name}")
        lines.append(f"\n{'=' * 50}")
        lines.append(f"Conclusion: {self.conclusion[:500]}")
        lines.append(f"Rounds: {self.total_rounds} | Tools called: {self.tool_calls} | Time: {self.total_time_ms:.0f}ms")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# REACT PROMPTS
# ═══════════════════════════════════════════════════════

THINK_PROMPT = """You are in a Think→Act→Observe→Reflect reasoning loop.

GOAL: {goal}

AVAILABLE TOOLS:
{tools_description}

PREVIOUS STEPS:
{history}

THINK: What information do you still need? Which tool should you use next?
If you have enough information to answer the goal, say "SUFFICIENT" and provide your conclusion.

Respond in this JSON format:
{{
    "thought": "Your reasoning about what to do next",
    "action_needed": true/false,
    "tool_name": "tool_to_call (if action_needed)",
    "tool_params": {{"param": "value"}},
    "conclusion": "Your final answer (if action_needed is false)"
}}
"""

REFLECT_PROMPT = """You are reflecting on information gathered so far.

GOAL: {goal}

INFORMATION GATHERED:
{observations}

REFLECT: Is this information sufficient and accurate for the goal?
- What gaps remain?
- Is any information contradictory?
- What should we investigate next?

Respond in JSON:
{{
    "reflection": "Your assessment",
    "sufficient": true/false,
    "gaps": ["gap1", "gap2"],
    "next_focus": "What to investigate next (if not sufficient)"
}}
"""


# ═══════════════════════════════════════════════════════
# TOOLS INTERFACE
# ═══════════════════════════════════════════════════════

@dataclass
class ToolDefinition:
    """A tool that the ReACT loop can use."""
    name: str
    description: str
    parameters: Dict[str, str]          # param_name -> description
    execute_fn: Callable                # Function to call: (params) -> str

    def to_description(self) -> str:
        params_str = ", ".join(f"{k}: {v}" for k, v in self.parameters.items())
        return f"- {self.name}: {self.description}\n  Parameters: {params_str}"


# ═══════════════════════════════════════════════════════
# THE REACT LOOP
# ═══════════════════════════════════════════════════════

class ReACTLoop:
    """
    ReACT (Reasoning + Acting) loop for complex tasks.

    Implements: Think → Act → Observe → Reflect cycle.
    Each round, the agent thinks about what to do, executes a tool,
    observes the result, and reflects on whether more info is needed.

    Usage:
        loop = ReACTLoop(llm_fn=my_llm.generate)

        # Define tools
        loop.add_tool(ToolDefinition(
            name="search",
            description="Search the knowledge base",
            parameters={"query": "Search query"},
            execute_fn=lambda p: kb.search(p["query"])
        ))

        result = loop.run(
            goal="Find all information about Project X",
            max_rounds=5
        )
        print(result.conclusion)
    """

    def __init__(self, llm_fn: Callable = None,
                 max_rounds: int = 5,
                 max_tool_calls: int = 10,
                 reflect_every: int = 2):
        """
        Args:
            llm_fn: Function that takes (prompt: str) -> str
            max_rounds: Maximum Think→Act rounds
            max_tool_calls: Maximum total tool calls
            reflect_every: Add reflection step every N rounds
        """
        self._llm_fn = llm_fn
        self._max_rounds = max_rounds
        self._max_tool_calls = max_tool_calls
        self._reflect_every = reflect_every
        self._tools: Dict[str, ToolDefinition] = {}
        self._stats = {
            "loops_run": 0,
            "total_rounds": 0,
            "total_tool_calls": 0,
            "avg_rounds_per_loop": 0,
        }

    def add_tool(self, tool: ToolDefinition):
        """Register a tool for the ReACT loop to use."""
        self._tools[tool.name] = tool

    def remove_tool(self, name: str):
        """Remove a registered tool."""
        self._tools.pop(name, None)

    def run(self, goal: str, max_rounds: int = None,
            context: str = "") -> ReACTResult:
        """
        Run the full ReACT loop for a goal.

        Args:
            goal: What the agent needs to accomplish
            max_rounds: Override default max rounds
            context: Additional context to provide

        Returns:
            ReACTResult with conclusion and full trace
        """
        start_time = time.time()
        max_r = max_rounds or self._max_rounds
        steps: List[ReACTStep] = []
        step_counter = 0
        tool_calls = 0
        observations = []
        conclusion = ""
        stop_reason = "max_rounds"

        self._stats["loops_run"] += 1

        for round_num in range(max_r):
            # ── THINK ──
            step_counter += 1
            think_start = time.time()
            thought, action_needed, tool_name, tool_params, think_conclusion = self._think(
                goal, steps, context
            )

            think_step = ReACTStep(
                step_number=step_counter, step_type=StepType.THINK,
                content=thought,
                duration_ms=(time.time() - think_start) * 1000
            )
            steps.append(think_step)

            # Check if we're done thinking
            if not action_needed or think_conclusion:
                conclusion = think_conclusion or thought
                stop_reason = "complete"
                break

            # ── ACT ──
            if tool_name and tool_name in self._tools:
                step_counter += 1
                act_start = time.time()

                act_step = ReACTStep(
                    step_number=step_counter, step_type=StepType.ACT,
                    content=f"Calling tool: {tool_name}",
                    tool_name=tool_name, tool_params=tool_params,
                    duration_ms=0
                )

                # Execute tool
                try:
                    tool = self._tools[tool_name]
                    result = tool.execute_fn(tool_params)
                    tool_result = str(result)[:5000]
                    tool_calls += 1
                except Exception as e:
                    tool_result = f"Tool error: {e}"

                act_step.tool_result = tool_result
                act_step.duration_ms = (time.time() - act_start) * 1000
                steps.append(act_step)

                # ── OBSERVE ──
                step_counter += 1
                observe_step = ReACTStep(
                    step_number=step_counter, step_type=StepType.OBSERVE,
                    content=tool_result[:2000],
                )
                steps.append(observe_step)
                observations.append(f"[{tool_name}]: {tool_result[:500]}")

            elif tool_name:
                # Tool not found
                step_counter += 1
                steps.append(ReACTStep(
                    step_number=step_counter, step_type=StepType.OBSERVE,
                    content=f"Tool '{tool_name}' not available. Available: {list(self._tools.keys())}",
                ))

            # Check tool call limit
            if tool_calls >= self._max_tool_calls:
                stop_reason = "max_tool_calls"
                break

            # ── REFLECT (every N rounds) ──
            if (round_num + 1) % self._reflect_every == 0 and observations:
                step_counter += 1
                reflect_start = time.time()
                reflection, sufficient = self._reflect(goal, observations)

                steps.append(ReACTStep(
                    step_number=step_counter, step_type=StepType.REFLECT,
                    content=reflection,
                    duration_ms=(time.time() - reflect_start) * 1000
                ))

                if sufficient:
                    # Do one final Think to formulate conclusion
                    step_counter += 1
                    _, _, _, _, conclusion = self._think(goal, steps, context)
                    if conclusion:
                        stop_reason = "complete"
                        break

        # If no conclusion yet, synthesize from observations
        if not conclusion:
            conclusion = self._synthesize_conclusion(goal, observations, steps)

        total_time = (time.time() - start_time) * 1000

        self._stats["total_rounds"] += len([s for s in steps if s.step_type == StepType.THINK])
        self._stats["total_tool_calls"] += tool_calls
        if self._stats["loops_run"] > 0:
            self._stats["avg_rounds_per_loop"] = round(
                self._stats["total_rounds"] / self._stats["loops_run"], 1
            )

        return ReACTResult(
            goal=goal, conclusion=conclusion,
            steps=steps, total_rounds=round_num + 1 if 'round_num' in dir() else 0,
            tool_calls=tool_calls, total_time_ms=total_time,
            success=stop_reason == "complete",
            stop_reason=stop_reason,
        )

    # ═══════════════════════════════════════════════════════
    # INTERNAL REASONING STEPS
    # ═══════════════════════════════════════════════════════

    def _think(self, goal: str, steps: List[ReACTStep],
               context: str) -> Tuple[str, bool, str, Dict, str]:
        """
        Think step: decide what to do next.
        Returns: (thought, action_needed, tool_name, tool_params, conclusion)
        """
        if not self._llm_fn:
            return self._think_without_llm(goal, steps)

        # Build history
        history = self._build_history(steps)
        tools_desc = "\n".join(t.to_description() for t in self._tools.values())

        prompt = THINK_PROMPT.format(
            goal=goal, tools_description=tools_desc,
            history=history if history else "(No steps yet)"
        )
        if context:
            prompt = f"CONTEXT:\n{context}\n\n{prompt}"

        try:
            response = self._llm_fn(prompt)
            parsed = self._parse_json_safe(response)

            if parsed:
                thought = parsed.get("thought", response[:200])
                action_needed = parsed.get("action_needed", False)
                tool_name = parsed.get("tool_name", "")
                tool_params = parsed.get("tool_params", {})
                conclusion = parsed.get("conclusion", "")
                return thought, action_needed, tool_name, tool_params, conclusion
            else:
                return response[:300], False, "", {}, response[:500]

        except Exception as e:
            return f"Think error: {e}", False, "", {}, ""

    def _think_without_llm(self, goal: str,
                            steps: List[ReACTStep]) -> Tuple[str, bool, str, Dict, str]:
        """Fallback think without LLM — uses tools sequentially."""
        tool_names = list(self._tools.keys())
        used = set(s.tool_name for s in steps if s.tool_name)
        unused = [t for t in tool_names if t not in used]

        if unused:
            next_tool = unused[0]
            return (
                f"Need to gather information using {next_tool}",
                True, next_tool, {"query": goal}, ""
            )
        else:
            observations = [s.content for s in steps if s.step_type == StepType.OBSERVE]
            summary = " | ".join(observations[:5])
            return (
                "All tools used, synthesizing conclusion",
                False, "", {}, f"Based on gathered information: {summary[:500]}"
            )

    def _reflect(self, goal: str, observations: List[str]) -> Tuple[str, bool]:
        """Reflect on gathered information. Returns (reflection, is_sufficient)."""
        if not self._llm_fn:
            return f"Gathered {len(observations)} observations.", len(observations) >= 3

        obs_text = "\n".join(f"- {obs}" for obs in observations[-10:])
        prompt = REFLECT_PROMPT.format(goal=goal, observations=obs_text)

        try:
            response = self._llm_fn(prompt)
            parsed = self._parse_json_safe(response)
            if parsed:
                return parsed.get("reflection", response[:300]), parsed.get("sufficient", False)
            return response[:300], False
        except Exception:
            return "Reflection error", False

    def _synthesize_conclusion(self, goal: str, observations: List[str],
                                steps: List[ReACTStep]) -> str:
        """Create a conclusion from all gathered information."""
        if not observations:
            return "No information gathered."

        if self._llm_fn:
            obs_text = "\n".join(f"- {obs}" for obs in observations[:10])
            prompt = f"Given the GOAL: {goal}\n\nAnd these observations:\n{obs_text}\n\nProvide a concise conclusion."
            try:
                return self._llm_fn(prompt)[:2000]
            except Exception:
                pass

        return f"Gathered {len(observations)} pieces of information about: {goal}. " + \
               " | ".join(observations[:3])

    def _build_history(self, steps: List[ReACTStep]) -> str:
        """Build a concise history string from steps."""
        if not steps:
            return ""
        lines = []
        for s in steps[-10:]:  # Last 10 steps
            prefix = {"think": "THOUGHT", "act": "ACTION", "observe": "OBSERVED", "reflect": "REFLECTION"}.get(
                s.step_type.value, "STEP"
            )
            content = s.content[:200]
            if s.tool_name:
                content = f"[{s.tool_name}] {content}"
            lines.append(f"{prefix}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _parse_json_safe(text: str) -> Optional[Dict]:
        """Safely parse JSON from LLM response."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try code block
        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text) if 'import re' else None
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding { ... }
        import re as _re
        brace = _re.search(r'\{[\s\S]*\}', text)
        if brace:
            try:
                return json.loads(brace.group())
            except json.JSONDecodeError:
                pass

        return None

    def get_stats(self) -> Dict[str, Any]:
        return dict(self._stats)
