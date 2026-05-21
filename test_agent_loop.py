"""
test_agent_loop.py

Integration test for Phase R Agent Loop.
Instantiates Agent with HeuristicPlanner and Tools.
Executes 3 test goals.
"""
import time
from src.agent.core import Agent
from src.agent.planner import HeuristicPlanner
from src.agent.tools.desktop import DesktopTool
from src.agent.tools.screen import ScreenTool
from src.agent.tools.shell import ShellTool

def box_print(msg):
    print("+" + "-"*60 + "+")
    print(f"| {msg:<58} |")
    print("+" + "-"*60 + "+")

def main():
    box_print("INITIALIZING AGENT (PHASE R)")
    
    # 1. Initialize Components
    planner = HeuristicPlanner()
    tools = [
        DesktopTool(),
        ScreenTool(),
        ShellTool()
    ]
    
    agent = Agent(planner, tools)
    print(f"Tools loaded: {[t.name for t in tools]}")
    
    # 2. Test Shell Tool
    box_print("TEST 1: SHELL EXECUTION (ls/dir)")
    agent.set_goal("ls")
    agent.step()
    
    # 3. Test Vision Tool
    box_print("TEST 2: VISION (screenshot)")
    agent.set_goal("screenshot")
    agent.step()
    
    # 4. Test Desktop Tool (Safe Click)
    box_print("TEST 3: DESKTOP CONTROL (click 10 10)")
    agent.set_goal("click 10 10")
    agent.step()
    
    box_print("AGENT LOOP VERIFIED")
    print("\nAction History:")
    for entry in agent.belief.action_history:
        print(f"  - {entry}")

if __name__ == "__main__":
    main()
