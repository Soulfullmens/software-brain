"""
test_revenue_workflow.py

Integration Test for Phase S (Full Revenue Workflow).
Verifies: Email -> Excel -> Report -> Email
"""
import os
import shutil
from src.agent.core import Agent
from src.agent.planner import RuleBasedPlanner
from src.agent.tools.desktop import DesktopTool
from src.agent.tools.screen import ScreenTool
from src.agent.tools.shell import ShellTool
from src.agent.tools.email import EmailTool
from src.agent.tools.excel import ExcelTool

def cleanup():
    # Remove test artifacts
    paths = [
        "c:/Users/abdul rahaman/Downloads/sales_data.xlsx",
        "c:/Users/abdul rahaman/data/master_sales.xlsx",
        "c:/Users/abdul rahaman/reports/daily_summary.txt",
        "./downloads", 
        "./data", 
        "./reports"
    ]
    for p in paths:
        if os.path.exists(p):
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
    print("[Setup] Cleaned up artifacts.")

def main():
    print("+------------------------------------------------------+")
    print("| TESTING REVENUE WORKFLOW (END-TO-END)                |")
    print("+------------------------------------------------------+")
    
    cleanup()
    
    # 1. Initialize Tools
    tools = [
        DesktopTool(),
        ScreenTool(),
        ShellTool(),
        EmailTool(backend_type="mock"),
        ExcelTool()
    ]
    
    # 2. Planner
    planner = RuleBasedPlanner()
    
    # 3. Agent
    agent = Agent(planner=planner, tools=tools)
    
    # --- STEP 1: FETCH EMAIL ---
    print("\n[Step 1] User: 'Check email for Sales Report'")
    results = agent.run("Check email for Sales Report")
    print(f"Step 1 Results: {results}")
    
    if os.path.exists("./downloads"):
        print(f"Downloads content: {os.listdir('./downloads')}")
    else:
        print("Downloads dir does not exist.")
    
    # Verify file downloaded
    assert os.path.exists("c:/Users/abdul rahaman/Downloads/sales_data.xlsx") or \
           os.path.exists("./downloads/sales_data.xlsx"), "Download failed"

    # --- STEP 2: UPDATE MASTER ---
    print("\n[Step 2] User: 'Update master spreadsheet'")
    agent.run("Update master spreadsheet")
    
    # Verify master created
    assert os.path.exists("c:/Users/abdul rahaman/data/master_sales.xlsx") or \
           os.path.exists("./data/master_sales.xlsx"), "Master update failed"
           
    # --- STEP 3: GENERATE REPORT ---
    print("\n[Step 3] User: 'Generate summary report'")
    agent.run("Generate summary report")
    
    # Verify report created
    report_path = "c:/Users/abdul rahaman/reports/daily_summary.txt"
    if not os.path.exists(report_path):
        report_path = "./reports/daily_summary.txt"
        
    assert os.path.exists(report_path), "Report generation failed"
    
    with open(report_path, "r") as f:
        content = f.read()
        print(f"\nReport Content:\n{content}")
        assert "Total Revenue" in content
        
    # --- STEP 4: SEND EMAIL ---
    print("\n[Step 4] User: 'Send email to manager'")
    agent.run("Send email to manager")
    
    print("\n+------------------------------------------------------+")
    print("| REVENUE WORKFLOW: SUCCESS                            |")
    print("+------------------------------------------------------+")

if __name__ == "__main__":
    main()
