"""
insight_daemon.py — Background Knowledge Synthesizer (The "Dreaming" Phase)

Simulates continuous background learning. When idle, the daemon scans the
Knowledge Graph for unlinked clusters or high-mention nodes, prompts the LLM
to deduce new insights, and injects "Hypothesis" or "Synthesis" facts.

CAPABILITIES:
    1. Idle Detection: Runs safely in the background.
    2. Graph Scanning: Finds complex overlapping nodes in the Knowledge Graph.
    3. LLM Deduction: Asks the LLM to find hidden connections or implications.
    4. Auto-Injection: Stores discoveries permanently in the graph.
"""
import threading
import time
import json
import logging
from typing import Callable, Optional, List, Dict, Any

from .knowledge_graph import KnowledgeGraph


class InsightDaemon:
    """
    Runs in a background thread to generate insights from the graph.
    """
    def __init__(self, kg: KnowledgeGraph, llm_fn: Callable, interval_sec: int = 60):
        self.kg = kg
        self.llm_fn = llm_fn
        self.interval_sec = interval_sec
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stats = {"dreams_run": 0, "insights_generated": 0}
        self.logger = logging.getLogger("InsightDaemon")

    def start(self):
        """Start the background daemon."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._daemon_loop, daemon=True, name="InsightDaemon")
        self._thread.start()
        self.logger.info("Insight Daemon started. Agent will now 'dream' in the background.")

    def stop(self):
        """Stop the background daemon."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def trigger_dream_now(self) -> int:
        """Manually trigger a dreaming cycle immediately. Returns new insights count."""
        return self._dream_cycle()

    def _daemon_loop(self):
        """Infinite loop for the background thread."""
        while self._running:
            time.sleep(self.interval_sec)
            try:
                self._dream_cycle()
            except Exception as e:
                self.logger.error(f"Daemon error during dreaming: {e}")

    def _dream_cycle(self) -> int:
        """
        The core dreaming process:
        1. Find 3 highly mentioned entities.
        2. Get their neighborhoods.
        3. Ask LLM to find a hidden connection.
        4. Add it to the graph.
        """
        self._stats["dreams_run"] += 1
        
        # 1. Get top entities
        top_entities = self.kg.list_entities(limit=3)
        if len(top_entities) < 2:
            return 0  # Not enough data to dream

        # 2. Gather context
        context_lines = []
        for ent in top_entities:
            neighborhood = self.kg.get_entity_neighborhood(ent.name, depth=1)
            context_lines.append(f"Entity: {ent.name} ({ent.entity_type})")
            context_lines.append(f"  Summary: {ent.summary}")
            if neighborhood.facts:
                context_lines.append("  Known Facts:")
                for fact in neighborhood.facts[:5]:
                    context_lines.append(f"    - {fact}")
            context_lines.append("")

        context_str = "\n".join(context_lines)

        # 3. Prompt LLM to synthesize
        prompt = (
            "You are a background cognitive process scanning memory for hidden insights.\n"
            "Review the following active knowledge:\n\n"
            f"{context_str}\n"
            "Based ONLY on the above, deduce 1 or 2 non-obvious, highly valuable insights, conclusions, or hypotheses.\n"
            "Return valid JSON matching this schema exactly:\n"
            "{\n"
            '  "insights": [\n'
            '    {\n'
            '      "source_entity": "Name of entity",\n'
            '      "target_entity": "Name of another entity",\n'
            '      "fact": "The newly deduced connection or hypothesis"\n'
            '    }\n'
            "  ]\n"
            "}"
        )

        try:
            response = self.llm_fn(prompt)
            # Parse safely
            start_idx = response.find("{")
            end_idx = response.rfind("}") + 1
            if start_idx == -1 or end_idx == 0:
                return 0
            
            data = json.loads(response[start_idx:end_idx])
            insights = data.get("insights", [])
            
            # 4. Inject into graph
            count = 0
            for ins in insights:
                source = ins.get("source_entity")
                target = ins.get("target_entity")
                fact = ins.get("fact")
                if source and target and fact:
                    self.kg.add_relationship(
                        source_name=source,
                        target_name=target,
                        relationship="synthesized_insight",
                        fact=f"[DEDUCED] {fact}",
                        confidence=0.6,
                        source="daemon_dream"
                    )
                    count += 1
                    self._stats["insights_generated"] += 1
            return count

        except Exception as e:
            self.logger.warning(f"Dream cycle failed to parse LLM: {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        return dict(self._stats)
