"""
demo_gemini_agent.py

This script demonstrates the agent using the Gemini LLM brain to take
actual physical control of your laptop browser and perform a task.
"""
import sys
import os
import time

# Ensure src is in the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.agent.autonomous_agent import AutonomousAgent
from src.agent.llm_gemini import GeminiClient

def load_env():
    """Manually parse .env to avoid adding python-dotenv dependency"""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return None
        
    with open(env_path, "r") as f:
        for line in f:
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None

def run_demo():
    print("\n" + "="*60)
    print("GEMINI-POWERED COGNITIVE AGENT : LAPTOP CONTROL DEMO")
    print("="*60 + "\n")
    
    api_key = load_env()
    if not api_key:
        print("[ERROR] GEMINI_API_KEY not found in .env file.")
        return
        
    print(f"[OK] Gemini API Key Loaded: ...{api_key[-4:]}")
    print("[OK] Initializing LLM Brain (gemini-1.5-flash)...")
    
    # 1. Initialize our custom LLM wrapper
    llm = GeminiClient(api_key=api_key)
    
    # 2. Give the brain to the Autonomous Agent
    agent = AutonomousAgent(headless=False, llm_client=llm)
    
    print("\n[SCENARIO]: We are asking the AI to physically open Wikipedia")
    print("and search for Reinforcement Learning to demonstrate desktop control.")
    
    goal = "Open the browser, go to https://www.wikipedia.org, and search for 'Reinforcement Learning'."
    print(f"\n[USER GOAL]: '{goal}'")
    print("\nStarting execution... watch your screen!\n")
    
    # 3. Execute!
    try:
        time.sleep(2)
        result = agent.run(goal)
        print("\n\n" + "="*30)
        print(f"TASK FINISHED: {result['status']}")
        print("="*30)
    except Exception as e:
        print(f"\n[ERROR] Execution Failed: {str(e)}")

if __name__ == "__main__":
    run_demo()
