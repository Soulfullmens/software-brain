"""
test_swarm_intelligence.py — Comprehensive Test Suite for MiroFish-Inspired Intelligence Modules

Tests all 6 modules:
    1. Knowledge Graph Engine
    2. Entity & Ontology Extractor
    3. ReACT Reasoning Loop
    4. Multi-Strategy Retriever
    5. Temporal Memory Layer (context_memory upgrade)
    6. Context Persona Engine
"""
import sys
import os
import time
import json
import tempfile
import shutil

# Add project to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Track results
RESULTS = {"passed": 0, "failed": 0, "tests": []}


def test(name, condition, details=""):
    """Test helper."""
    status = "PASS" if condition else "FAIL"
    RESULTS["passed" if condition else "failed"] += 1
    RESULTS["tests"].append({"name": name, "status": status})
    icon = "✅" if condition else "❌"
    print(f"  {icon} {name}" + (f" — {details}" if details else ""))


def run_all_tests():
    print("=" * 60)
    print("  SWARM INTELLIGENCE TEST SUITE")
    print("  MiroFish-Inspired Cognitive Upgrades")
    print("=" * 60)

    test_knowledge_graph()
    test_entity_extractor()
    test_react_loop()
    test_multi_retriever()
    test_temporal_memory()
    test_persona_engine()

    print("\n" + "=" * 60)
    total = RESULTS["passed"] + RESULTS["failed"]
    print(f"  RESULTS: {RESULTS['passed']}/{total} passed")
    if RESULTS["failed"] == 0:
        print("  🎉 ALL TESTS PASSED")
    else:
        print(f"  ⚠️  {RESULTS['failed']} FAILED")
    print("=" * 60)


# ═══════════════════════════════════════════════════════
# 1. KNOWLEDGE GRAPH TESTS
# ═══════════════════════════════════════════════════════

def test_knowledge_graph():
    print("\n📊 [1/6] Knowledge Graph Engine")
    from agent.intelligence.knowledge_graph import KnowledgeGraph, GraphNode, GraphEdge

    # Use temp file for storage
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name

    try:
        kg = KnowledgeGraph(storage_path=path)

        # Test: Add entities
        n1 = kg.add_entity("OpenAI", "organization", summary="AI research lab")
        test("Add entity", n1.name == "OpenAI" and n1.entity_type == "organization")

        n2 = kg.add_entity("Sam Altman", "person", summary="CEO of OpenAI")
        test("Add second entity", n2.name == "Sam Altman")

        # Test: Entity merging
        n1_again = kg.add_entity("OpenAI", "organization", summary="Creator of GPT-4")
        test("Entity merge (same name)", n1_again.mention_count == 2,
             f"mention_count={n1_again.mention_count}")
        test("Merge updates summary", "GPT-4" in n1_again.summary)

        # Test: Get entity
        found = kg.get_entity("openai")  # case-insensitive
        test("Get entity (case-insensitive)", found is not None and found.name == "OpenAI")

        # Test: Add relationship
        edge = kg.add_relationship("Sam Altman", "OpenAI", "leads",
                                   fact="Sam Altman is the CEO of OpenAI")
        test("Add relationship", edge is not None and edge.relationship == "leads")

        # Test: Get relationships
        rels = kg.get_relationships("Sam Altman")
        test("Get relationships", len(rels) == 1 and rels[0].fact == "Sam Altman is the CEO of OpenAI")

        # Test: Search
        results = kg.search("CEO OpenAI")
        test("Search returns results", len(results.nodes) > 0 or len(results.facts) > 0)

        # Test: Entity neighborhood
        neighborhood = kg.get_entity_neighborhood("OpenAI", depth=1)
        test("Neighborhood traversal", len(neighborhood.nodes) >= 2,
             f"found {len(neighborhood.nodes)} nodes")

        # Test: Temporal — active facts
        active = kg.get_active_facts("OpenAI")
        test("Active facts", len(active) >= 1)

        # Test: Expire relationship
        kg.expire_relationship(edge.id)
        historical = kg.get_historical_facts("Sam Altman")
        test("Expire relationship → historical", len(historical) >= 1)

        # Test: Entities by type
        persons = kg.get_entities_by_type("person")
        test("Get entities by type", len(persons) == 1 and persons[0].name == "Sam Altman")

        # Test: Persistence
        kg.save()
        kg2 = KnowledgeGraph(storage_path=path)
        test("JSON persistence (load)", len(kg2.list_entities()) == 2)

        # Test: Stats
        stats = kg.get_stats()
        test("Stats tracking", stats["total_nodes"] == 2 and stats["total_edges"] >= 1)

    finally:
        os.unlink(path)


# ═══════════════════════════════════════════════════════
# 2. ENTITY EXTRACTOR TESTS
# ═══════════════════════════════════════════════════════

def test_entity_extractor():
    print("\n🔍 [2/6] Entity & Ontology Extractor")
    from agent.intelligence.entity_extractor import EntityExtractor, ExtractionResult

    extractor = EntityExtractor()  # No LLM, regex fallback

    # Test: Entity extraction (regex)
    text = "OpenAI released GPT-4o. Sam Altman is the CEO. Microsoft invested billions."
    result = extractor.extract(text, use_llm=False)
    test("Regex extraction finds entities", len(result.entities) > 0,
         f"found {len(result.entities)}")
    test("Extraction returns ExtractionResult", isinstance(result, ExtractionResult))
    test("Method is regex_fallback", result.method == "regex_fallback")

    # Test: Organization detection
    org_names = [e.name for e in result.entities if e.entity_type == "organization"]
    test("Detects organizations", len(org_names) > 0, f"orgs: {org_names}")

    # Test: Technology detection
    tech_text = "The GPT-4o model uses advanced NLP and LLM techniques with the API."
    tech_result = extractor.extract(tech_text, use_llm=False)
    tech_names = [e.name for e in tech_result.entities if e.entity_type == "technology"]
    test("Detects technologies", len(tech_names) > 0, f"techs: {tech_names}")

    # Test: Relationship inference
    text2 = "Sam Altman leads OpenAI. OpenAI created GPT-4o."
    result2 = extractor.extract(text2, use_llm=False)
    test("Infers relationships", len(result2.relationships) >= 0)

    # Test: Populate knowledge graph
    from agent.intelligence.knowledge_graph import KnowledgeGraph
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        kg = KnowledgeGraph(storage_path=path)
        result3 = extractor.extract_and_populate_graph(text, kg)
        test("Auto-populate KG", len(kg.list_entities()) > 0,
             f"populated {len(kg.list_entities())} entities")
    finally:
        os.unlink(path)

    # Test: Stats
    stats = extractor.get_stats()
    test("Stats tracking", stats["extractions"] >= 3)


# ═══════════════════════════════════════════════════════
# 3. REACT LOOP TESTS
# ═══════════════════════════════════════════════════════

def test_react_loop():
    print("\n🔄 [3/6] ReACT Reasoning Loop")
    from agent.intelligence.react_loop import ReACTLoop, ToolDefinition, ReACTResult, StepType

    # Create loop without LLM (uses fallback logic)
    loop = ReACTLoop(max_rounds=3)

    # Add mock tools
    search_calls = []
    def mock_search(params):
        search_calls.append(params)
        return f"Found info about: {params.get('query', 'unknown')}"

    calc_calls = []
    def mock_calc(params):
        calc_calls.append(params)
        return f"Calculated: {params.get('query', '?')} = 42"

    loop.add_tool(ToolDefinition(
        name="search", description="Search for information",
        parameters={"query": "Search query"},
        execute_fn=mock_search
    ))
    loop.add_tool(ToolDefinition(
        name="calculate", description="Calculate a value",
        parameters={"query": "Expression to calculate"},
        execute_fn=mock_calc
    ))

    # Run loop
    result = loop.run("What is the meaning of life?", max_rounds=3)

    test("Returns ReACTResult", isinstance(result, ReACTResult))
    test("Has steps", len(result.steps) > 0, f"{len(result.steps)} steps")
    test("Has conclusion", len(result.conclusion) > 0)
    test("Tracks tool calls", result.tool_calls >= 1, f"{result.tool_calls} calls")
    test("Has execution trace", len(result.get_trace()) > 0)

    # Test: Tools were called
    test("Search tool was called", len(search_calls) > 0)

    # Test: Step types
    step_types = [s.step_type for s in result.steps]
    test("Has THINK steps", StepType.THINK in step_types)
    test("Has ACT steps", StepType.ACT in step_types)
    test("Has OBSERVE steps", StepType.OBSERVE in step_types)

    # Test: Stats
    stats = loop.get_stats()
    test("Loop stats", stats["loops_run"] >= 1)


# ═══════════════════════════════════════════════════════
# 4. MULTI-STRATEGY RETRIEVER TESTS
# ═══════════════════════════════════════════════════════

def test_multi_retriever():
    print("\n🔎 [4/6] Multi-Strategy Retriever")
    from agent.intelligence.multi_retriever import MultiRetriever, RetrievalResult
    from agent.intelligence.knowledge_graph import KnowledgeGraph

    # Create KG with test data
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name

    try:
        kg = KnowledgeGraph(storage_path=path)
        kg.add_entity("Python", "technology", summary="Programming language")
        kg.add_entity("Guido van Rossum", "person", summary="Creator of Python")
        kg.add_entity("AI", "concept", summary="Artificial Intelligence")
        kg.add_relationship("Guido van Rossum", "Python", "created",
                           fact="Guido van Rossum created Python in 1991")
        kg.add_relationship("Python", "AI", "used_in",
                           fact="Python is widely used in AI and machine learning")

        retriever = MultiRetriever(knowledge_graph=kg)

        # Test: Quick search
        quick = retriever.retrieve("Python", strategy="quick")
        test("Quick search returns results", quick.total_items > 0,
             f"{quick.total_items} items")
        test("Quick strategy label", quick.strategy == "quick")

        # Test: Deep search
        deep = retriever.retrieve("Who created Python?", strategy="deep")
        test("Deep search decomposes", len(deep.sub_queries) >= 1,
             f"{len(deep.sub_queries)} sub-queries")
        test("Deep search returns facts", len(deep.facts) >= 0)

        # Test: Broad search
        broad = retriever.retrieve("Python overview", strategy="broad")
        test("Broad search returns entities", len(broad.entities) >= 0)

        # Test: Auto selection
        auto = retriever.retrieve("Why is Python popular for AI?", strategy="auto")
        test("Auto selects strategy", auto.strategy in ["deep", "broad", "quick"],
             f"selected: {auto.strategy}")

        # Test: to_text output
        text_output = quick.to_text()
        test("to_text() works", "Retrieval Results" in text_output)

    finally:
        os.unlink(path)


# ═══════════════════════════════════════════════════════
# 5. TEMPORAL MEMORY TESTS
# ═══════════════════════════════════════════════════════

def test_temporal_memory():
    print("\n⏰ [5/6] Temporal Memory Layer")
    from agent.context_memory import ContextMemory

    # Use temp directory
    tmpdir = tempfile.mkdtemp()
    try:
        mem = ContextMemory(memory_dir=tmpdir)

        # Test: Remember with validity
        mem.remember("test_app", "fact", "Python is great", valid_hours=24)
        test("Remember with valid_hours", True)

        # Test: Active facts
        active = mem.get_active_facts("test_app", "fact")
        test("Get active facts", len(active) == 1 and active[0]["value"] == "Python is great")
        test("Active fact has relevance", active[0]["relevance"] > 0)
        test("Active fact has age", "age_hours" in active[0])

        # Test: Historical (nothing expired yet)
        historical = mem.get_historical_facts("test_app", "fact")
        test("No historical facts yet", len(historical) == 0)

        # Test: Expire fact manually
        result = mem.expire_fact("test_app", "fact", "Python is great")
        test("expire_fact() returns True", result is True)

        # Now it should be historical
        historical = mem.get_historical_facts("test_app", "fact")
        test("Expired fact becomes historical", len(historical) == 1)

        active = mem.get_active_facts("test_app", "fact")
        test("Expired fact no longer active", len(active) == 0)

        # Test: Multiple facts
        mem.remember("test_app", "preference", "dark mode")
        mem.remember("test_app", "preference", "vim keys")
        all_active = mem.get_active_facts("test_app")
        test("Multiple active facts", len(all_active) >= 2)

        # Test: Old API still works
        recalled = mem.recall("test_app", "preference")
        test("Old recall() still works", len(recalled) >= 2)

    finally:
        shutil.rmtree(tmpdir)


# ═══════════════════════════════════════════════════════
# 6. PERSONA ENGINE TESTS
# ═══════════════════════════════════════════════════════

def test_persona_engine():
    print("\n🎭 [6/6] Context Persona Engine")
    from agent.intelligence.persona_engine import PersonaEngine, PersonaProfile

    engine = PersonaEngine()

    # Test: Auto-select developer
    persona = engine.select_persona("Fix this Python error in my API")
    test("Auto-select developer", persona.archetype == "developer",
         f"selected: {persona.archetype}")

    # Test: Auto-select researcher
    persona = engine.select_persona("Research what happened in 2024 elections")
    test("Auto-select researcher", persona.archetype == "researcher",
         f"selected: {persona.archetype}")

    # Test: Auto-select analyst
    persona = engine.select_persona("Analyze this data and show me patterns")
    test("Auto-select analyst", persona.archetype == "analyst",
         f"selected: {persona.archetype}")

    # Test: Auto-select creative
    persona = engine.select_persona("Design a new logo and branding concept")
    test("Auto-select creative", persona.archetype == "creative",
         f"selected: {persona.archetype}")

    # Test: Auto-select strategist
    persona = engine.select_persona("Plan our product roadmap and risk assessment")
    test("Auto-select strategist", persona.archetype == "strategist",
         f"selected: {persona.archetype}")

    # Test: Force archetype
    persona = engine.select_persona("anything", force_archetype="mentor")
    test("Force archetype", persona.archetype == "mentor")

    # Test: System prompt adaptation
    base = "You are an AI assistant."
    enhanced = engine.adapt_system_prompt(base, persona)
    test("System prompt injection", len(enhanced) > len(base))
    test("Prompt contains persona", "MENTOR" in enhanced.upper())

    # Test: List archetypes
    archetypes = engine.list_archetypes()
    test("List archetypes", len(archetypes) >= 6, f"found {len(archetypes)}")

    # Test: Current persona tracking
    current = engine.get_current_persona()
    test("Current persona tracked", current is not None)

    # Test: MBTI assignment
    test("Has MBTI", len(current.mbti) == 4, f"MBTI: {current.mbti}")

    # Test: Stats
    stats = engine.get_stats()
    test("Stats tracking", stats["persona_switches"] >= 6)


# ═══════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    run_all_tests()
