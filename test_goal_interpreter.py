"""
test_goal_interpreter.py

Unit test for Phase R.1 Goal Interpreter.
Verifies pattern matching and fallback logic.
"""
from src.agent.goal.interpreter import GoalInterpreter
from src.agent.goal.schema import GoalPlan

def box_print(msg):
    print("+" + "-"*60 + "+")
    print(f"| {msg:<58} |")
    print("+" + "-"*60 + "+")

def main():
    interpreter = GoalInterpreter()
    
    # Test 1: Open File (Pattern)
    box_print("TEST 1: OPEN FILE (Pattern)")
    text = "Open the quarterly_report.xlsx file please"
    plan = interpreter.interpret(text)
    print(f"Input: {text}")
    print(f"Intent: {plan.intent}")
    print(f"Entities: {plan.entities}")
    print(f"Confidence: {plan.confidence}")
    assert plan.intent == "OPEN_FILE"
    assert plan.entities["filename"] == "quarterly_report.xlsx"
    
    # Test 2: Screenshot (Pattern)
    box_print("TEST 2: SCREENSHOT (Pattern)")
    text = "Take a screenshot of the dashboard"
    plan = interpreter.interpret(text)
    print(f"Input: {text}")
    print(f"Intent: {plan.intent}")
    print(f"Confidence: {plan.confidence}")
    assert plan.intent == "SCREENSHOT"
    
    # Test 3: Run Command (Pattern)
    box_print("TEST 3: RUN COMMAND (Pattern)")
    text = "Run dir command"
    plan = interpreter.interpret(text)
    print(f"Input: {text}")
    print(f"Intent: {plan.intent}")
    print(f"Entities: {plan.entities}")
    assert plan.intent == "RUN_SHELL"
    
    # Test 4: Ambiguous / LLM Fallback
    box_print("TEST 4: UNKNOWN (Fallback)")
    text = "Analyze the sentiment of the market today"
    plan = interpreter.interpret(text)
    print(f"Input: {text}")
    print(f"Intent: {plan.intent}")
    print(f"Requires Approval: {plan.requires_approval}")
    assert plan.intent == "UNKNOWN_LLM_FALLBACK"
    assert plan.requires_approval is True
    
    box_print("GOAL INTERPRETER VERIFIED")

if __name__ == "__main__":
    main()
