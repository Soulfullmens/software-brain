"""
autonomous_agent.py

The Autonomous Agent — Self-Improving Personal Operator.
Top-level entry point with full intelligence integration.

THIS AGENT GETS SMARTER OVER TIME.
- First run: Uses heuristic planning (still effective)
- After 10 runs: Knows which sites/selectors work
- After 50 runs: Outperforms static LLM planning on repeat tasks
- After 100 runs: Has domain-specific intelligence that Claude can't match

Usage:
    with AutonomousAgent() as agent:
        # First task — baseline intelligence
        result = agent.run("Search for best AI tools")
        
        # Second task — already learning from first
        result = agent.run("Watch videos about Python")
        
        # Check what it learned
        print(agent.learning_stats())
"""
from typing import Dict, Any, Optional, Callable
from .brain.controller import ExecutiveController
from .tool import Tool
from .tools.browser import BrowserControlTool
from .tools.email import EmailTool
from .tools.excel import ExcelTool
from .tools.world_monitor import WorldMonitorTool


class AutonomousAgent:
    """
    Self-Improving Personal Operator Agent.
    
    ADVANTAGES OVER STATIC LLM:
    1. Persistent memory — remembers across sessions
    2. Experience learning — improves with every task
    3. Self-critique — catches problems before execution
    4. Plan validation — rejects bad plans
    5. Risk scoring — never acts on critical-risk tasks without permission
    6. Tool confidence — knows which actions are reliable
    
    Capabilities:
    - Smart task decomposition
    - Multi-step autonomous execution
    - Safety-first (NEVER touches payments without asking)
    - Intelligent recovery (tries alternatives when stuck)
    - Search & recommend
    - YouTube, flight booking, form filling, comparison
    """
    
    def __init__(self, headless: bool = True, llm_client=None,
                 max_steps: int = 20, user_callback: Callable = None,
                 data_dir: str = "./agent_data"):
        # Initialize tools
        self.tools: Dict[str, Tool] = {}
        self._init_tools(headless)
        
        # Initialize brain with self-improvement
        self.controller = ExecutiveController(
            tools=self.tools,
            llm_client=llm_client,
            max_steps=max_steps,
            user_callback=user_callback,
            data_dir=data_dir
        )
        
        self.llm_client = llm_client
        self.task_history: list = []
    
    def _init_tools(self, headless: bool):
        """Register all available tools."""
        tool_list = [
            BrowserControlTool(headless=headless),
            EmailTool(backend_type="mock"),
            ExcelTool(),
            WorldMonitorTool(backend_type="mock"),
        ]
        
        try:
            from .tools.shell import ShellTool
            tool_list.append(ShellTool())
        except Exception:
            pass
        
        try:
            from .tools.desktop import DesktopTool
            tool_list.append(DesktopTool())
        except Exception:
            pass
        
        try:
            from .tools.screen import ScreenTool
            tool_list.append(ScreenTool())
        except Exception:
            pass
        
        self.tools = {t.name: t for t in tool_list}
    
    def run(self, goal: str) -> Dict[str, Any]:
        """
        Execute a goal with full self-improving intelligence.
        
        The agent will:
        1. Understand your goal (decompose)
        2. Validate the plan (pre-check)
        3. Score risk (safety assessment)
        4. Self-critique using past experience
        5. Execute with safety checks
        6. Recover from failures intelligently
        7. Reflect and learn from the execution
        
        Returns:
            Result dict with status, message, and learning data
        """
        if self.llm_client:
            result = self.controller.execute_goal_llm(goal)
        else:
            result = self.controller.execute_goal(goal)
        
        self.task_history.append({
            "goal": goal,
            "status": result["status"],
            "steps": result["steps"]
        })
        
        return result
    
    def learning_stats(self) -> Dict[str, Any]:
        """Get the agent's learning statistics."""
        stats = self.controller.get_learning_stats()
        stats["session_tasks"] = len(self.task_history)
        stats["session_success_rate"] = (
            sum(1 for t in self.task_history if t["status"] == "completed") / 
            max(1, len(self.task_history))
        )
        return stats
    
    def get_task_graph(self):
        """Get the current task graph."""
        return self.controller.task_graph
    
    def approve_and_continue(self, subgoal_id: str) -> Dict[str, Any]:
        """Approve a blocked subgoal and continue."""
        if self.controller.task_graph:
            self.controller.task_graph.approve(subgoal_id)
            return self.controller.execute_goal(self.controller.memory.goal)
        return {"status": "error", "message": "No active task graph"}
    
    def shutdown(self):
        """Clean up all resources."""
        browser = self.tools.get("browser_control")
        if browser:
            try:
                browser.run("close")
            except Exception:
                pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.shutdown()
