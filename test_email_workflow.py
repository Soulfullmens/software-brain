"""
test_email_workflow.py

Integration Test for Phase S (Email Workflow).
Verifies: Interpreter -> Planner -> Executor -> Evaluator
for FETCH_EMAIL and SEND_EMAIL intents.
"""
from src.agent.core import Agent
from src.agent.planner import RuleBasedPlanner
from src.agent.tools.desktop import DesktopTool
from src.agent.tools.screen import ScreenTool
from src.agent.tools.shell import ShellTool
from src.agent.tools.email import EmailTool

def main():
    print("+------------------------------------------------------+")
    print("| TESTING EMAIL AGENT WORKFLOW [MOCK]                  |")
    print("+------------------------------------------------------+")
    
    # 1. Initialize Tools
    tools = [
        DesktopTool(),
        ScreenTool(),
        ShellTool(),
        EmailTool(backend_type="mock")
    ]
    
    # 2. Planner
    planner = RuleBasedPlanner()
    
    # 3. Agent
    agent = Agent(planner=planner, tools=tools)
    
    # --- TEST 1: FETCH EMAIL ---
    print("\n[Scenario 1] User: 'Check email for Sales Report'")
    goal1 = "Check email for Sales Report"
    results1 = agent.run(goal1)
    
    last1 = results1[-1]
    verdict1 = last1["evaluation"]
    print(f"Goal 1 Verdict: Success={verdict1.success}, Reason={verdict1.failure_reason}")
    print(f"Goal 1 Execution Result: {last1['result']}")
    
    assert verdict1.success is True, "Fetch email failed"
    assert "sales_data.xlsx" in str(last1["result"]), "Attachment not found"

    # --- TEST 2: SEND EMAIL ---
    print("\n[Scenario 2] User: 'Send email to manager'")
    goal2 = "Send email to manager"
    results2 = agent.run(goal2)
    
    last2 = results2[-1]
    verdict2 = last2["evaluation"]
    print(f"Goal 2 Verdict: Success={verdict2.success}, Reason={verdict2.failure_reason}")
    print(f"Goal 2 Execution Result: {last2['result']}")
    
    assert verdict2.success is True, "Send email failed"
    assert "sent" in str(last2["result"]), "Send status mismatch"

    print("\n+------------------------------------------------------+")
    print("| EMAIL REVENUE WORKFLOW VERIFIED                      |")
    print("+------------------------------------------------------+")

if __name__ == "__main__":
    main()
