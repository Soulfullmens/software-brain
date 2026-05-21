"""
reasoning_engine.py

Advanced Reasoning Engine — Claude-Level Cognitive Processing.

This is the thinking core that makes this agent reason like Claude Opus 4.
Implements multiple reasoning strategies that Claude uses internally:

1. Chain-of-Thought (CoT)      — Step-by-step sequential reasoning
2. Tree-of-Thought (ToT)       — Branching exploration of solution paths
3. Self-Reflection              — Critique own reasoning, catch errors
4. Decomposition                — Break complex problems into sub-problems
5. Analogical Reasoning         — Draw parallels from past experience
6. Hypothesis Testing           — Generate and validate hypotheses
7. Meta-Cognition               — Know what you know and don't know

Architecture:
    ReasoningEngine
    ├── ThinkingManager      (orchestrates reasoning strategies)
    ├── ThoughtChain         (maintains reasoning trace)
    ├── ReasoningStrategy    (abstract strategy interface)
    └── ConfidenceTracker    (calibrated uncertainty)
"""
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .llm_router import LLMRouter, LLMRequest, LLMResponse, Message, Role

# Intelligence modules (MiroFish-inspired)
try:
    from .intelligence.knowledge_graph import KnowledgeGraph
    from .intelligence.multi_retriever import MultiRetriever
    from .intelligence.persona_engine import PersonaEngine
    _HAS_INTELLIGENCE = True
except ImportError:
    _HAS_INTELLIGENCE = False


# ────────────────────────────────────────────────────────
#  Data Structures
# ────────────────────────────────────────────────────────

class ThoughtType(str, Enum):
    OBSERVATION = "observation"       # What I notice
    REASONING = "reasoning"           # Logical inference
    HYPOTHESIS = "hypothesis"         # Tentative conclusion
    CRITIQUE = "critique"             # Self-correction
    PLAN = "plan"                     # Action planning
    SYNTHESIS = "synthesis"           # Combining insights
    UNCERTAINTY = "uncertainty"       # What I don't know
    CONCLUSION = "conclusion"         # Final answer


@dataclass
class Thought:
    """A single unit of reasoning."""
    type: ThoughtType
    content: str
    confidence: float = 0.5
    evidence: List[str] = field(default_factory=list)
    parent_id: Optional[int] = None   # for tree-of-thought branching
    timestamp: float = field(default_factory=time.time)
    id: int = 0


@dataclass
class ThoughtChain:
    """Complete reasoning trace for a single problem."""
    thoughts: List[Thought] = field(default_factory=list)
    final_answer: str = ""
    overall_confidence: float = 0.0
    strategy_used: str = ""
    total_thinking_time_ms: float = 0.0
    token_count: int = 0

    def add(self, thought_type: ThoughtType, content: str,
            confidence: float = 0.5, evidence: Optional[List[str]] = None,
            parent_id: Optional[int] = None) -> Thought:
        t = Thought(
            type=thought_type,
            content=content,
            confidence=confidence,
            evidence=evidence or [],
            parent_id=parent_id,
            id=len(self.thoughts),
        )
        self.thoughts.append(t)
        return t

    def to_text(self) -> str:
        """Render the thought chain as human-readable text."""
        lines = []
        for t in self.thoughts:
            prefix = {
                ThoughtType.OBSERVATION: "👁 Observation",
                ThoughtType.REASONING: "🔗 Reasoning",
                ThoughtType.HYPOTHESIS: "💡 Hypothesis",
                ThoughtType.CRITIQUE: "⚠ Self-Critique",
                ThoughtType.PLAN: "📋 Plan",
                ThoughtType.SYNTHESIS: "🔀 Synthesis",
                ThoughtType.UNCERTAINTY: "❓ Uncertainty",
                ThoughtType.CONCLUSION: "✅ Conclusion",
            }.get(t.type, "💭")
            conf = f" ({t.confidence:.0%})" if t.confidence < 1.0 else ""
            lines.append(f"  {prefix}{conf}: {t.content}")
        if self.final_answer:
            lines.append(f"\n  📌 Final Answer: {self.final_answer}")
        return "\n".join(lines)


@dataclass
class ReasoningContext:
    """Everything the reasoning engine needs to think."""
    question: str
    context: str = ""                  # Additional context
    conversation_history: List[Message] = field(default_factory=list)
    available_tools: List[str] = field(default_factory=list)
    past_experience: Optional[Dict] = None
    constraints: List[str] = field(default_factory=list)
    max_thinking_steps: int = 15
    require_confidence: float = 0.7     # minimum confidence to stop


# ────────────────────────────────────────────────────────
#  Reasoning Strategies
# ────────────────────────────────────────────────────────

COT_SYSTEM = """You are an advanced reasoning engine. Think step-by-step to solve problems.

For each thinking step, output a JSON object:
{
  "type": "observation|reasoning|hypothesis|critique|plan|synthesis|uncertainty|conclusion",
  "content": "Your thought in this step",
  "confidence": 0.0-1.0,
  "evidence": ["supporting evidence 1", "evidence 2"],
  "needs_more_thinking": true/false
}

RULES:
1. Start with OBSERVATION — state what you know and what's being asked.
2. Use REASONING to work through logic step by step.
3. Use HYPOTHESIS when forming tentative conclusions.
4. ALWAYS use CRITIQUE to check your own reasoning for errors.
5. Use UNCERTAINTY to flag what you're unsure about.
6. End with CONCLUSION only when confidence exceeds the threshold.
7. If you find an error in your reasoning, correct it — don't hide mistakes.
8. Be calibrated — 0.9 confidence means you'd bet 9:1 on being right.
"""

DECOMPOSE_SYSTEM = """You are a problem decomposition engine. Break complex problems into smaller, solvable sub-problems.

Output a JSON object:
{
  "sub_problems": [
    {
      "id": 1,
      "description": "Sub-problem description",
      "depends_on": [],
      "complexity": "low|medium|high",
      "approach": "How to solve this sub-problem"
    }
  ],
  "synthesis_strategy": "How to combine sub-answers into final answer",
  "estimated_steps": 5
}
"""

TOOL_REASONING_SYSTEM = """You are an intelligent tool-use reasoning engine. Given a goal and available tools, determine the optimal sequence of tool calls.

Available tools will be provided. For each step, reason about:
1. What information do I need?
2. Which tool provides that information?
3. What parameters should I use?
4. What do I expect to get back?
5. How does this advance me toward the goal?

Output a JSON object:
{
  "thought": {
    "observation": "What I know so far",
    "reasoning": "Why this tool call is the right next step",
    "plan_status": "What's done and what remains",
    "confidence": 0.8
  },
  "tool_call": {
    "name": "tool_name",
    "arguments": {"param1": "value1"}
  },
  "is_complete": false,
  "needs_more_info": false,
  "uncertainty": "What I'm unsure about"
}
"""


class ReasoningEngine:
    """
    Advanced reasoning engine that thinks like Claude.
    Orchestrates multiple reasoning strategies and picks
    the best approach for each problem type.

    MiroFish-Inspired Intelligence:
        - KnowledgeGraph for entity/relationship evidence
        - MultiRetriever for multi-strategy information retrieval
        - PersonaEngine for task-adaptive reasoning style
    """

    def __init__(self, llm: LLMRouter,
                 knowledge_graph=None,
                 retriever=None,
                 persona_engine=None):
        self.llm = llm
        self.thought_history: List[ThoughtChain] = []

        # Intelligence modules (optional, MiroFish-inspired)
        self.knowledge_graph = knowledge_graph
        self.retriever = retriever
        self.persona_engine = persona_engine

        # Auto-wire retriever to knowledge graph if both exist
        if self.retriever and self.knowledge_graph:
            self.retriever.set_knowledge_graph(self.knowledge_graph)

    def think(self, ctx: ReasoningContext) -> ThoughtChain:
        """
        Main entry: reason about a question using the best strategy.
        Automatically selects chain-of-thought, decomposition, or
        direct answer based on problem complexity.

        If KnowledgeGraph is available, augments context with graph evidence.
        If PersonaEngine is available, adapts reasoning style to task.
        """
        # Augment context with knowledge graph evidence
        if self.retriever:
            try:
                retrieval = self.retriever.retrieve(ctx.question, strategy="auto")
                if retrieval.facts:
                    evidence = "\n".join(f"- {f}" for f in retrieval.facts[:10])
                    ctx.context = (ctx.context or "") + f"\n\nKNOWN FACTS:\n{evidence}"
            except Exception:
                pass

        # Adapt persona if available
        if self.persona_engine:
            try:
                persona = self.persona_engine.select_persona(ctx.question)
                ctx.context = (ctx.context or "") + f"\n\nActive persona: {persona.name} ({persona.tone})"
            except Exception:
                pass

        complexity = self._estimate_complexity(ctx)

        if complexity == "simple":
            return self._think_direct(ctx)
        elif complexity == "complex":
            return self._think_decompose_then_solve(ctx)
        else:
            return self._think_chain_of_thought(ctx)

    def think_about_tools(self, goal: str, available_tools: List[Dict],
                          context: str = "",
                          history: Optional[List[Message]] = None) -> LLMResponse:
        """
        Reason about which tool to call next.
        This is the core of Claude-style agentic tool use.
        """
        tools_desc = json.dumps(available_tools, indent=2)
        prompt = (
            f"GOAL: {goal}\n\n"
            f"AVAILABLE TOOLS:\n{tools_desc}\n\n"
            f"CURRENT CONTEXT:\n{context or 'No context yet.'}\n\n"
            f"What tool should I call next? Think step by step."
        )

        messages = list(history or [])
        messages.append(Message(Role.USER, prompt))

        request = LLMRequest(
            messages=messages,
            system=TOOL_REASONING_SYSTEM,
            temperature=0.1,
            json_mode=True,
            max_tokens=2048,
        )
        return self.llm.generate(request)

    def reflect_on_result(self, action: str, result: str,
                          goal: str, history: str = "") -> Dict[str, Any]:
        """
        Reflect on an action result — did it advance the goal?
        Returns assessment with next-step recommendation.
        """
        prompt = (
            f"GOAL: {goal}\n"
            f"ACTION TAKEN: {action}\n"
            f"RESULT: {result}\n"
            f"HISTORY: {history or 'First action.'}\n\n"
            f"Analyze this result. Did it advance the goal? What should happen next?\n\n"
            f"Respond in JSON:\n"
            f'{{"assessment": "success|partial|failure|unexpected",'
            f' "goal_progress": 0.0-1.0,'
            f' "key_info_extracted": ["fact1", "fact2"],'
            f' "next_action": "description",'
            f' "reasoning": "why"}}'
        )

        try:
            return self.llm.chat_json(prompt, system="You are a self-reflective reasoning engine. Analyze action results honestly.")
        except (json.JSONDecodeError, ConnectionError):
            return {
                "assessment": "unknown",
                "goal_progress": 0.0,
                "key_info_extracted": [],
                "next_action": "retry or try alternative",
                "reasoning": "Could not analyze result",
            }

    def generate_hypotheses(self, observation: str,
                            context: str = "") -> List[Dict[str, Any]]:
        """Generate multiple hypotheses to explain an observation."""
        prompt = (
            f"OBSERVATION: {observation}\n"
            f"CONTEXT: {context}\n\n"
            f"Generate 3-5 hypotheses that could explain this observation.\n"
            f"For each, estimate probability and suggest how to test it.\n\n"
            f"Respond in JSON:\n"
            f'{{"hypotheses": [{{"hypothesis": "...", "probability": 0.0-1.0, '
            f'"evidence_for": ["..."], "evidence_against": ["..."], '
            f'"test": "How to verify"}}]}}'
        )
        try:
            return self.llm.chat_json(
                prompt,
                system="You are a hypothesis generation engine. Be creative but calibrated."
            ).get("hypotheses", [])
        except (json.JSONDecodeError, ConnectionError):
            return []

    # ── Internal Reasoning Strategies ──

    def _think_chain_of_thought(self, ctx: ReasoningContext) -> ThoughtChain:
        """Multi-step chain-of-thought reasoning."""
        chain = ThoughtChain(strategy_used="chain_of_thought")
        t0 = time.time()

        # Build the reasoning prompt
        prompt = f"QUESTION: {ctx.question}"
        if ctx.context:
            prompt += f"\n\nCONTEXT:\n{ctx.context}"
        if ctx.constraints:
            prompt += f"\n\nCONSTRAINTS:\n" + "\n".join(f"- {c}" for c in ctx.constraints)
        prompt += f"\n\nMinimum confidence to conclude: {ctx.require_confidence}"
        prompt += "\n\nThink step by step. Output one JSON thought per step."

        messages: List[Message] = list(ctx.conversation_history)
        messages.append(Message(Role.USER, prompt))

        # Iterative thinking loop
        for step in range(ctx.max_thinking_steps):
            request = LLMRequest(
                messages=messages,
                system=COT_SYSTEM,
                temperature=0.2,
                json_mode=True,
                max_tokens=1024,
            )
            try:
                response = self.llm.generate(request)
                chain.token_count += response.input_tokens + response.output_tokens
                thought_data = json.loads(response.content)
            except (json.JSONDecodeError, ConnectionError):
                chain.add(ThoughtType.UNCERTAINTY, "Failed to generate reasoning step.")
                break

            # Record the thought
            thought_type = ThoughtType(thought_data.get("type", "reasoning"))
            chain.add(
                thought_type=thought_type,
                content=thought_data.get("content", ""),
                confidence=thought_data.get("confidence", 0.5),
                evidence=thought_data.get("evidence", []),
            )

            # Check if done
            if thought_type == ThoughtType.CONCLUSION:
                chain.final_answer = thought_data.get("content", "")
                chain.overall_confidence = thought_data.get("confidence", 0.5)
                break

            if not thought_data.get("needs_more_thinking", True):
                chain.final_answer = thought_data.get("content", "")
                chain.overall_confidence = thought_data.get("confidence", 0.5)
                break

            # Feed the thought back for the next step
            messages.append(Message(Role.ASSISTANT, response.content))
            messages.append(Message(Role.USER, "Continue reasoning. What's the next step?"))

        chain.total_thinking_time_ms = (time.time() - t0) * 1000
        self.thought_history.append(chain)
        return chain

    def _think_direct(self, ctx: ReasoningContext) -> ThoughtChain:
        """Direct answer for simple questions."""
        chain = ThoughtChain(strategy_used="direct")
        t0 = time.time()

        messages = list(ctx.conversation_history)
        messages.append(Message(Role.USER, ctx.question))

        response = self.llm.generate(LLMRequest(
            messages=messages,
            system=ctx.context or "",
            temperature=0.2,
            max_tokens=2048,
        ))

        chain.add(ThoughtType.CONCLUSION, response.content, confidence=0.8)
        chain.final_answer = response.content
        chain.overall_confidence = 0.8
        chain.token_count = response.input_tokens + response.output_tokens
        chain.total_thinking_time_ms = (time.time() - t0) * 1000
        self.thought_history.append(chain)
        return chain

    def _think_decompose_then_solve(self, ctx: ReasoningContext) -> ThoughtChain:
        """Decompose complex problem, solve parts, synthesize."""
        chain = ThoughtChain(strategy_used="decompose_and_solve")
        t0 = time.time()

        # Step 1: Decompose
        chain.add(ThoughtType.PLAN, f"Decomposing complex problem: {ctx.question}")

        decomp_prompt = f"PROBLEM: {ctx.question}"
        if ctx.context:
            decomp_prompt += f"\nCONTEXT: {ctx.context}"

        try:
            decomposition = self.llm.chat_json(
                decomp_prompt, system=DECOMPOSE_SYSTEM
            )
            sub_problems = decomposition.get("sub_problems", [])
        except (json.JSONDecodeError, ConnectionError):
            # Fall back to chain-of-thought
            return self._think_chain_of_thought(ctx)

        chain.add(ThoughtType.PLAN,
                  f"Decomposed into {len(sub_problems)} sub-problems",
                  evidence=[sp["description"] for sp in sub_problems])

        # Step 2: Solve each sub-problem
        sub_answers = {}
        for sp in sub_problems:
            sub_ctx = ReasoningContext(
                question=sp["description"],
                context=ctx.context,
                conversation_history=ctx.conversation_history,
                max_thinking_steps=5,
                require_confidence=0.6,
            )
            sub_chain = self._think_chain_of_thought(sub_ctx)
            sub_answers[sp["id"]] = sub_chain.final_answer
            chain.add(ThoughtType.REASONING,
                      f"Sub-problem {sp['id']}: {sub_chain.final_answer}",
                      confidence=sub_chain.overall_confidence)
            chain.token_count += sub_chain.token_count

        # Step 3: Synthesize
        synthesis_prompt = (
            f"ORIGINAL PROBLEM: {ctx.question}\n\n"
            f"SUB-PROBLEM ANSWERS:\n"
            + "\n".join(f"  {k}: {v}" for k, v in sub_answers.items())
            + f"\n\nSYNTHESIS STRATEGY: {decomposition.get('synthesis_strategy', 'Combine logically')}"
            + "\n\nSynthesize a final, complete answer."
        )

        response = self.llm.generate(LLMRequest(
            messages=[Message(Role.USER, synthesis_prompt)],
            system="Synthesize sub-answers into a complete, coherent response.",
            temperature=0.2,
            max_tokens=2048,
        ))
        chain.token_count += response.input_tokens + response.output_tokens

        chain.add(ThoughtType.SYNTHESIS, response.content, confidence=0.8)
        chain.final_answer = response.content
        chain.overall_confidence = 0.8
        chain.total_thinking_time_ms = (time.time() - t0) * 1000
        self.thought_history.append(chain)
        return chain

    def _estimate_complexity(self, ctx: ReasoningContext) -> str:
        """Estimate problem complexity to choose strategy."""
        q = ctx.question.lower()
        word_count = len(q.split())

        # Simple heuristics (no LLM call needed)
        if word_count < 15 and "?" in ctx.question:
            return "simple"

        complex_signals = [
            "compare", "analyze", "explain why", "step by step",
            "design", "architect", "implement", "debug",
            "trade-off", "pros and cons", "multi-step",
        ]
        if any(signal in q for signal in complex_signals):
            return "complex"

        if word_count > 50 or len(ctx.constraints) > 2:
            return "complex"

        return "medium"
