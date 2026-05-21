"""
claude_agent.py

The Unified Claude-Level Agent — Your Software Brain's Apex Intelligence.

This is the top-level agent that integrates ALL systems into a single
Claude-competitive intelligence:

┌─────────────────────────────────────────────────────────────────┐
│                     ClaudeAgent                                  │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────────┐    │
│  │ LLMRouter │  │ Conversation │  │   ReasoningEngine      │    │
│  │ (Multi-   │  │  Manager     │  │ (Chain/Tree of Thought)│    │
│  │ Provider) │  │ (Infinite    │  │ (Self-Reflection)      │    │
│  │           │  │  Memory)     │  │ (Hypothesis Gen)       │    │
│  └──────────┘  └──────────────┘  └────────────────────────┘    │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────────┐    │
│  │ ToolProto│  │ CodeEngine   │  │  ExistingBrain          │    │
│  │ (Agentic │  │ (Generate,   │  │ (Safety, Experience,    │    │
│  │  Loop)   │  │  Analyze,    │  │  Learning, Reflection)  │    │
│  │          │  │  Execute)    │  │                          │    │
│  └──────────┘  └──────────────┘  └────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘

WHAT MAKES THIS CLAUDE-LEVEL:

1. REASONING: Chain-of-thought, tree-of-thought, self-reflection,
   hypothesis testing — not just "ask LLM and hope"

2. TOOL USE: Full agentic loop — LLM decides tools, calls them,
   processes results, iterates until done — exactly like Claude

3. CONVERSATION: Multi-turn with sliding window, summarization,
   persistent storage — remembers everything that matters

4. CODE: Generate, analyze, fix, explain, execute code — like Claude

5. MULTI-PROVIDER: Claude/Gemini/GPT-4o/Ollama with automatic fallback

6. SELF-IMPROVEMENT: Learns from every interaction (experience memory,
   pattern detection, self-critique) — BETTER than Claude

7. SAFETY: Authority system, safety governor, autonomy regulation,
   audit trail — production-grade guardrails

Usage:
    agent = ClaudeAgent.from_env()
    
    # Simple chat
    response = agent.chat("What is quantum computing?")
    
    # Agentic task with tools
    result = agent.run("Search for the latest AI news and summarize it")
    
    # Code generation
    code = agent.code("Write a web scraper for HN front page")
    
    # Multi-turn conversation
    agent.chat("Remember my name is Abdul")
    agent.chat("What's my name?")  # "Your name is Abdul"
    
    # Deep reasoning
    chain = agent.think("Compare RISC-V vs ARM for edge AI deployment")
"""
import json
import os
import time
from typing import Any, Callable, Dict, List, Optional

from .llm_router import LLMRouter, Message, Role
from .reasoning_engine import ReasoningEngine, ReasoningContext, ThoughtChain
from .conversation_manager import ConversationManager
from .tool_protocol import (
    AgentToolLoop, ToolRegistry, AgentLoopResult,
    create_default_registry,
    BROWSER_COMMANDS, EMAIL_COMMANDS, SHELL_COMMANDS, FILE_COMMANDS,
)
from .code_engine import CodeEngine
from .expert_router import ExpertRouter
from .research_engine import ResearchEngine, ResearchReport


# ────────────────────────────────────────────────────────
#  System Prompts
# ────────────────────────────────────────────────────────

CLAUDE_SYSTEM_PROMPT = """You are Software Brain — an advanced autonomous AI agent with persistent memory, learning, and tool access.

CAPABILITIES:
- Multi-turn conversation with full context memory
- Web browsing and information retrieval
- Email management (read and compose)
- Code generation, analysis, debugging, and execution
- File system operations (read, write, list)
- Shell command execution
- Desktop and screen control
- Deep reasoning (chain-of-thought, hypothesis testing)
- Self-improvement through experience learning

PERSONALITY:
- Honest and transparent about uncertainty
- Proactive — suggest actions, don't just wait
- Thorough — complete tasks fully, verify results
- Safe — never take irreversible actions without confirmation
- Learning — remember user preferences and improve over time

RULES:
1. Think before acting. Explain your reasoning.
2. Use tools when needed — don't guess when you can verify.
3. If unsure, say so. Never fabricate information.
4. For dangerous/irreversible actions, always ask for confirmation.
5. Be concise but complete.
6. Remember context from the conversation.
7. When you make mistakes, acknowledge and correct them.
"""


# ────────────────────────────────────────────────────────
#  Claude-Level Agent
# ────────────────────────────────────────────────────────

class ClaudeAgent:
    """
    The unified Claude-level agent.
    
    Integrates:
    - Multi-provider LLM routing (Claude/GPT/Gemini/Ollama)
    - Advanced reasoning (CoT, ToT, self-reflection)
    - Multi-turn conversation with infinite memory
    - Agentic tool use loop (Claude-style)
    - Code generation and execution
    - Self-improvement and learning
    """

    def __init__(self, llm: LLMRouter,
                 system_prompt: str = CLAUDE_SYSTEM_PROMPT,
                 data_dir: Optional[str] = None,
                 max_tool_steps: int = 25,
                 approval_callback: Optional[Callable] = None):
        self.llm = llm
        
        # Priority: explicit param -> env var -> default
        self.data_dir = data_dir or os.getenv("AGENT_STORAGE_PATH", "./agent_data")

        # ── SD Card / External Drive Health Check ──
        self._storage_mode = self._check_storage_health(self.data_dir)
        os.makedirs(self.data_dir, exist_ok=True)

        # Core systems
        self.reasoning = ReasoningEngine(llm)
        self.conversation = ConversationManager(
            llm=llm,
            max_context_tokens=100_000,
            storage_dir=os.path.join(self.data_dir, "conversations"),
        )
        self.code_engine = CodeEngine(llm)

        # Expert persona routing
        self.expert_router = ExpertRouter()

        # Stanford PhD Research Engine
        self.research_engine = ResearchEngine(llm)

        # Tool registry (populated when tools are added)
        self.tool_registry = ToolRegistry()
        self.tool_loop = AgentToolLoop(
            llm=llm,
            tools=self.tool_registry,
            conversation=self.conversation,
            max_steps=max_tool_steps,
            approval_callback=approval_callback,
        )

        # Session management
        self.system_prompt = system_prompt
        self.active_session = self.conversation.new_session(
            system_prompt=system_prompt,
        )

        # Stats
        self._stats = {
            "total_chats": 0,
            "total_tasks": 0,
            "total_code_runs": 0,
            "total_reasoning_chains": 0,
            "expert_activations": 0,
        }

    @classmethod
    def from_env(cls, env_path: str = ".env",
                 data_dir: str = "./agent_data",
                 **kwargs) -> "ClaudeAgent":
        """Create agent from environment configuration."""
        llm = LLMRouter.from_env(env_path)
        agent = cls(llm=llm, data_dir=data_dir, **kwargs)
        return agent

    def register_tools(self, tools: Dict[str, Any]):
        """Register existing Tool instances for agentic use."""
        self.tool_registry = create_default_registry(tools)
        self.tool_loop.tools = self.tool_registry

    def register_custom_tool(self, name: str, description: str,
                             parameters: Dict, handler: Callable,
                             requires_approval: bool = False):
        """Register a custom tool for the agent."""
        self.tool_registry.register(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
            requires_approval=requires_approval,
        )

    # ────────────────────────────────────────────────
    #  Chat — Simple Conversational Interface
    # ────────────────────────────────────────────────

    def chat(self, message: str, provider: Optional[str] = None,
             use_expert: bool = True) -> str:
        """
        Smart chat interface with conversation memory and expert routing.
        Automatically selects the best expert persona for the query.
        """
        self._stats["total_chats"] += 1
        sid = self.active_session.id

        self.conversation.add_user_message(sid, message)
        messages = self.conversation.get_context_messages(sid)

        # Expert routing: augment system prompt if a specialist matches
        base_system = self.conversation.get_system_prompt(sid)
        if use_expert:
            system = self.expert_router.build_system_prompt(
                query=message, base_prompt=base_system,
            )
            if system != base_system:
                self._stats["expert_activations"] += 1
        else:
            system = base_system

        response = self.llm.chat_with_history(
            messages=messages,
            system=system,
            provider=provider,
        )

        self.conversation.add_assistant_message(sid, response.content)
        return response.content

    # ────────────────────────────────────────────────
    #  Run — Agentic Task Execution with Tools
    # ────────────────────────────────────────────────

    def run(self, goal: str, provider: Optional[str] = None) -> AgentLoopResult:
        """
        Execute a goal using the full agentic tool use loop.
        The agent will autonomously call tools until the task is done.
        """
        self._stats["total_tasks"] += 1
        return self.tool_loop.run(
            user_message=goal,
            system=self.system_prompt,
            session_id=self.active_session.id,
            provider=provider,
        )

    # ────────────────────────────────────────────────
    #  Research — Stanford PhD Protocol Pipeline
    # ────────────────────────────────────────────────

    def research(self, topic: str, sources: Optional[List[str]] = None,
                 deep: bool = True, provider: Optional[str] = None) -> ResearchReport:
        """
        Run Stanford PhD-level research analysis on a topic.

        Args:
            topic: The research topic or question.
            sources: Optional list of paper abstracts / source texts.
            deep: If True, runs all 9 protocols. If False, runs quick (3 protocols).
            provider: Force specific LLM provider.

        Returns:
            ResearchReport with structured protocol outputs.
        """
        if deep:
            return self.research_engine.deep_research(
                topic=topic, sources=sources, provider=provider
            )
        else:
            return self.research_engine.quick_research(
                topic=topic, sources=sources, provider=provider
            )

    # ────────────────────────────────────────────────
    #  Think — Deep Reasoning
    # ────────────────────────────────────────────────

    def think(self, question: str, context: str = "",
              max_steps: int = 15) -> ThoughtChain:
        """
        Deep reasoning with chain-of-thought.
        For complex questions that need step-by-step analysis.
        """
        self._stats["total_reasoning_chains"] += 1
        ctx = ReasoningContext(
            question=question,
            context=context,
            conversation_history=self.conversation.get_context_messages(
                self.active_session.id
            ),
            available_tools=[t.definition.name for t in self.tool_registry.tools.values()],
            max_thinking_steps=max_steps,
        )
        chain = self.reasoning.think(ctx)

        # Save the reasoning to conversation
        self.conversation.add_user_message(self.active_session.id, question)
        self.conversation.add_assistant_message(
            self.active_session.id,
            chain.final_answer or chain.to_text(),
        )

        return chain

    # ────────────────────────────────────────────────
    #  Code — Code Generation & Execution
    # ────────────────────────────────────────────────

    def code(self, description: str, language: str = "python",
             execute: bool = False) -> Dict[str, Any]:
        """
        Generate code from natural language description.
        Optionally execute it immediately.
        """
        self._stats["total_code_runs"] += 1
        generated = self.code_engine.generate(description, language)
        result = {"code": generated, "language": language}

        if execute:
            execution = self.code_engine.execute(generated, language)
            result["execution"] = {
                "stdout": execution.stdout,
                "stderr": execution.stderr,
                "exit_code": execution.exit_code,
                "timed_out": execution.timed_out,
            }

        return result

    def analyze_code(self, code: str, language: str = "python") -> Dict:
        """Analyze code for bugs, security issues, and improvements."""
        analysis = self.code_engine.analyze(code, language)
        return {
            "summary": analysis.summary,
            "issues": analysis.issues,
            "suggestions": analysis.suggestions,
            "complexity": analysis.complexity,
            "security_concerns": analysis.security_concerns,
        }

    def fix_code(self, code: str, error: str,
                 language: str = "python") -> Dict[str, str]:
        """Fix buggy code given an error message."""
        return self.code_engine.fix_code(code, error, language)

    def explain_code(self, code: str, language: str = "python") -> str:
        """Explain what code does in plain English."""
        return self.code_engine.explain(code, language)

    # ────────────────────────────────────────────────
    #  Session Management
    # ────────────────────────────────────────────────

    def new_conversation(self, system_prompt: Optional[str] = None) -> str:
        """Start a new conversation session."""
        self.active_session = self.conversation.new_session(
            system_prompt=system_prompt or self.system_prompt,
        )
        return self.active_session.id

    def save_conversation(self):
        """Persist current conversation to disk."""
        self.conversation.save_session(self.active_session.id)

    def load_conversation(self, session_id: str) -> bool:
        """Load a previous conversation."""
        session = self.conversation.load_session(session_id)
        if session:
            self.active_session = session
            return True
        return False

    # ────────────────────────────────────────────────
    #  Status & Stats
    # ────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """Get agent status and statistics."""
        conv_stats = self.conversation.stats(self.active_session.id)
        llm_stats = self.llm.usage_stats()
        return {
            "agent": "ClaudeAgent (Software Brain)",
            "version": "2.1.0",
            "session_id": self.active_session.id,
            "storage_mode": self._storage_mode,
            "data_dir": self.data_dir,
            "conversation": conv_stats,
            "llm": llm_stats,
            "tools_registered": len(self.tool_registry.tools),
            "experts_loaded": len(self.expert_router.available_experts),
            "stats": self._stats,
        }

    def __repr__(self):
        tools = len(self.tool_registry.tools)
        providers = len(self.llm.providers)
        experts = len(self.expert_router.available_experts)
        return f"<ClaudeAgent tools={tools} providers={providers} experts={experts} storage={self._storage_mode}>"

    # ────────────────────────────────────────────────
    #  Storage Health Check
    # ────────────────────────────────────────────────

    @staticmethod
    def _check_storage_health(data_dir: str) -> str:
        """
        Check if the configured storage path is healthy.
        Detects whether data_dir is on an external/SD card drive
        and whether it's currently accessible.

        Returns:
            'external' — data on SD card / external drive, healthy
            'local'    — data on local disk (default)
            'fallback' — external drive not found, using local fallback
        """
        import sys

        # Detect if path points to a non-default location (likely external)
        is_external = False
        abs_path = os.path.abspath(data_dir)

        if sys.platform == 'win32':
            # External drives: D:\, E:\, F:\, etc. (not C:\)
            drive_letter = os.path.splitdrive(abs_path)[0].upper()
            if drive_letter and drive_letter[0] not in ('C', ''):
                is_external = True
        else:
            # Linux/Mac: /mnt/, /media/, /Volumes/
            external_prefixes = ('/mnt/', '/media/', '/Volumes/')
            if any(abs_path.startswith(p) for p in external_prefixes):
                is_external = True

        if not is_external:
            return 'local'

        # External path detected — check if the drive is actually mounted
        if sys.platform == 'win32':
            drive_root = os.path.splitdrive(abs_path)[0] + '\\'
            if os.path.exists(drive_root):
                return 'external'
            else:
                # Drive not found — fall back to local
                import warnings
                warnings.warn(
                    f"External drive {drive_root} not found. "
                    f"Falling back to local storage ./agent_data"
                )
                return 'fallback'
        else:
            parent = os.path.dirname(abs_path)
            if os.path.ismount(parent) or os.path.exists(parent):
                return 'external'
            else:
                import warnings
                warnings.warn(
                    f"External mount {parent} not found. "
                    f"Falling back to local storage ./agent_data"
                )
                return 'fallback'


# ────────────────────────────────────────────────────────
#  Interactive REPL
# ────────────────────────────────────────────────────────

def run_interactive(env_path: str = ".env"):
    """Run the agent in interactive REPL mode."""
    print("=" * 60)
    print("  SOFTWARE BRAIN — Claude-Level Agent")
    print("  Type 'quit' to exit, 'status' for stats")
    print("  Type '/think <question>' for deep reasoning")
    print("  Type '/code <description>' for code generation")
    print("  Type '/run <task>' for agentic tool execution")
    print("  Type '/new' for new conversation")
    print("=" * 60)

    agent = ClaudeAgent.from_env(env_path)
    print(f"\n[OK] Agent initialized with {len(agent.llm.providers)} LLM providers")
    print(f"[OK] Tools: {len(agent.tool_registry.tools)} registered")
    print(f"[OK] Session: {agent.active_session.id}\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() == "quit":
            agent.save_conversation()
            print("Conversation saved. Goodbye!")
            break

        if user_input.lower() == "status":
            print(json.dumps(agent.status(), indent=2))
            continue

        if user_input.lower() == "/new":
            agent.new_conversation()
            print("[OK] New conversation started.")
            continue

        if user_input.startswith("/think "):
            question = user_input[7:]
            print("\n[Thinking...]\n")
            chain = agent.think(question)
            print(chain.to_text())
            print(f"\n[Confidence: {chain.overall_confidence:.0%}]")
            print(f"[Strategy: {chain.strategy_used}]")
            print(f"[Tokens: {chain.token_count}]\n")
            continue

        if user_input.startswith("/code "):
            description = user_input[6:]
            print("\n[Generating code...]\n")
            result = agent.code(description, execute=True)
            print(f"```python\n{result['code']}\n```")
            if "execution" in result:
                ex = result["execution"]
                if ex["stdout"]:
                    print(f"\nOutput:\n{ex['stdout']}")
                if ex["stderr"]:
                    print(f"\nErrors:\n{ex['stderr']}")
            continue

        if user_input.startswith("/run "):
            goal = user_input[5:]
            print(f"\n[Executing: {goal}]\n")
            result = agent.run(goal)
            print(f"\nResult ({result.status}):")
            print(result.final_response)
            print(f"\n[Steps: {len(result.steps)} | Tools: {result.total_tool_calls}]")
            continue

        # Default: chat
        response = agent.chat(user_input)
        print(f"\nAgent: {response}\n")


if __name__ == "__main__":
    run_interactive()
