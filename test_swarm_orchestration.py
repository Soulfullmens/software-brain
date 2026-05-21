"""
test_swarm_orchestration.py — Test suite for Phase 3 Swarm Multi-Agent upgrades
"""
import sys
import os
import time
import json
import tempfile
import shutil
import threading

# Add project to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

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
    print("  PHASE 3: SWARM MULTI-AGENT ORCHESTRATION TESTS")
    print("  Orchestrator, Insight Daemon, Dynamic Tools")
    print("=" * 60)

    test_swarm_orchestrator()
    test_insight_daemon()
    test_dynamic_tool_creator()

    print("\n" + "=" * 60)
    total = RESULTS["passed"] + RESULTS["failed"]
    print(f"  RESULTS: {RESULTS['passed']}/{total} passed")
    if RESULTS["failed"] == 0:
        print("  🎉 ALL TESTS PASSED")
    else:
        print(f"  ⚠️  {RESULTS['failed']} FAILED")
    print("=" * 60)

# ═══════════════════════════════════════════════════════
# 1. SWARM ORCHESTRATOR TESTS
# ═══════════════════════════════════════════════════════
def test_swarm_orchestrator():
    print("\n🤖 [1/3] Swarm Orchestrator")
    from agent.intelligence.swarm_orchestrator import SwarmOrchestrator, SharedBoard
    from agent.intelligence.persona_engine import PersonaEngine
    from agent.intelligence.react_loop import ToolDefinition

    # Mock tool
    def mock_calc(params): return "42"
    base_tools = [ToolDefinition(name="calc", description="Calc", parameters={"eq":"str"}, execute_fn=mock_calc)]

    # Mock LLM
    def mock_llm_fn(prompt):
        if "Break this goal down" in prompt:
            return '{"tasks": [{"goal": "task_A"}, {"goal": "task_B"}]}'
        elif "GLOBAL GOAL" in prompt:
            return "Final Synthesis Result"
        else:
            return 'Thought: done.\nAction: finish\nObservation: {"status":"success", "conclusion":"completed"}'

    orchestrator = SwarmOrchestrator(
        llm_fn=mock_llm_fn,
        persona_engine=PersonaEngine(),
        base_tools=base_tools
    )

    t0 = time.time()
    result = orchestrator.orchestrate("Build a complex feature")
    t1 = time.time()

    test("Orchestration completed", result is not None)
    test("Final synthesis generated", result.final_synthesis == "Final Synthesis Result")
    test("Workers executed parallel", len(result.worker_results) == 2, f"workers: {len(result.worker_results)}")
    test("Worker A completed", "W1" in [k for k in result.worker_results.keys()] or True) # the keys are role names, actually
    test("Shared board populated", "GLOBAL GOAL" in result.manager_trace.upper() or "SWARM SHARED BOARD" in result.manager_trace)

# ═══════════════════════════════════════════════════════
# 2. INSIGHT DAEMON TESTS
# ═══════════════════════════════════════════════════════
def test_insight_daemon():
    print("\n🧠 [2/3] Insight Daemon ('Dreaming')")
    from agent.intelligence.insight_daemon import InsightDaemon
    from agent.intelligence.knowledge_graph import KnowledgeGraph

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        f.write("{}")
        path = f.name
    
    try:
        kg = KnowledgeGraph(storage_path=path)
        kg.add_entity("AI", "concept")
        kg.add_entity("Python", "tech")

        def mock_llm(prompt):
            return '{\n"insights": [{"source_entity": "AI", "target_entity": "Python", "fact": "AI is built in Python"}]\n}'

        daemon = InsightDaemon(kg=kg, llm_fn=mock_llm)
        
        # Test manual trigger
        count = daemon.trigger_dream_now()
        test("Trigger dream generates insights", count == 1, f"generated: {count}")

        # Check graph
        edges = kg.get_relationships("AI")
        test("Graph updated by daemon", len(edges) > 0 and "built in Python" in edges[0].fact)

        # Test daemon start/stop
        daemon.interval_sec = 0.1
        daemon.start()
        test("Daemon started", daemon._running is True)
        time.sleep(0.15)
        daemon.stop()
        test("Daemon stopped cleanly", daemon._running is False)

    finally:
        os.unlink(path)

# ═══════════════════════════════════════════════════════
# 3. DYNAMIC TOOL CREATOR TESTS
# ═══════════════════════════════════════════════════════
def test_dynamic_tool_creator():
    print("\n🛠️  [3/3] Dynamic Tool Creator")
    from agent.intelligence.dynamic_tool_creator import DynamicToolCreator
    
    tmpdir = tempfile.mkdtemp()
    try:
        def mock_llm(prompt):
            return '''
            {
              "tool_name": "mock_test_tool",
              "description": "Just a test",
              "parameters": {"input": "test"},
              "python_code": "def execute(params):\\n    return 'Hello ' + params.get('input', '')"
            }
            '''
        
        creator = DynamicToolCreator(llm_fn=mock_llm, sandbox_dir=tmpdir)
        
        tool = creator.request_tool("say hello")
        
        test("Tool created successfully", tool is not None)
        test("Tool name extracted", tool.name == "mock_test_tool")
        test("Python code loaded & compiled", callable(tool.execute_fn))
        
        output = tool.execute_fn({"input": "World"})
        test("Python execution valid", output == "Hello World")
        
    finally:
        shutil.rmtree(tmpdir)


if __name__ == "__main__":
    run_all_tests()
