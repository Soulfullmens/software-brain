"""
run_pipeline.py

Production Entry Point for the Autonomous Revenue Agent.
Phase S Step 3.

Usage:
    python run_pipeline.py [--loop]

"""
import sys
import time
import argparse
from src.config import config
from src.agent.core import Agent
from src.agent.planner import RuleBasedPlanner

def main():
    parser = argparse.ArgumentParser(description="Run the Autonomous Revenue Agent")
    parser.add_argument("--loop", action="store_true", help="Run in a continuous loop")
    args = parser.parse_args()

    print(f" [System] Starting Agent (Env: {config.env})")
    print(f" [System] Logging to: {config.paths.get('logs')}")

    # Initialize Agent
    planner = RuleBasedPlanner()
    agent = Agent(planner)

    # Define Workflow Triggers
    # In a real system, this would listen to an Event Bus or Cron.
    # Here we mock the trigger sequence.

    triggers = [
        "Check email for Sales Report",
        # Note: The agent is planner-driven. 
        # "Check email" will trigger fetch -> download.
        # But we also need to trigger "Update Excel" and "Generate Report" 
        # if the first step yields results. 
        # OR we can give a high-level goal: "Process daily sales reports"
        # and the Planner breaks it down?
        # Current Interpreter handles atomic goals.
        # So we chain them or use a "Macro Goal"?
        # User defined: "Process sales report and send summary"
        # Let's try the complex goal if Interpreter supports it?
        # Currently Interpreter is single-intent.
        # So we will chain them in the pipeline script for now (Workflow Engine layer).
    ]

    # Workflow Definition
    workflow_steps = [
        "Check email for Sales Report",
        "Update master spreadsheet with sales_data.xlsx",
        "Generate daily summary report from master data",
        "Send email to manager with report"
    ]

    if args.loop:
        print(" [System] Entering Event Loop (Ctrl+C to stop)")
        try:
            while True:
                run_workflow(agent, workflow_steps)
                sleep_time = config.email.get("poll_interval", 60)
                print(f" [System] Sleeping for {sleep_time}s...")
                time.sleep(sleep_time)
        except KeyboardInterrupt:
            print("\n [System] Stopping...")
    else:
        run_workflow(agent, workflow_steps)

def run_workflow(agent: Agent, steps: list):
    print("\n=== Starting Workflow Cycle ===")
    
    # 1. Fetch
    # We ideally only proceed if Fetch found something.
    # But for v0, we run the sequence.
    # Robustness: Evaluator checks if download happened.
    
    for step in steps:
        print(f"\n>> Trigger: {step}")
        results = agent.run(step)
        
        # Simple Flow Control based on results
        # If fetch failed or found nothing, break?
        # Logic: If step is FETCH and result is empty -> break
        # This requires inspecting 'results' content.
        # For now, we run all. The Tools/Evaluators handle "File not found" errors gracefully.
        
    print("\n=== Workflow Cycle Complete ===")

if __name__ == "__main__":
    main()
