"""Clean module audit - no emoji, file output."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

results = {"ok": [], "fail": [], "tests": {}}

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
        results["ok"].append(name)
    except Exception as e:
        results["fail"].append({"name": name, "error": str(e)[:120]})

# Test Persona Engine
try:
    from src.agent.intelligence.persona_engine import PersonaEngine
    pe = PersonaEngine()
    p = pe.select_persona("Should I sell Tesla stock if US goes to war?")
    results["tests"]["persona_stock"] = {"selected": p.name, "archetype": p.archetype}
    p2 = pe.select_persona("Debug this Python error")
    results["tests"]["persona_code"] = {"selected": p2.name, "archetype": p2.archetype}
except Exception as e:
    results["tests"]["persona"] = {"error": str(e)}

# Test Knowledge Harvester
try:
    from src.agent.intelligence.knowledge_harvester import KnowledgeHarvester
    h = KnowledgeHarvester()
    stats = h.store.get_stats()
    results["tests"]["knowledge_harvester"] = stats
except Exception as e:
    results["tests"]["knowledge_harvester"] = {"error": str(e)}

with open("audit_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print("AUDIT COMPLETE - see audit_results.json")
