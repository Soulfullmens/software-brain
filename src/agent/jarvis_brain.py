"""
JarvisBrain v5 — Autonomous AI Agent

NOT hardcoded regex patterns. Uses the LLM to THINK, PLAN, ACT, OBSERVE.

You say: "I want to watch Dhurander movie"
It does: Opens browser → Searches movie → Finds streaming site → Plays it
         ...all while showing you live progress tabs.

Architecture:
1. SmartAgent = Memory + Learning + Chat (the knowledge)
2. AutonomousEngine = LLM-powered Think→Plan→Act loop (the intelligence)
3. Desktop + Browser = Hands and eyes (the actions)
4. Jarvis = Error prevention (the safety net)
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.agent.smart_agent import SmartAgent, SmartResponse
from src.agent.autonomous_engine import AutonomousEngine
from src.tools.desktop_control import DesktopControl, ActionResult
from src.tools.browser_automation import BrowserAutomation, BrowserResult

try:
    from src.agent.llm_router import LLMRouter
    LLM_ROUTER_AVAILABLE = True
except ImportError:
    LLM_ROUTER_AVAILABLE = False

try:
    from jarvis_v2.jarvis_dev import JarvisDev
    JARVIS_AVAILABLE = True
except ImportError:
    JARVIS_AVAILABLE = False


# ═══════════════════════════════════════════════════════
#  JarvisBrain — The Unified Super Agent
# ═══════════════════════════════════════════════════════

class JarvisBrain:
    """
    Autonomous AI Agent — understands natural language, plans, and acts.
    
    NOT regex. NOT hardcoded. The LLM decides what to do.
    
    "I want to watch Dhurander movie" →
        1. Opens browser
        2. Searches "Dhurander bollywood movie watch online"
        3. Reads search results
        4. Clicks best streaming link
        5. Reports back
    
    USAGE:
        brain = JarvisBrain.from_env()
        
        # Autonomous mode — it figures out what to do
        for event in brain.autonomous_stream("I want to watch a movie"):
            print(event)
        
        # Simple chat with memory
        r = brain.smart_chat("What is quantum computing?")
    """

    def __init__(
        self,
        data_dir: str = "./agent_data/smart_demo",
        ollama_url: str = "http://localhost:11434",
        preferred_model: Optional[str] = None,
        headless: bool = True,
    ):
        # Core SmartAgent (memory + learning + chat)
        self.agent = SmartAgent(
            data_dir=data_dir,
            ollama_url=ollama_url,
            preferred_model=preferred_model,
        )

        # Desktop Control (open apps, type, click)
        self.desktop = DesktopControl(
            screenshot_dir=os.path.join(data_dir, "..", "screenshots")
        )

        # Browser Automation (navigate, fill, read)
        self.browser = BrowserAutomation(
            headless=headless,
            screenshot_dir=os.path.join(data_dir, "..", "screenshots"),
        )

        # LLM Router (Claude tool calling)
        self._llm_router = None
        if LLM_ROUTER_AVAILABLE:
            try:
                env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
                self._llm_router = LLMRouter.from_env(env_path)
            except Exception:
                pass

        # Autonomous Engine (LLM-powered planner + executor)
        self._engine = AutonomousEngine(
            llm_bridge=self.agent._brain,
            desktop=self.desktop,
            browser=self.browser,
            llm_router=self._llm_router,
            memory_store=getattr(self.agent, "_memory", None),
            continual_learner=getattr(self.agent, "_continual", None),
        )

        # Jarvis Developer Co-Pilot (error prevention)
        self.jarvis = JarvisDev() if JARVIS_AVAILABLE else None

        # Stats
        self._tool_successes = 0
        self._tool_failures = 0
        self._action_history: List[Dict] = []

    @classmethod
    def from_env(cls, **kwargs) -> JarvisBrain:
        env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        key, value = key.strip(), value.strip()
                        if value:
                            os.environ[key] = value
        return cls(**kwargs)

    # ═══════════════════════════════════════
    #  Autonomous Mode — LLM Plans & Executes
    # ═══════════════════════════════════════

    def smart_chat(self, message: str) -> Dict:
        """
        The ONE method for everything. Handles natural language.
        
        - "What is quantum computing?" → chat with memory
        - "Open Chrome" → autonomous execution
        - "I want to watch Dhurander movie" → multi-step autonomous plan
        """
        start = time.time()

        # Does this need tools?
        if self._engine.needs_tools(message):
            # Create plan and execute
            plan = self._engine.create_plan(message)
            if plan.needs_tools and plan.steps:
                results = []
                for event in self._engine.execute_plan(plan):
                    results.append(event)
                
                # Build response from execution results
                summary_parts = [f"Intent: {plan.intent}"]
                for r in results:
                    if r["type"] == "step_done":
                        summary_parts.append(f"  Step {r['step_id']}: {r['detail']}")
                    elif r["type"] == "step_failed":
                        summary_parts.append(f"  Step {r['step_id']}: FAILED - {r['error']}")
                    elif r["type"] == "complete":
                        summary_parts.append(r["summary"])

                # Learn from execution (lightweight — log for memory)
                self._learn_from_execution(plan, results)

                return {
                    "content": "\n".join(summary_parts),
                    "tool_used": "autonomous",
                    "plan": {"intent": plan.intent, "thinking": plan.thinking,
                             "steps": [{"action": s.action, "description": s.description, 
                                       "status": s.status} for s in plan.steps]},
                    "model": "",
                    "provider": "autonomous",
                    "memories_retrieved": 0,
                    "latency_ms": round((time.time() - start) * 1000),
                }

        # Regular chat with memory
        response = self.agent.chat(message)
        return {
            "content": response.content,
            "tool_used": None,
            "plan": None,
            "model": response.model_used,
            "provider": response.provider,
            "memories_retrieved": response.memories_retrieved,
            "latency_ms": round(response.latency_ms),
        }

    def smart_chat_stream(self, message: str) -> Generator[Dict, None, None]:
        """
        Streaming version — yields real-time progress events.
        
        Uses the autonomous engine's multi-round observe→think→act loop:
        - For tool tasks: plan → execute → observe → replan if needed
        - For chat: streaming token-by-token with memory
        
        Events:
          {"type": "thinking", "content": "..."}
          {"type": "plan", "intent": "...", "steps": [...]}
          {"type": "step_start", "step_id": 1, "description": "..."}
          {"type": "step_done", "step_id": 1, "detail": "..."}
          {"type": "observe", "content": "..."}  (agent observing results)
          {"type": "replan", "reason": "...", "new_steps": [...]}  (agent adapting)
          {"type": "token", "content": "..."}  (for chat mode)
          {"type": "done", "meta": {...}}
        """
        start = time.time()

        # Check if tools needed
        if self._engine.needs_tools(message):
            # Use the full multi-round autonomous loop
            plan_intent = ""
            complete_time_ms = 0
            for event in self._engine.run(message):
                if event.get("type") == "plan":
                    plan_intent = event.get("intent", message)
                if event.get("type") == "complete":
                    complete_time_ms = round((time.time() - start) * 1000)
                if event.get("type") == "chat_mode":
                    # Engine decided no tools needed — fall through to chat
                    break
                yield event
            else:
                # Engine completed (didn't break) — emit done immediately
                yield {"type": "done", "meta": {
                    "mode": "autonomous",
                    "intent": plan_intent or message,
                    "latency_ms": complete_time_ms or round((time.time() - start) * 1000),
                }}
                # Learn in background (don't block the SSE response)
                if plan_intent:
                    import threading
                    threading.Thread(
                        target=self._learn_from_run,
                        args=(plan_intent, message),
                        daemon=True,
                    ).start()
                return

        # Regular streaming chat
        yield from self.agent.chat_stream(message)

    def _learn_from_run(self, intent: str, original_message: str):
        """Store execution experience in memory after a run.
        
        Note: Detailed step-level learning is now handled by
        AutonomousEngine._store_execution_experience() and _self_reflect().
        This method only records the high-level action history.
        """
        self._action_history.append({
            "intent": intent,
            "message": original_message,
            "timestamp": time.time(),
        })

    def _learn_from_execution(self, plan, results):
        """Store execution outcome in memory for future reference."""
        try:
            success = all(r.get("type") != "step_failed" for r in results)
            self._memory.store(
                text=f"Autonomous task: {plan.intent} — {'completed successfully' if success else 'had failures'}",
                category="execution_log",
                importance=0.3,
                confidence=0.8,
            )
        except Exception:
            pass  # Non-critical

    def cancel(self):
        """Cancel any running autonomous execution."""
        self._engine.cancel()

    # ═══════════════════════════════════════
    #  Learn Mode — Record & Replay User Actions
    # ═══════════════════════════════════════

    def start_learn(self) -> Dict:
        """Start recording user actions across all apps."""
        return self._engine.start_learn_recording()

    def stop_learn(self) -> Dict:
        """Stop recording and return summary."""
        return self._engine.stop_learn_recording()

    def analyze_learn(self) -> Dict:
        """Analyze the recorded actions with LLM to extract intent."""
        return self._engine.analyze_recording()

    def replay_learn(self, preferences: str = "") -> Generator[Dict, None, None]:
        """Replay the learned workflow with optional user preferences."""
        yield from self._engine.replay_workflow(preferences)

    # ═══════════════════════════════════════
    #  Direct Tool Access (for API endpoints)
    # ═══════════════════════════════════════

    def open_app(self, name: str, args: List[str] = None) -> ActionResult:
        return self.desktop.open_app(name, args)

    def browse_to(self, url: str) -> BrowserResult:
        return self.browser.goto(url)

    def search(self, query: str) -> BrowserResult:
        return self.browser.google_search(query)

    def run_cmd(self, command: str, timeout: int = 30) -> ActionResult:
        return self.desktop.run_command(command, timeout=timeout)

    def take_screenshot(self) -> ActionResult:
        return self.desktop.screenshot()

    # ═══════════════════════════════════════
    #  Multi-Step Workflows (direct)
    # ═══════════════════════════════════════

    def browse_and_fill(self, url: str, form_data: Dict[str, str],
                        submit_selector: str = None) -> Dict:
        results = {"steps": []}
        r = self.browser.goto(url)
        results["steps"].append({"action": "goto", "success": r.success, "url": url})
        if not r.success:
            results["success"] = False
            return results
        time.sleep(1)
        r = self.browser.fill_form(form_data)
        results["steps"].append({"action": "fill_form", "success": r.success})
        if submit_selector:
            time.sleep(0.5)
            r = self.browser.click(submit_selector)
            results["steps"].append({"action": "submit", "success": r.success})
        results["success"] = all(s["success"] for s in results["steps"])
        return results

    # ═══════════════════════════════════════
    #  Jarvis Integration
    # ═══════════════════════════════════════

    def check_code(self, command: str, file_path: str = "", code_text: str = None) -> List[Dict]:
        if not self.jarvis:
            return []
        return self.jarvis.check_before_run(command, file_path, code_text)

    def record_error(self, traceback_text: str, **kwargs) -> Dict:
        result = {}
        if self.jarvis:
            result = self.jarvis.record_error(traceback_text, **kwargs)
        self.agent._memory.store(
            content=f"Error encountered: {traceback_text[:500]}",
            collection="procedural",
            source="error_learning",
            importance=0.6,
            confidence=0.9,
        )
        return result

    # ═══════════════════════════════════════
    #  Delegated SmartAgent Methods
    # ═══════════════════════════════════════

    def chat(self, message: str) -> SmartResponse:
        return self.agent.chat(message)

    def teach(self, name, description, examples=None, category="general"):
        return self.agent.teach(name, description, examples, category)

    def remember(self, fact, importance=0.7):
        return self.agent.remember(fact, importance)

    def recall(self, query, limit=10):
        return self.agent.recall(query, limit)

    def correct(self, wrong, correct_answer):
        return self.agent.correct(wrong, correct_answer)

    def recognize(self, text, category=None):
        return self.agent.recognize(text, category)

    def learn_skill(self, name, description, steps):
        return self.agent.learn_skill(name, description, steps)

    def harvest_topic(self, query, max_articles=3):
        return self.agent.harvest_topic(query, max_articles)

    def smart_harvest(self, query):
        return self.agent.smart_harvest(query)

    def new_session(self):
        return self.agent.new_session()

    # ═══════════════════════════════════════
    #  Status
    # ═══════════════════════════════════════

    def full_status(self) -> Dict:
        agent_status = self.agent.status()
        return {
            "agent": {
                "model": agent_status.active_model,
                "ollama_running": agent_status.ollama_running,
                "available_models": agent_status.available_models,
                "total_memories": agent_status.total_memories,
                "memories_by_collection": agent_status.memories_by_collection,
                "prototypes_learned": agent_status.prototypes_learned,
                "facts_extracted": agent_status.facts_extracted,
                "total_interactions": agent_status.total_interactions,
                "knowledge_growth_rate": round(agent_status.knowledge_growth_rate, 2),
                "avg_latency_ms": round(agent_status.avg_latency_ms),
                "total_requests": agent_status.total_requests,
            },
            "desktop": {"actions_performed": len(self.desktop._action_log)},
            "browser": self.browser.get_status(),
            "autonomous": self._engine.stats,
            "jarvis": {
                "available": self.jarvis is not None,
                "status": self.jarvis.status() if self.jarvis else None,
            },
            "tools": {
                "total_actions": len(self._action_history),
                "successes": self._tool_successes,
                "failures": self._tool_failures,
            },
        }

    def close(self):
        self.browser.close()
