"""
swarm_orchestrator.py — True Multi-Agent Swarm Orchestration

Takes the agent beyond a single ReACT loop into a multi-threaded swarm.
A Manager Agent breaks down a massive task and spawns specialized
Worker Agents (each with their own archetype, tools, and ReACT loop).
Workers run in parallel and communicate via a Shared Memory Board.

CAPABILITIES:
    1. SwarmManager: Task decomposition and worker dispatch.
    2. WorkerAgent: Autonomous parallel sub-agent.
    3. SharedBoard: Thread-safe whiteboard for agents to share insights.
    4. Auto-Aggregation: Manager synthesizes worker findings into a final result.
"""
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
import uuid

from .react_loop import ReACTLoop, ToolDefinition, ReACTResult
from .persona_engine import PersonaEngine, PersonaProfile


# ═══════════════════════════════════════════════════════
# DATA TYPES
# ═══════════════════════════════════════════════════════

@dataclass
class SwarmMessage:
    """A message posted to the shared board."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    sender_id: str = ""
    sender_role: str = ""
    content: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class SharedBoard:
    """Thread-safe whiteboard for intra-swarm communication."""
    messages: List[SwarmMessage] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def post(self, sender_id: str, sender_role: str, content: str):
        with self.lock:
            self.messages.append(SwarmMessage(
                sender_id=sender_id,
                sender_role=sender_role,
                content=content
            ))

    def read_all(self) -> str:
        with self.lock:
            if not self.messages:
                return "The shared board is empty."
            lines = ["--- SWARM SHARED BOARD ---"]
            for m in self.messages[-20:]:  # Keep context window reasonable
                lines.append(f"[{m.sender_role} {m.sender_id}] {m.content}")
            return "\n".join(lines)


@dataclass
class SwarmResult:
    """Final result from a swarm execution."""
    goal: str
    final_synthesis: str
    manager_trace: str
    worker_results: Dict[str, ReACTResult] = field(default_factory=dict)
    total_time_ms: float = 0


# ═══════════════════════════════════════════════════════
# SWARM ORCHESTRATOR
# ═══════════════════════════════════════════════════════

class WorkerAgent:
    """An autonomous sub-agent running in a background thread."""
    def __init__(self, agent_id: str, role: str, goal: str,
                 persona: PersonaProfile, llm_fn: Callable,
                 tools: List[ToolDefinition], board: SharedBoard):
        self.id = agent_id
        self.role = role
        self.goal = goal
        self.persona = persona
        self.llm_fn = llm_fn
        self.tools = tools
        self.board = board
        self.result: Optional[ReACTResult] = None
        self._thread: Optional[threading.Thread] = None

    def _run(self):
        """Execute the worker's specific ReACT loop."""
        # Inject persona into LLM fn
        def wrapped_llm(prompt: str) -> str:
            # Read shared board for every reasoning step
            board_context = self.board.read_all()
            full_prompt = (
                f"You are a '{self.persona.name}' ({self.persona.archetype}).\n"
                f"{self.persona.system_prompt_addon}\n\n"
                f"{board_context}\n\n"
                f"{prompt}"
            )
            return self.llm_fn(full_prompt)

        loop = ReACTLoop(llm_fn=wrapped_llm, max_rounds=5)
        
        # Add a tool to post to the board
        loop.add_tool(ToolDefinition(
            name="post_to_board",
            description="Share a crucial finding with the rest of the swarm.",
            parameters={"message": "The insight to share"},
            execute_fn=self._post_to_board_tool
        ))

        for t in self.tools:
            loop.add_tool(t)

        self.board.post(self.id, self.role, f"Starting task: {self.goal}")
        t0 = time.time()
        
        self.result = loop.run(goal=self.goal)
        
        duration = int((time.time() - t0) * 1000)
        self.board.post(self.id, self.role, f"Finished in {duration}ms. Conclusion: {self.result.conclusion}")

    def _post_to_board_tool(self, params: Dict) -> str:
        msg = params.get("message", "")
        if msg:
            self.board.post(self.id, self.role, msg)
            return "Message posted successfully."
        return "Failed: empty message."

    def start(self):
        self._thread = threading.Thread(target=self._run, name=f"Worker-{self.role}-{self.id}")
        self._thread.start()

    def join(self):
        if self._thread:
            self._thread.join()


class SwarmOrchestrator:
    """
    Spawns and manages a multi-agent swarm.
    """
    def __init__(self, llm_fn: Callable, persona_engine: PersonaEngine,
                 base_tools: List[ToolDefinition]):
        self.llm_fn = llm_fn
        self.persona_engine = persona_engine
        self.base_tools = base_tools

    def orchestrate(self, global_goal: str) -> SwarmResult:
        """
        1. Manager analyzes goal and creates a plan.
        2. Spawns N workers with specific personas and sub-goals.
        3. Waits for all to finish.
        4. Synthesizes final result.
        """
        start_time = time.time()
        board = SharedBoard()
        board.post("Manager", "Manager", f"Global Swarm Goal: {global_goal}")

        # In a full implementation, the LLM determines the sub-goals. 
        # For safety/determinism in v1, we use a robust heuristic based on the goal complexity.
        sub_tasks = self._decompose_goal(global_goal)
        
        workers: List[WorkerAgent] = []
        for i, task in enumerate(sub_tasks):
            # Select best persona for the sub-task
            persona = self.persona_engine.select_persona(task["goal"])
            
            worker = WorkerAgent(
                agent_id=f"W{i+1}",
                role=persona.name,
                goal=task["goal"],
                persona=persona,
                llm_fn=self.llm_fn,
                tools=self.base_tools,
                board=board
            )
            workers.append(worker)

        # Start swarm
        for w in workers:
            w.start()

        # Wait for swarm
        for w in workers:
            w.join()

        # Gather results
        worker_results = {w.id: w.result for w in workers if w.result}
        
        # Final Manager Synthesis
        board_history = board.read_all()
        synthesis_prompt = (
            f"GLOBAL GOAL: {global_goal}\n\n"
            f"SWARM ACTIVITY LOG:\n{board_history}\n\n"
            f"Synthesize the swarm's findings into a single, cohesive, excellent final response."
        )
        
        try:
            final_synthesis = self.llm_fn(synthesis_prompt)
        except Exception:
            final_synthesis = "Swarm synthesis failed. Consult individual worker logs."

        return SwarmResult(
            goal=global_goal,
            final_synthesis=final_synthesis,
            manager_trace=board_history,
            worker_results=worker_results,
            total_time_ms=(time.time() - start_time) * 1000
        )

    def _decompose_goal(self, goal: str) -> List[Dict[str, str]]:
        """
        Break the goal down.
        A smart implementation calls the LLM. 
        If LLM is unavailable or for speed, use heuristics.
        """
        try:
            prompt = (
                f"Break this goal down into 2-3 distinct parallel sub-tasks for a swarm of AI agents.\n"
                f"Goal: {goal}\n"
                "Return valid JSON:\n"
                '{"tasks": [{"goal": "Specific sub-goal"}]}'
            )
            response = self.llm_fn(prompt)
            import json, re
            match = re.search(r'\{[\s\S]*\}', response)
            if match:
                data = json.loads(match.group())
                return data.get("tasks", [{"goal": goal}])
        except Exception:
            pass

        # Fallback heuristic
        if "code" in goal.lower() or "build" in goal.lower():
            return [
                {"goal": f"Research architecture and requirements for: {goal}"},
                {"goal": f"Write the core logic and code for: {goal}"},
            ]
        elif "analyze" in goal.lower() or "research" in goal.lower():
            return [
                {"goal": f"Gather raw data and facts for: {goal}"},
                {"goal": f"Analyze trends and implications for: {goal}"},
            ]
            
        return [{"goal": goal}]
