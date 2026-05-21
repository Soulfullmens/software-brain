"""Diagnostic: identify the 4 failing tests."""
import sys, os, time, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

fails = []

# --- KG TESTS ---
from agent.intelligence.knowledge_graph import KnowledgeGraph
with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
    f.write("{}")
    path = f.name
try:
    kg = KnowledgeGraph(storage_path=path)
    n1 = kg.add_entity("OpenAI", "organization", summary="AI research lab")
    n2 = kg.add_entity("Sam Altman", "person", summary="CEO of OpenAI")
    n1b = kg.add_entity("OpenAI", "organization", summary="Creator of GPT-4")
    e = kg.add_relationship("Sam Altman", "OpenAI", "leads", fact="Sam Altman is the CEO of OpenAI")
    
    r = kg.search("CEO OpenAI")
    if not (len(r.nodes) > 0 or len(r.facts) > 0):
        fails.append(f"KG search: nodes={len(r.nodes)}, facts={len(r.facts)}")
    
    nb = kg.get_entity_neighborhood("OpenAI", depth=1)
    if not (len(nb.nodes) >= 2):
        fails.append(f"KG neighborhood: nodes={len(nb.nodes)}")
    
    kg.save()
    kg2 = KnowledgeGraph(storage_path=path)
    if not (len(kg2.list_entities()) == 2):
        fails.append(f"KG persistence: entities={len(kg2.list_entities())}")
finally:
    os.unlink(path)

# --- ENTITY EXTRACTOR ---
from agent.intelligence.entity_extractor import EntityExtractor
ex = EntityExtractor()
text1 = "OpenAI released GPT-4o. Sam Altman is the CEO. Microsoft invested billions."
r1 = ex.extract(text1, use_llm=False)
org_names = [e.name for e in r1.entities if e.entity_type == "organization"]
if not org_names:
    fails.append(f"Extractor orgs: {[e.name + '(' + e.entity_type + ')' for e in r1.entities]}")

tech_text = "The GPT-4o model uses advanced NLP and LLM techniques with the API."
r2 = ex.extract(tech_text, use_llm=False)
tech_names = [e.name for e in r2.entities if e.entity_type == "technology"]
if not tech_names:
    fails.append(f"Extractor techs: {[e.name + '(' + e.entity_type + ')' for e in r2.entities]}")

# --- REACT ---
from agent.intelligence.react_loop import ReACTLoop, ToolDefinition, StepType
loop = ReACTLoop(max_rounds=3)
loop.add_tool(ToolDefinition(name="search", description="Search", parameters={"query": "q"}, execute_fn=lambda p: "found"))
loop.add_tool(ToolDefinition(name="calc", description="Calc", parameters={"query": "q"}, execute_fn=lambda p: "42"))
res = loop.run("test", max_rounds=3)
types = [s.step_type for s in res.steps]
if StepType.THINK not in types:
    fails.append(f"ReACT no THINK: {types}")
if StepType.ACT not in types:
    fails.append(f"ReACT no ACT: {types}")
if StepType.OBSERVE not in types:
    fails.append(f"ReACT no OBSERVE: {types}")

# --- RETRIEVER ---
from agent.intelligence.multi_retriever import MultiRetriever
with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
    f.write("{}")
    path2 = f.name
try:
    kg3 = KnowledgeGraph(storage_path=path2)
    kg3.add_entity("Python", "technology", summary="Programming language")
    kg3.add_entity("Guido", "person", summary="Creator")
    kg3.add_relationship("Guido", "Python", "created", fact="Guido created Python")
    ret = MultiRetriever(knowledge_graph=kg3)
    q = ret.retrieve("Python", strategy="quick")
    if not (q.total_items > 0):
        fails.append(f"Quick search: items={q.total_items}")
finally:
    os.unlink(path2)

# --- TEMPORAL MEMORY ---
from agent.context_memory import ContextMemory
tmpdir = tempfile.mkdtemp()
try:
    mem = ContextMemory(memory_dir=tmpdir)
    mem.remember("app", "fact", "Python is great", valid_hours=24)
    active = mem.get_active_facts("app", "fact")
    if not (len(active) == 1):
        fails.append(f"Temporal active: {len(active)}")
    mem.expire_fact("app", "fact", "Python is great")
    hist = mem.get_historical_facts("app", "fact")
    if not (len(hist) == 1):
        fails.append(f"Temporal historical: {len(hist)}")
finally:
    shutil.rmtree(tmpdir)

# --- PERSONA ---
from agent.intelligence.persona_engine import PersonaEngine
pe = PersonaEngine()
p1 = pe.select_persona("Fix Python error"); 
if p1.archetype != "developer": fails.append(f"Persona dev: {p1.archetype}")
p2 = pe.select_persona("Research elections"); 
if p2.archetype != "researcher": fails.append(f"Persona res: {p2.archetype}")
p3 = pe.select_persona("Analyze data patterns"); 
if p3.archetype != "analyst": fails.append(f"Persona ana: {p3.archetype}")

# OUTPUT
print(f"FAILURES: {len(fails)}")
for f in fails:
    print(f"  - {f}")
if not fails:
    print("ALL KEY TESTS PASS")
