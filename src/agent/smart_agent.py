"""
SmartAgent — The "Small Brain + Big Memory" Orchestrator

PURPOSE: This is the UNIFIED agent that implements the full
"Small Brain + Big Memory" architecture:

    ┌─────────────────────────────────────────────────────────────┐
    │                     SmartAgent (~2-6 GB)                     │
    │                                                             │
    │  ┌──────────────┐    ┌────────────────────────────────┐    │
    │  │  SMALL BRAIN  │◄──►│  BIG MEMORY (Vector Store)     │    │
    │  │  (1-3B model) │    │  ┌────────┐ ┌──────────────┐  │    │
    │  │  Via Ollama   │    │  │Episodic│ │  Semantic    │  │    │
    │  │  or Cloud API │    │  │        │ │  (facts)     │  │    │
    │  │               │    │  └────────┘ └──────────────┘  │    │
    │  │  Handles:     │    │  ┌────────┐ ┌──────────────┐  │    │
    │  │  - Reasoning  │    │  │Proced. │ │  Prototypes  │  │    │
    │  │  - Planning   │    │  │(skills)│ │  (few-shot)  │  │    │
    │  │  - Language   │    │  └────────┘ └──────────────┘  │    │
    │  └──────────────┘    │  ┌──────────────────────────┐  │    │
    │         │             │  │  Web Knowledge           │  │    │
    │         ▼             │  │  (ingested internet)     │  │    │
    │  ┌──────────────┐    │  └──────────────────────────┘  │    │
    │  │  FEW-SHOT    │    └────────────────────────────────┘    │
    │  │  LEARNER     │                                          │
    │  │  See once →  │    ┌────────────────────────────────┐    │
    │  │  Remember    │    │  CONTINUAL LEARNER              │    │
    │  │  forever     │    │  Gets smarter every day         │    │
    │  └──────────────┘    │  No retraining needed           │    │
    │                       └────────────────────────────────┘    │
    │                                                             │
    │  ┌──────────────────────────────────────────────────────┐  │
    │  │  EXISTING TOOLS (Browser, Email, Shell, Desktop)      │  │
    │  │  + Existing Reasoning Engine (CoT, ToT)               │  │
    │  │  + Existing Safety/Authority System                    │  │
    │  └──────────────────────────────────────────────────────┘  │
    └─────────────────────────────────────────────────────────────┘

KEY INSIGHT:
    Traditional: 175B parameters = 350GB+ = massive GPU cluster
    SmartAgent:  3B parameters + Vector DB = 2-6GB = runs on a laptop
    
    The Vector Memory IS the missing billions of parameters.
    Instead of encoding knowledge in weights, we store it in
    searchable memory and retrieve it at inference time.

FLOW:
    1. User asks something
    2. SmartAgent retrieves relevant memories (RAG)
    3. Memory context is injected into the prompt
    4. Small model generates response WITH full knowledge
    5. Continual Learner extracts facts and stores them
    6. Agent gets smarter with every interaction

INTEGRATES WITH EXISTING:
    - ClaudeAgent (existing) — for complex tasks that need full power
    - ReasoningEngine (existing) — for deep thinking
    - ToolProtocol (existing) — for agentic tool use
    - MemoryManager (existing) — bridged to vector store
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ..memory.vector_store import VectorMemoryStore
from ..learning.few_shot_learner import FewShotLearner
from ..learning.continual_learner import ContinualLearner
from ..knowledge.harvester import KnowledgeHarvester
from ..knowledge.multi_source_harvester import MultiSourceHarvester
from ..knowledge.vision_analyzer import VisionAnalyzer
from .small_model_bridge import SmallModelBridge, SmallModelResponse


# ────────────────────────────────────────────────────────
#  Data Structures
# ────────────────────────────────────────────────────────

@dataclass
class SmartResponse:
    """Response from the SmartAgent."""
    content: str
    model_used: str
    provider: str
    memories_retrieved: int
    memories_used_in_context: bool
    new_facts_learned: int
    latency_ms: float
    thinking: Optional[str] = None  # Chain-of-thought if reasoning was used


@dataclass
class AgentStatus:
    """Full status of the SmartAgent system."""
    # Model
    active_model: str
    ollama_running: bool
    available_models: List[str]
    
    # Memory
    total_memories: int
    memories_by_collection: Dict[str, int]
    
    # Learning
    prototypes_learned: int
    facts_extracted: int
    total_interactions: int
    knowledge_growth_rate: float
    
    # Performance
    avg_latency_ms: float
    total_requests: int


# ────────────────────────────────────────────────────────
#  SmartAgent
# ────────────────────────────────────────────────────────

class SmartAgent:
    """
    The unified "Small Brain + Big Memory" agent.
    
    This is the main entry point for the new architecture.
    It combines:
    - Small Model Bridge (1-3B local model with cloud fallback)
    - Vector Memory Store (ChromaDB-based persistent memory)
    - Few-Shot Learner (learn from 1-5 examples)
    - Continual Learner (gets smarter every interaction)
    
    USAGE:
        # Create the agent
        agent = SmartAgent.from_env()
        
        # Chat (with automatic memory retrieval + learning)
        response = agent.chat("What should I work on today?")
        
        # Teach it something (one-shot)
        agent.teach("spam_email", "Unsolicited commercial emails",
                   examples=["Buy now!", "You won $1M!"])
        
        # It remembers and recognizes
        result = agent.recognize("Amazing deal! Free money!")
        # → "spam_email" (confidence: 0.82)
        
        # Ingest web knowledge
        agent.ingest_url("https://docs.python.org/3/tutorial/")
        
        # Get status
        status = agent.status()
        # → 3B model, 15,234 memories, 47 prototypes, 2.3 facts/day
    """

    def __init__(
        self,
        data_dir: str = "./agent_data",
        ollama_url: str = "http://localhost:11434",
        preferred_model: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ):
        self._data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

        # 1. BIG MEMORY — Vector Store
        self._memory = VectorMemoryStore(
            persist_dir=os.path.join(data_dir, "vector_memory"),
        )

        # 2. SMALL BRAIN — Model Bridge
        self._brain = SmallModelBridge(
            ollama_url=ollama_url,
            preferred_model=preferred_model,
        )

        # 3. FEW-SHOT LEARNER
        self._few_shot = FewShotLearner(self._memory)

        # 4. CONTINUAL LEARNER (rule-based extraction — no extra LLM call)
        self._continual = ContinualLearner(
            vector_store=self._memory,
            llm_generate=None,  # Rule-based only — LLM extraction was 30-60s per call
        )

        # 5. KNOWLEDGE HARVESTER — downloads internet into memory
        self._harvester = KnowledgeHarvester(self._memory)

        # 6. MULTI-SOURCE HARVESTER — Wikipedia + WikiHow + StackExchange + arXiv
        self._multi_harvester = MultiSourceHarvester(self._memory)

        # 7. VISION ANALYZER — image/video analysis with auto-harvest
        self._vision = VisionAnalyzer(
            ollama_url=ollama_url,
            harvester=self._multi_harvester,
        )

        # System prompt
        self._system_prompt = system_prompt or self._default_system_prompt()

        # Conversation history (in-memory for current session)
        self._conversation: List[Dict[str, str]] = []
        self._session_start = datetime.now()

        # Stats
        self._total_requests = 0
        self._total_latency = 0.0

    @classmethod
    def from_env(cls, env_path: str = ".env", **kwargs) -> SmartAgent:
        """Create SmartAgent from environment configuration."""
        # Load .env if it exists
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        key, value = key.strip(), value.strip()
                        if value:  # Only set if value is non-empty
                            os.environ[key] = value

        return cls(**kwargs)

    def _default_system_prompt(self) -> str:
        return (
            "You are Jarvis — a fast, precise AI assistant with persistent vector memory.\n\n"
            "## RULES\n"
            "- Be concise and direct — no filler.\n"
            "- Use RELEVANT MEMORIES below to answer accurately. They are personalized facts about the user.\n"
            "- If memories conflict with your training data, prefer the memories.\n"
            "- Never fabricate facts. Say 'I don't know' when uncertain.\n"
            "- Show work for math and code.\n"
            f"\n## CONTEXT\n"
            f"- Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        )

    def _brain_generate(self, prompt: str) -> str:
        """Helper: generate text using the small brain (for internal use)."""
        response = self._brain.generate(prompt, max_tokens=4096)
        return response.content

    # ────────────────────────────────────────────────
    #  Chat — The Main Interface
    # ────────────────────────────────────────────────

    def chat(self, message: str, use_memory: bool = True) -> SmartResponse:
        """
        Chat with the SmartAgent. This is the primary interface.
        
        FLOW:
        1. Retrieve relevant memories (RAG)
        2. Build augmented prompt
        3. Generate response (small model or cloud)
        4. Learn from the interaction
        5. Return response
        
        Args:
            message: User's message
            use_memory: Whether to retrieve memory context (default True)
        
        Returns:
            SmartResponse with content and metadata
        """
        self._total_requests += 1
        start = time.time()

        # Step 1: Retrieve relevant memories (fast — cached embeddings)
        memory_context = ""
        memories_retrieved = 0
        if use_memory:
            memory_context = self._memory.retrieve_for_context(
                query=message,
                max_tokens=800,
                limit=5,
            )
            if memory_context:
                memories_retrieved = memory_context.count("\n")

        # Step 2: Add to conversation history
        self._conversation.append({"role": "user", "content": message})

        # Step 3: Generate response
        if len(self._conversation) > 1:
            # Multi-turn: use chat mode
            response = self._brain.chat(
                messages=self._conversation[-10:],  # Last 10 turns (faster)
                system=self._system_prompt,
                memory_context=memory_context,
                max_tokens=512,
            )
        else:
            # Single turn: use generate mode
            response = self._brain.generate(
                prompt=message,
                system=self._system_prompt,
                memory_context=memory_context,
                max_tokens=512,
            )

        # Step 4: Add response to conversation
        self._conversation.append({"role": "assistant", "content": response.content})

        # Step 5: Learn from this interaction (background)
        learning_event = self._continual.learn_from_interaction(
            user_message=message,
            agent_response=response.content,
            importance=0.5,
        )

        latency = (time.time() - start) * 1000
        self._total_latency += latency

        return SmartResponse(
            content=response.content,
            model_used=response.model,
            provider=response.provider,
            memories_retrieved=memories_retrieved,
            memories_used_in_context=bool(memory_context),
            new_facts_learned=len(learning_event.extracted_facts),
            latency_ms=latency,
        )

    def chat_stream(self, message: str, use_memory: bool = True):
        """
        Stream chat response token-by-token for instant perceived speed.
        
        Yields dicts: {"type": "token", "content": "..."} for tokens,
        then {"type": "done", "meta": {...}} at the end.
        """
        self._total_requests += 1
        start = time.time()

        # Retrieve memories
        memory_context = ""
        memories_retrieved = 0
        if use_memory:
            memory_context = self._memory.retrieve_for_context(
                query=message, max_tokens=800, limit=5,
            )
            if memory_context:
                memories_retrieved = memory_context.count("\n")

        self._conversation.append({"role": "user", "content": message})

        full_response = []
        try:
            if len(self._conversation) > 1:
                gen = self._brain.chat_stream(
                    messages=self._conversation[-10:],
                    system=self._system_prompt,
                    memory_context=memory_context,
                )
            else:
                gen = self._brain.generate_stream(
                    prompt=message,
                    system=self._system_prompt,
                    memory_context=memory_context,
                )

            for token in gen:
                full_response.append(token)
                yield {"type": "token", "content": token}
        except Exception as e:
            yield {"type": "token", "content": f"[Error: {e}]"}
            full_response.append(f"[Error: {e}]")

        content = "".join(full_response)
        self._conversation.append({"role": "assistant", "content": content})

        # Learn in background
        learning_event = self._continual.learn_from_interaction(
            user_message=message, agent_response=content, importance=0.5,
        )

        latency = (time.time() - start) * 1000
        self._total_latency += latency

        yield {
            "type": "done",
            "meta": {
                "model": self._brain._active_model or "cloud",
                "provider": "stream",
                "memories_retrieved": memories_retrieved,
                "new_facts_learned": len(learning_event.extracted_facts),
                "latency_ms": round(latency),
            }
        }

    # ────────────────────────────────────────────────
    #  Correct — Learn From Mistakes
    # ────────────────────────────────────────────────

    def correct(self, wrong_response: str, correct_answer: str) -> str:
        """
        Tell the agent it was wrong. It learns the correction permanently.
        
        Args:
            wrong_response: What the agent said (incorrectly)
            correct_answer: What the correct answer is
        
        Returns:
            Acknowledgment message
        """
        self._continual.learn_from_correction(
            original_response=wrong_response,
            correction=correct_answer,
        )
        return f"Got it! I've permanently learned: {correct_answer}"

    # ────────────────────────────────────────────────
    #  Teach — Few-Shot Learning
    # ────────────────────────────────────────────────

    def teach(
        self,
        name: str,
        description: str,
        examples: Optional[List[str]] = None,
        category: str = "general",
    ) -> str:
        """
        Teach the agent a new concept (one-shot/few-shot).
        Like showing a human a KitKat once — it remembers forever.
        
        Args:
            name: Name of the concept
            description: What it is
            examples: 1-5 example descriptions
            category: Category for organization
        
        Returns:
            Confirmation message
        """
        prototype = self._few_shot.learn(
            name=name,
            description=description,
            examples=examples,
            category=category,
        )
        n_examples = len(examples) if examples else 0
        return (
            f"Learned '{name}' from {n_examples} example(s). "
            f"I'll recognize it forever — no retraining needed."
        )

    def recognize(self, input_text: str, category: Optional[str] = None) -> Dict:
        """
        Try to recognize/classify something against learned prototypes.
        
        Returns dict with: matched, name, confidence, all_matches
        """
        result = self._few_shot.recognize(input_text, category=category)
        return {
            "matched": result.matched,
            "name": result.prototype_name,
            "confidence": result.confidence,
            "category": result.category,
            "all_matches": result.all_matches,
        }

    # ────────────────────────────────────────────────
    #  Knowledge — Ingest & Remember
    # ────────────────────────────────────────────────

    def remember(self, fact: str, importance: float = 0.7) -> str:
        """
        Explicitly tell the agent to remember something.
        
        Args:
            fact: The fact to remember
            importance: How important (0.0-1.0)
        
        Returns:
            Confirmation
        """
        self._memory.store(
            content=fact,
            collection="semantic",
            source="user_explicit",
            importance=importance,
            confidence=0.95,
        )
        return f"Remembered: {fact}"

    def recall(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Recall memories related to a query.
        
        Returns list of {content, collection, relevance, source}
        """
        results = self._memory.retrieve(query, limit=limit, min_relevance=0.3)
        return [
            {
                "content": r.content,
                "collection": r.collection,
                "relevance": round(r.relevance_score, 3),
                "source": r.metadata.get("source", "unknown"),
            }
            for r in results
        ]

    def ingest_text(self, text: str, source: str = "document") -> str:
        """
        Ingest a large text (article, documentation, etc.).
        The agent will chunk it and make it searchable.
        """
        event = self._continual.learn_from_web(
            url=source,
            content=text,
        )
        return f"Ingested text from '{source}' — {len(event.extracted_facts)} facts extracted"

    def learn_skill(
        self,
        name: str,
        description: str,
        steps: List[str],
    ) -> str:
        """Teach the agent a new skill/procedure."""
        self._continual.learn_skill(
            skill_name=name,
            description=description,
            steps=steps,
        )
        return f"Learned skill: {name} ({len(steps)} steps)"

    # ────────────────────────────────────────────────
    #  Knowledge Harvesting — Fill Memory From Internet
    # ────────────────────────────────────────────────

    def harvest_topic(self, query: str, max_articles: int = 3) -> List[Dict]:
        """Search Wikipedia for a topic and harvest articles into memory."""
        results = self._harvester.harvest_topic(query, max_articles)
        return [
            {
                "source": r.source,
                "topic": r.topic,
                "chunks_stored": r.chunks_stored,
                "total_chars": r.total_chars,
                "success": r.success,
                "error": r.error,
                "duration_s": round(r.duration_s, 2),
            }
            for r in results
        ]

    def harvest_url(self, url: str, topic: str = "web") -> Dict:
        """Harvest knowledge from any URL into memory."""
        r = self._harvester.harvest_url(url, topic)
        return {
            "source": r.source,
            "topic": r.topic,
            "chunks_stored": r.chunks_stored,
            "total_chars": r.total_chars,
            "success": r.success,
            "error": r.error,
            "duration_s": round(r.duration_s, 2),
        }

    def harvest_pack(self, pack_name: str, callback=None) -> List[Dict]:
        """Harvest a topic pack (ai_fundamentals, programming, math, business, general)."""
        results = self._harvester.harvest_pack(pack_name, callback)
        return [
            {
                "source": r.source,
                "topic": r.topic,
                "chunks_stored": r.chunks_stored,
                "success": r.success,
                "error": r.error,
            }
            for r in results
        ]

    def harvest_essentials(self, callback=None) -> List[Dict]:
        """Harvest all essential topics — makes agent knowledgeable about CS, AI, math, etc."""
        results = self._harvester.harvest_essentials(callback)
        return [
            {
                "source": r.source,
                "topic": r.topic,
                "chunks_stored": r.chunks_stored,
                "success": r.success,
            }
            for r in results
        ]

    def harvest_custom_text(self, text: str, topic: str = "custom") -> Dict:
        """Store custom text directly into knowledge base."""
        r = self._harvester.harvest_custom(text, topic)
        return {
            "chunks_stored": r.chunks_stored,
            "total_chars": r.total_chars,
            "success": r.success,
        }

    def harvest_stats(self) -> Dict:
        """Get harvesting statistics."""
        return self._harvester.get_stats()

    # ────────────────────────────────────────────────
    #  Multi-Source Harvesting — Smart, Quality-Filtered
    # ────────────────────────────────────────────────

    def smart_harvest(self, query: str) -> List[Dict]:
        """
        Smart multi-source harvest. Searches Wikipedia + WikiHow +
        Stack Exchange + arXiv automatically based on query type.
        Only stores proven, quality-filtered content.
        """
        results = self._multi_harvester.smart_harvest(query)
        return [
            {
                "source": r.source,
                "topic": r.topic,
                "chunks_stored": r.chunks_stored,
                "total_chars": r.total_chars,
                "success": r.success,
                "quality_score": round(r.quality_score, 2),
                "source_type": r.source_type,
                "error": r.error,
                "duration_s": round(r.duration_s, 2),
            }
            for r in results
        ]

    def harvest_wikihow(self, query: str) -> Dict:
        """Harvest practical how-to knowledge from WikiHow."""
        r = self._multi_harvester.harvest_wikihow(query)
        return {
            "source": r.source, "topic": r.topic,
            "chunks_stored": r.chunks_stored, "success": r.success,
            "quality_score": round(r.quality_score, 2), "error": r.error,
        }

    def harvest_stackexchange(self, query: str, site: str = "stackoverflow") -> Dict:
        """Harvest Q&A from Stack Exchange."""
        r = self._multi_harvester.harvest_stackexchange(query, site)
        return {
            "source": r.source, "topic": r.topic,
            "chunks_stored": r.chunks_stored, "success": r.success,
            "quality_score": round(r.quality_score, 2), "error": r.error,
        }

    def harvest_arxiv(self, query: str, max_papers: int = 3) -> Dict:
        """Harvest scientific paper abstracts from arXiv."""
        r = self._multi_harvester.harvest_arxiv(query, max_papers)
        return {
            "source": r.source, "topic": r.topic,
            "chunks_stored": r.chunks_stored, "success": r.success,
            "quality_score": round(r.quality_score, 2), "error": r.error,
        }

    def harvest_multi_pack(self, pack_name: str) -> List[Dict]:
        """Harvest an expanded multi-source topic pack."""
        results = self._multi_harvester.harvest_pack(pack_name)
        return [
            {
                "source": r.source, "topic": r.topic,
                "chunks_stored": r.chunks_stored, "success": r.success,
                "error": r.error,
            }
            for r in results
        ]

    def harvest_wikihow_pack(self, pack_name: str) -> List[Dict]:
        """Harvest a WikiHow how-to pack (cooking, repairs, building)."""
        results = self._multi_harvester.harvest_wikihow_pack(pack_name)
        return [
            {
                "source": r.source, "topic": r.topic,
                "chunks_stored": r.chunks_stored, "success": r.success,
                "error": r.error,
            }
            for r in results
        ]

    def multi_harvest_stats(self) -> Dict:
        """Get multi-source harvesting statistics."""
        return self._multi_harvester.get_stats()

    # ────────────────────────────────────────────────
    #  Vision — Image Analysis + Auto-Harvest
    # ────────────────────────────────────────────────

    def analyze_image(self, image_path: str, question: str = "",
                      auto_harvest: bool = True) -> Dict:
        """
        Analyze an image and auto-harvest related knowledge.
        
        Args:
            image_path: Path to image file
            question: Optional specific question about the image
            auto_harvest: Whether to search internet for related topics
        """
        r = self._vision.analyze_image(image_path, question, auto_harvest)
        return {
            "description": r.description,
            "topics_detected": r.topics_detected,
            "provider": r.provider,
            "model": r.model,
            "auto_harvest_results": r.auto_harvest_results,
            "latency_ms": round(r.latency_ms),
            "success": r.success,
            "error": r.error,
        }

    def analyze_image_bytes(self, image_bytes: bytes, filename: str = "upload.jpg",
                            question: str = "", auto_harvest: bool = True) -> Dict:
        """Analyze image from raw bytes (file upload)."""
        r = self._vision.analyze_image_bytes(image_bytes, filename, question, auto_harvest)
        return {
            "description": r.description,
            "topics_detected": r.topics_detected,
            "provider": r.provider,
            "model": r.model,
            "auto_harvest_results": r.auto_harvest_results,
            "latency_ms": round(r.latency_ms),
            "success": r.success,
            "error": r.error,
        }

    def vision_status(self) -> Dict:
        """Get vision system status."""
        return self._vision.get_status()

    def is_online(self) -> bool:
        """Check if internet is available."""
        return self._harvester.is_online()

    # ────────────────────────────────────────────────
    #  Session Management
    # ────────────────────────────────────────────────

    def new_session(self) -> str:
        """Start a new conversation session."""
        self._conversation = []
        self._session_start = datetime.now()
        return "New session started. Memory is persistent — I still remember everything."

    def get_conversation(self) -> List[Dict[str, str]]:
        """Get the current conversation history."""
        return list(self._conversation)

    # ────────────────────────────────────────────────
    #  Status & Stats
    # ────────────────────────────────────────────────

    def status(self) -> AgentStatus:
        """Get full agent status."""
        brain_status = self._brain.get_status()
        memory_stats = self._memory.get_stats()
        learner_stats = self._few_shot.get_stats()
        continual_stats = self._continual.get_stats()

        avg_latency = (
            self._total_latency / self._total_requests
            if self._total_requests > 0 else 0
        )

        return AgentStatus(
            active_model=brain_status["active_model"] or "cloud_fallback",
            ollama_running=brain_status["ollama_running"],
            available_models=brain_status["available_local_models"],
            total_memories=memory_stats.total_entries,
            memories_by_collection=memory_stats.entries_by_collection,
            prototypes_learned=learner_stats.total_prototypes,
            facts_extracted=continual_stats.facts_extracted,
            total_interactions=continual_stats.total_events_processed,
            knowledge_growth_rate=continual_stats.knowledge_growth_rate,
            avg_latency_ms=avg_latency,
            total_requests=self._total_requests,
        )

    def status_text(self) -> str:
        """Get a human-readable status report."""
        s = self.status()
        lines = [
            "╔══════════════════════════════════════════╗",
            "║   SmartAgent — Small Brain + Big Memory   ║",
            "╚══════════════════════════════════════════╝",
            "",
            f"  🧠 Model:        {s.active_model}",
            f"  🔌 Ollama:       {'✅ Running' if s.ollama_running else '❌ Offline (using cloud)'}",
            f"  📊 Local Models: {', '.join(s.available_models) if s.available_models else 'None'}",
            "",
            f"  💾 Total Memories:     {s.total_memories:,}",
        ]
        for coll, count in s.memories_by_collection.items():
            lines.append(f"     - {coll}: {count:,}")
        lines += [
            "",
            f"  🎯 Prototypes:         {s.prototypes_learned}",
            f"  📝 Facts Extracted:    {s.facts_extracted:,}",
            f"  💬 Total Interactions: {s.total_interactions:,}",
            f"  📈 Growth Rate:        {s.knowledge_growth_rate:.1f} entries/day",
            "",
            f"  ⏱️  Avg Latency:       {s.avg_latency_ms:.0f}ms",
            f"  📡 Total Requests:     {s.total_requests:,}",
            "",
            "  Architecture: Small Brain (~2-6GB) + Big Memory (unlimited)",
            "  No retraining needed — learns from every interaction.",
        ]
        return "\n".join(lines)
