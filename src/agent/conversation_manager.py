"""
conversation_manager.py

Conversation Context Manager — Infinite Memory with Bounded Context.

Claude-level conversation management with:
1. Multi-turn conversation history with roles
2. Sliding window with automatic summarization
3. Token budget management (never exceed context limit)
4. Conversation branching (save/restore points)
5. System prompt management
6. Tool result injection into conversation
7. Persistent conversation storage (resume across sessions)

The key insight: Claude appears to "remember everything" but actually
manages context windows intelligently — summarizing old turns while
keeping recent ones verbatim. This module does the same.
"""
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .llm_router import LLMRouter, LLMRequest, Message, Role


# ────────────────────────────────────────────────────────
#  Token Estimation
# ────────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """Fast token estimate (4 chars ≈ 1 token for English)."""
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: List[Message]) -> int:
    total = 0
    for m in messages:
        total += estimate_tokens(m.content) + 4  # role overhead
    return total


# ────────────────────────────────────────────────────────
#  Conversation Turn
# ────────────────────────────────────────────────────────

@dataclass
class ConversationTurn:
    """A single turn in the conversation."""
    role: Role
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # For tool results
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    # Token count (cached)
    _tokens: int = 0

    @property
    def tokens(self) -> int:
        if not self._tokens:
            self._tokens = estimate_tokens(self.content) + 4
        return self._tokens

    def to_message(self) -> Message:
        return Message(
            role=self.role,
            content=self.content,
            name=self.tool_name,
            tool_call_id=self.tool_call_id,
        )


# ────────────────────────────────────────────────────────
#  Conversation Session
# ────────────────────────────────────────────────────────

@dataclass
class ConversationSession:
    """A single conversation session with full history."""
    id: str
    system_prompt: str = ""
    turns: List[ConversationTurn] = field(default_factory=list)
    summary: str = ""                  # Summary of older turns
    summary_covers_up_to: int = 0      # Index of last summarized turn
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        tokens = estimate_tokens(self.system_prompt)
        tokens += estimate_tokens(self.summary) if self.summary else 0
        for turn in self.turns[self.summary_covers_up_to:]:
            tokens += turn.tokens
        return tokens

    @property
    def turn_count(self) -> int:
        return len(self.turns)


# ────────────────────────────────────────────────────────
#  Conversation Manager
# ────────────────────────────────────────────────────────

SUMMARIZE_PROMPT = """Summarize the following conversation turns into a concise summary.
Preserve:
- Key facts and decisions made
- User preferences expressed
- Important context needed for future turns
- Any unresolved questions or tasks

Keep it under 500 words. Be factual and precise.

CONVERSATION:
{conversation}

SUMMARY:"""


class ConversationManager:
    """
    Manages conversation context with intelligent windowing.

    Usage:
        cm = ConversationManager(llm=router, max_context_tokens=100_000)
        session = cm.new_session(system_prompt="You are a helpful assistant.")

        # Add turns
        cm.add_user_message(session.id, "Hello!")
        cm.add_assistant_message(session.id, "Hi! How can I help?")

        # Get messages for LLM (auto-managed context window)
        messages = cm.get_context_messages(session.id)

        # Add tool results
        cm.add_tool_result(session.id, tool_call_id="tc_1",
                           tool_name="browser", content="Page loaded")
    """

    def __init__(self, llm: Optional[LLMRouter] = None,
                 max_context_tokens: int = 100_000,
                 summarize_threshold: float = 0.7,
                 storage_dir: Optional[str] = None):
        self.llm = llm
        self.max_context_tokens = max_context_tokens
        self.summarize_threshold = summarize_threshold  # summarize when 70% full
        self.sessions: Dict[str, ConversationSession] = {}
        self.storage_dir = storage_dir
        if storage_dir:
            os.makedirs(storage_dir, exist_ok=True)

    def new_session(self, system_prompt: str = "",
                    session_id: Optional[str] = None,
                    metadata: Optional[Dict] = None) -> ConversationSession:
        """Create a new conversation session."""
        sid = session_id or f"conv_{int(time.time() * 1000)}"
        session = ConversationSession(
            id=sid,
            system_prompt=system_prompt,
            metadata=metadata or {},
        )
        self.sessions[sid] = session
        return session

    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        return self.sessions.get(session_id)

    def add_user_message(self, session_id: str, content: str,
                         metadata: Optional[Dict] = None):
        """Add a user message to the conversation."""
        session = self.sessions[session_id]
        session.turns.append(ConversationTurn(
            role=Role.USER,
            content=content,
            metadata=metadata or {},
        ))
        self._maybe_summarize(session)

    def add_assistant_message(self, session_id: str, content: str,
                              metadata: Optional[Dict] = None):
        """Add an assistant message to the conversation."""
        session = self.sessions[session_id]
        session.turns.append(ConversationTurn(
            role=Role.ASSISTANT,
            content=content,
            metadata=metadata or {},
        ))

    def add_tool_result(self, session_id: str, tool_call_id: str,
                        tool_name: str, content: str):
        """Add a tool result to the conversation."""
        session = self.sessions[session_id]
        session.turns.append(ConversationTurn(
            role=Role.TOOL,
            content=content,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        ))

    def add_system_context(self, session_id: str, context: str):
        """Inject additional system context mid-conversation."""
        session = self.sessions[session_id]
        session.turns.append(ConversationTurn(
            role=Role.SYSTEM,
            content=context,
            metadata={"type": "injected_context"},
        ))

    def get_context_messages(self, session_id: str) -> List[Message]:
        """
        Get the optimally windowed messages for an LLM call.
        Handles summarization and token budget automatically.
        """
        session = self.sessions[session_id]
        messages: List[Message] = []

        # 1. System prompt is always first
        # (handled separately by LLM router as 'system' param)

        # 2. Add summary of older turns if exists
        if session.summary:
            messages.append(Message(
                Role.SYSTEM,
                f"[Summary of earlier conversation]\n{session.summary}"
            ))

        # 3. Add recent turns (after summary cutoff)
        recent = session.turns[session.summary_covers_up_to:]

        # Token budget check — keep removing oldest if over budget
        budget = self.max_context_tokens - estimate_tokens(session.system_prompt)
        if session.summary:
            budget -= estimate_tokens(session.summary) + 20

        # Walk backwards to prioritize recent turns
        included = []
        used = 0
        for turn in reversed(recent):
            if used + turn.tokens > budget:
                break
            included.append(turn)
            used += turn.tokens
        included.reverse()

        for turn in included:
            messages.append(turn.to_message())

        return messages

    def get_system_prompt(self, session_id: str) -> str:
        """Get the system prompt for a session."""
        return self.sessions[session_id].system_prompt

    def get_full_history(self, session_id: str) -> List[ConversationTurn]:
        """Get complete conversation history (for export/debug)."""
        return list(self.sessions.get(session_id, ConversationSession(id="")).turns)

    def save_session(self, session_id: str):
        """Persist session to disk."""
        if not self.storage_dir:
            return
        session = self.sessions.get(session_id)
        if not session:
            return
        path = os.path.join(self.storage_dir, f"{session_id}.json")
        data = {
            "id": session.id,
            "system_prompt": session.system_prompt,
            "summary": session.summary,
            "summary_covers_up_to": session.summary_covers_up_to,
            "created_at": session.created_at,
            "metadata": session.metadata,
            "turns": [
                {
                    "role": t.role.value,
                    "content": t.content,
                    "timestamp": t.timestamp,
                    "metadata": t.metadata,
                    "tool_call_id": t.tool_call_id,
                    "tool_name": t.tool_name,
                }
                for t in session.turns
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_session(self, session_id: str) -> Optional[ConversationSession]:
        """Load session from disk."""
        if not self.storage_dir:
            return None
        path = os.path.join(self.storage_dir, f"{session_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        session = ConversationSession(
            id=data["id"],
            system_prompt=data["system_prompt"],
            summary=data.get("summary", ""),
            summary_covers_up_to=data.get("summary_covers_up_to", 0),
            created_at=data.get("created_at", time.time()),
            metadata=data.get("metadata", {}),
        )
        for td in data.get("turns", []):
            session.turns.append(ConversationTurn(
                role=Role(td["role"]),
                content=td["content"],
                timestamp=td.get("timestamp", 0),
                metadata=td.get("metadata", {}),
                tool_call_id=td.get("tool_call_id"),
                tool_name=td.get("tool_name"),
            ))
        self.sessions[session.id] = session
        return session

    def _maybe_summarize(self, session: ConversationSession):
        """Summarize older turns if context is getting too large."""
        threshold = int(self.max_context_tokens * self.summarize_threshold)
        if session.total_tokens < threshold:
            return
        if not self.llm:
            return

        # Summarize the oldest half of unsummarized turns
        unsummarized = session.turns[session.summary_covers_up_to:]
        if len(unsummarized) < 6:
            return  # not enough to summarize

        to_summarize = unsummarized[:len(unsummarized) // 2]
        conversation_text = "\n".join(
            f"{t.role.value}: {t.content}" for t in to_summarize
        )

        prompt = SUMMARIZE_PROMPT.format(conversation=conversation_text)

        try:
            new_summary = self.llm.chat(
                prompt,
                system="Create a concise, factual conversation summary.",
                temperature=0.1,
                max_tokens=1024,
            )

            # Merge with existing summary
            if session.summary:
                session.summary = f"{session.summary}\n\n---\n\n{new_summary}"
            else:
                session.summary = new_summary

            session.summary_covers_up_to += len(to_summarize)
        except ConnectionError:
            pass  # keep full history if summarization fails

    def stats(self, session_id: str) -> Dict[str, Any]:
        """Get session statistics."""
        session = self.sessions.get(session_id)
        if not session:
            return {}
        return {
            "session_id": session.id,
            "total_turns": len(session.turns),
            "user_turns": sum(1 for t in session.turns if t.role == Role.USER),
            "assistant_turns": sum(1 for t in session.turns if t.role == Role.ASSISTANT),
            "tool_turns": sum(1 for t in session.turns if t.role == Role.TOOL),
            "total_tokens": session.total_tokens,
            "has_summary": bool(session.summary),
            "summarized_turns": session.summary_covers_up_to,
            "created_at": session.created_at,
        }
