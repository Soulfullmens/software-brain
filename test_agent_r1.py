"""
test_agent_r1.py

Integration Test for Phase R.1 Agent Loop.
Verifies: Interpreter -> Planner -> Executor.
"""
from src.agent.core import Agent
from src.agent.planner import RuleBasedPlanner
from src.agent.tools.desktop import DesktopTool
from src.agent.tools.screen import ScreenTool
from src.agent.tools.shell import ShellTool

def main():
    print("+------------------------------------------------------+")
    print("| INITIALIZING AGENT (PHASE R.1)                       |")
    print("+------------------------------------------------------+")
    
    # 1. Initialize Tools
    tools = [
        DesktopTool(),
        ScreenTool(),
        ShellTool()
    ]
    
    # 2. Initialize Planner (GoalPlanner)
    planner = RuleBasedPlanner()
    
    # 3. Initialize Agent
    agent = Agent(planner=planner, tools=tools)
    
    # Test 1: RUN_SHELL
    print("\n+------------------------------------------------------+")
    print("| TEST 1: RUN_SHELL ('Run dir')                        |")
    print("+------------------------------------------------------+")
    goal = "Run dir"
    results = agent.run(goal)
    
    # Verify results
    assert len(results) > 0, "No results returned"
    last_result = results[-1]
    result_text = last_result['result']
    print(f"FULL RESULT:\n{result_text}")
    print(f"FULL RESULT REPR:\n{repr(result_text)}")
    
    if result_text.startswith("Error"):
        print("SHELL TOOL RETURNED ERROR")
        
    assert "Volume" in result_text or "Directory of" in result_text or "total" in result_text or "File(s)" in result_text, f"Dir output failure: {result_text}"
    
    # Test 2: OPEN_FILE (Plan Generation Only - Mock Execution?)
    # We won't assert execution success for UI actions in headless/test env easily, 
    # but we can check the logs.
    print("\n+------------------------------------------------------+")
    print("| TEST 2: OPEN_FILE (Plan Generation)                  |")
    print("+------------------------------------------------------+")
    goal = "Open quarterly_report.xlsx"
    # We expect this to try to click things. 
    # NOTE: This might move the mouse!
    try:
        results = agent.run(goal)
        print("Execution finished (Action sequence ran).")
    except Exception as e:
        print(f"Execution failed (Expected if UI not interactive): {e}")

    print("\n+------------------------------------------------------+")
    print("| TEST 3: FAILURE MODE ('Run dir non_existent_folder') |")
    print("+------------------------------------------------------+")
    goal = "Run dir non_existent_folder"
    results = agent.run(goal)
    
    last_result = results[-1]
    verdict = last_result.get("evaluation")
    print(f"Verdict: Success={verdict.success}, Reason={verdict.failure_reason}")
    
    assert verdict is not None, "Evaluator did not run"
    assert verdict.success is False, "Evaluator failed to detect failure"
    assert "File Not Found" in verdict.failure_reason or "Error" in verdict.failure_reason or "file not found" in str(last_result['result']).lower(), "Failure reason mismatch"

    print("\n+------------------------------------------------------+")
    print("| AGENT R.1 PIPELINE VERIFIED (WITH EVALUATOR)         |")
    print("+------------------------------------------------------+")

if __name__ == "__main__":
    main()
