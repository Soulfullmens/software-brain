"""Comprehensive module audit for NOMAD SecureChat platform."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

ok = []
fail = []

modules = [
    ("react_loop", "src.agent.intelligence.react_loop"),
    ("persona_engine", "src.agent.intelligence.persona_engine"),
    ("swarm_orchestrator", "src.agent.intelligence.swarm_orchestrator"),
    ("knowledge_harvester", "src.agent.intelligence.knowledge_harvester"),
    ("knowledge_graph", "src.agent.intelligence.knowledge_graph"),
    ("entity_extractor", "src.agent.intelligence.entity_extractor"),
    ("network_policy", "src.agent.security.network_policy"),
    ("inference_gateway", "src.agent.security.inference_gateway"),
    ("security_kernel", "src.agent.security.security_kernel"),
    ("browser_tool", "src.agent.tools.browser_tool"),
    ("shell", "src.agent.tools.shell"),
    ("fast_browser", "src.agent.tools.fast_browser"),
    ("db", "chat_platform.db"),
    ("crypto", "chat_platform.crypto"),
    ("translator", "chat_platform.translator"),
    ("agent_bridge", "chat_platform.agent_bridge"),
]

for name, mod_path in modules:
    try:
        __import__(mod_path)
        ok.append(name)
    except Exception as e:
        fail.append((name, str(e)[:100]))

print("=" * 60)
print(f"  NOMAD Module Audit: {len(ok)} OK / {len(fail)} FAIL")
print("=" * 60)
print("\n✅ WORKING:")
for m in ok:
    print(f"   • {m}")
print("\n❌ FAILED:")
for m, err in fail:
    print(f"   • {m}: {err}")
print()

# Test Persona Engine
print("--- Persona Engine Test ---")
try:
    from src.agent.intelligence.persona_engine import PersonaEngine
    pe = PersonaEngine()
    p = pe.select_persona("Should I sell Tesla stock if US goes to war?")
    print(f"  Selected: {p.name} ({p.archetype}) for stock question")
    p2 = pe.select_persona("Debug this Python error")
    print(f"  Selected: {p2.name} ({p2.archetype}) for coding question")
    print("  ✅ Persona Engine works")
except Exception as e:
    print(f"  ❌ {e}")

# Test Swarm Orchestrator init
print("\n--- Swarm Orchestrator Test ---")
try:
    from src.agent.intelligence.swarm_orchestrator import SwarmOrchestrator
    print(f"  ✅ SwarmOrchestrator imported OK")
except Exception as e:
    print(f"  ❌ {e}")

# Test Knowledge Harvester
print("\n--- Knowledge Harvester Test ---")
try:
    from src.agent.intelligence.knowledge_harvester import KnowledgeHarvester
    h = KnowledgeHarvester()
    stats = h.store.get_stats()
    print(f"  KB items: {stats['total_knowledge_items']}, words: {stats['total_words']}")
    print(f"  ✅ Knowledge Harvester works")
except Exception as e:
    print(f"  ❌ {e}")

print("\n" + "=" * 60)
print("DONE")
