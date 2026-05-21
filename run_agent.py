"""
run_agent.py

Main entry point for the Claude-Level Software Brain Agent.

Usage:
    python run_agent.py              # Interactive chat mode
    python run_agent.py --goal "..." # Execute a single goal
    python run_agent.py --code "..." # Generate code
    python run_agent.py --think "..."# Deep reasoning
    python run_agent.py --status     # Show agent status
"""
import argparse
import json
import sys
import os

# Ensure src is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.agent.claude_agent import ClaudeAgent, run_interactive


def main():
    parser = argparse.ArgumentParser(
        description="Software Brain — Claude-Level Autonomous Agent"
    )
    parser.add_argument("--goal", type=str, help="Execute a goal with tool use")
    parser.add_argument("--chat", type=str, help="Single chat message")
    parser.add_argument("--think", type=str, help="Deep reasoning on a question")
    parser.add_argument("--code", type=str, help="Generate code from description")
    parser.add_argument("--execute", action="store_true", help="Execute generated code")
    parser.add_argument("--provider", type=str, help="Force specific LLM provider (anthropic/openai/gemini/ollama)")
    parser.add_argument("--research", type=str, help="Deep research analysis (9 protocols)")
    parser.add_argument("--research-quick", type=str, dest="research_quick", help="Quick research (3 protocols)")
    parser.add_argument("--status", action="store_true", help="Show agent status")
    parser.add_argument("--env", type=str, default=".env", help="Path to .env file")

    args = parser.parse_args()

    # If no specific command, run interactive
    if not any([args.goal, args.chat, args.think, args.code, args.status, args.research, args.research_quick]):
        run_interactive(args.env)
        return

    agent = ClaudeAgent.from_env(args.env)

    if args.status:
        print(json.dumps(agent.status(), indent=2))
        return

    if args.chat:
        response = agent.chat(args.chat, provider=args.provider)
        print(response)
        return

    if args.think:
        print("[Thinking...]\n")
        chain = agent.think(args.think)
        print(chain.to_text())
        print(f"\nConfidence: {chain.overall_confidence:.0%}")
        print(f"Strategy: {chain.strategy_used}")
        return

    if args.code:
        result = agent.code(args.code, execute=args.execute)
        print(f"```python\n{result['code']}\n```")
        if "execution" in result:
            ex = result["execution"]
            if ex["stdout"]:
                print(f"\nOutput:\n{ex['stdout']}")
            if ex["stderr"]:
                print(f"\nErrors:\n{ex['stderr']}")
        return

    if args.goal:
        print(f"[Executing: {args.goal}]\n")
        result = agent.run(args.goal, provider=args.provider)
        print(f"\nStatus: {result.status}")
        print(f"Response: {result.final_response}")
        print(f"Steps: {len(result.steps)} | Tool calls: {result.total_tool_calls}")
        return

    research_topic = args.research or args.research_quick
    if research_topic:
        deep = bool(args.research)
        mode_label = "DEEP (9 protocols)" if deep else "QUICK (3 protocols)"
        print(f"[Research Mode: {mode_label}]")
        print(f"[Topic: {research_topic}]\n")
        report = agent.research(
            topic=research_topic,
            deep=deep,
            provider=args.provider,
        )
        print(report.to_text())
        return


if __name__ == "__main__":
    main()
