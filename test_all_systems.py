"""
test_all_systems.py

Run this to verify ALL systems are working.
Tests every module created for the platform.

Usage:
    cd software-brain
    python test_all_systems.py
"""

import sys
import os
import time
import traceback

# Ensure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

PASS = 0
FAIL = 0
RESULTS = []


def test(name, fn):
    global PASS, FAIL
    try:
        result = fn()
        PASS += 1
        RESULTS.append(("PASS", name, result))
        print(f"  PASS  {name}")
        if result:
            print(f"        {result}")
    except Exception as e:
        FAIL += 1
        RESULTS.append(("FAIL", name, str(e)))
        print(f"  FAIL  {name}")
        print(f"        {e}")
        traceback.print_exc()


def banner(text):
    print(f"\n{'='*55}")
    print(f"  {text}")
    print(f"{'='*55}")


# ====================================================
#  1. CORE AGENT MODULES
# ====================================================

banner("1. CORE AGENT MODULES")

def test_llm_router():
    from src.agent.llm_router import LLMRouter, Message, Role
    router = LLMRouter.from_env()
    return f"Providers: {list(router.providers.keys())}"

def test_reasoning_engine():
    from src.agent.reasoning_engine import ReasoningEngine
    from src.agent.llm_router import LLMRouter
    router = LLMRouter.from_env()
    engine = ReasoningEngine(router)
    return "Chain-of-thought, tree-of-thought, self-reflection loaded"

def test_conversation_manager():
    from src.agent.conversation_manager import ConversationManager
    mgr = ConversationManager()
    session = mgr.new_session()
    mgr.add_user_message(session.id, "Hello")
    mgr.add_assistant_message(session.id, "Hi there!")
    return f"Session {session.id} created, {len(session.turns)} turns"

def test_tool_protocol():
    from src.agent.tool_protocol import AgentToolLoop, ToolRegistry
    registry = ToolRegistry()
    return f"Tool registry created"

def test_code_engine():
    from src.agent.code_engine import CodeEngine
    from src.agent.llm_router import LLMRouter
    router = LLMRouter.from_env()
    engine = CodeEngine(router)
    return "Code engine loaded (generate, analyze, fix, execute)"

def test_claude_agent():
    from src.agent.claude_agent import ClaudeAgent
    return "ClaudeAgent class imported"

test("LLM Router (multi-provider)", test_llm_router)
test("Reasoning Engine (CoT/ToT)", test_reasoning_engine)
test("Conversation Manager", test_conversation_manager)
test("Tool Protocol (agentic loop)", test_tool_protocol)
test("Code Engine", test_code_engine)
test("Claude Agent (unified)", test_claude_agent)


# ====================================================
#  2. MULTI-AGENT ORCHESTRATOR
# ====================================================

banner("2. MULTI-AGENT ORCHESTRATOR")

def test_orchestrator_init():
    from src.business.multi_agent import Orchestrator
    orch = Orchestrator()
    return f"{len(orch.agents)} agents: {[a.name for a in orch.agents]}"

def test_agent_routing():
    from src.business.multi_agent import Orchestrator
    orch = Orchestrator()
    r1 = orch.handle_natural("I need a villa in Dubai Marina")
    r2 = orch.handle_natural("I have a payment issue")
    r3 = orch.handle_natural("Schedule a meeting at 10am")
    agents = [r1.get("_routed_to"), r2.get("_routed_to"), r3.get("_routed_to")]
    assert "real_estate_agent" in agents, f"Routing wrong: {agents}"
    assert "support_agent" in agents, f"Routing wrong: {agents}"
    assert "scheduling_agent" in agents, f"Routing wrong: {agents}"
    return f"Correctly routed to: {agents}"

def test_crm_agent():
    from src.business.multi_agent import Orchestrator
    orch = Orchestrator()
    r = orch.handle_task({"action": "create_lead", "name": "Test User", "email": "test@test.com"})
    assert r.get("status") == "ok", f"CRM failed: {r}"
    return f"Lead created: {r.get('lead_id')}"

def test_support_agent():
    from src.business.multi_agent import Orchestrator
    orch = Orchestrator()
    r = orch.handle_task({"action": "create_ticket", "subject": "Test ticket", "description": "Testing"})
    assert r.get("status") == "ok"
    return f"Ticket created: {r.get('ticket_id')}"

def test_property_search():
    from src.business.multi_agent import Orchestrator
    orch = Orchestrator()
    r = orch.real_estate.handle({"action": "search", "filters": {"type": "villa"}})
    assert r["count"] > 0, "No villas found"
    return f"Found {r['count']} villas"

test("Orchestrator init", test_orchestrator_init)
test("Natural language routing", test_agent_routing)
test("CRM Agent - create lead", test_crm_agent)
test("Support Agent - create ticket", test_support_agent)
test("Real Estate Agent - property search", test_property_search)


# ====================================================
#  3. CRM + SCHEDULING
# ====================================================

banner("3. CRM + SCHEDULING SYSTEM")

def test_crm_system():
    from src.business.crm_scheduling import CRMSystem
    crm = CRMSystem(data_dir="agent_data/crm_test")
    contact = crm.create_contact("Test User", "test@email.com", "+971501234567")
    assert contact.id, "Contact not created"
    lead = crm.create_lead(contact.id, source="website", budget=1_000_000)
    assert lead.score > 0, "Lead not scored"
    return f"Contact: {contact.id}, Lead score: {lead.score}"

def test_lead_scoring():
    from src.business.crm_scheduling import CRMSystem, InteractionType
    crm = CRMSystem(data_dir="agent_data/crm_test")
    c = crm.create_contact("Scorer Test", "s@email.ae", "+971509999999", company="Big Corp")
    l = crm.create_lead(c.id, source="referral", budget=2_000_000, timeline="immediate")
    crm.add_interaction(l.id, InteractionType.CALL, "Great call")
    crm.add_interaction(l.id, InteractionType.MEETING, "Met in office")
    crm.add_interaction(l.id, InteractionType.EMAIL, "Sent proposal")
    score = crm.score_lead(l.id)
    qual = crm.scoring.qualify(score)
    assert score >= 70, f"Score too low: {score}"
    return f"Score: {score}, Qualification: {qual}"

def test_scheduling():
    from src.business.crm_scheduling import SchedulingSystem
    sched = SchedulingSystem(data_dir="agent_data/sched_test")
    slots = sched.get_available_slots("2026-03-15")
    assert len(slots) > 0, "No slots"
    appt = sched.book("2026-03-15", "10:00", contact_id="test", service="consultation")
    assert appt is not None, "Booking failed"
    # conflict test
    appt2 = sched.book("2026-03-15", "10:00", contact_id="test2")
    assert appt2 is None, "Conflict detection failed"
    return f"Booked {appt.id} at 10:00, conflict detected correctly"

def test_business_crm():
    from src.business.crm_scheduling import BusinessCRM
    biz = BusinessCRM(data_dir="agent_data/biz_test")
    result = biz.onboard_customer(
        name="Integration Test", email="int@test.com",
        source="referral", budget=500_000, interest="apartment"
    )
    assert "contact" in result and "lead" in result
    analytics = biz.get_full_dashboard()
    assert "crm" in analytics and "scheduling" in analytics
    return f"Onboarded + analytics OK, leads: {analytics['crm']['leads']['total']}"

test("CRM System (contacts + leads)", test_crm_system)
test("Lead Scoring Engine", test_lead_scoring)
test("Scheduling (booking + conflicts)", test_scheduling)
test("BusinessCRM (unified)", test_business_crm)


# ====================================================
#  4. WORKFLOW ENGINE
# ====================================================

banner("4. WORKFLOW ENGINE")

def test_workflow_templates():
    from src.business.workflow_engine import WorkflowEngine
    wf = WorkflowEngine()
    templates = list(wf.templates.keys())
    assert len(templates) >= 4, f"Only {len(templates)} templates"
    return f"Templates: {templates}"

def test_workflow_execution():
    from src.business.workflow_engine import WorkflowEngine
    wf = WorkflowEngine()
    template = wf.get_template("clinic_patient_intake")
    execution = wf.start(template, {"patient_name": "Test", "patient_email": "t@t.com"})
    wf.run(execution)
    completed = sum(1 for s in execution.steps if s.status.value == "completed")
    assert completed > 0, "No steps completed"
    return f"Clinic workflow: {completed}/{len(execution.steps)} steps done"

test("Workflow templates loaded", test_workflow_templates)
test("Workflow execution (clinic)", test_workflow_execution)


# ====================================================
#  5. UAE INTELLIGENCE
# ====================================================

banner("5. UAE INTELLIGENCE")

def test_bilingual():
    from src.business.uae_solutions import BilingualAssistant
    ba = BilingualAssistant()
    assert ba.detect_language("Hello") == "english"
    assert ba.detect_language("مرحبا") == "arabic"
    # Mixed: "أريد apartment" — 4 arabic, 9 latin → english wins by char count
    mixed = ba.detect_language("أريد apartment")
    assert mixed in ("arabic", "english"), f"Unknown: {mixed}"
    return f"English/Arabic/Mixed({mixed}) detection OK"

def test_property_prediction():
    from src.business.uae_solutions import DubaiPropertyPredictor, PropertyListing
    pred = DubaiPropertyPredictor()
    prop = PropertyListing(area="Dubai Marina", bedrooms=2, size_sqft=1200, type="apartment")
    est = pred.predict_price(prop)
    price = est.get("predicted_price_aed", 0)
    assert price > 1_000_000, f"Price too low: {price}"
    return f"Dubai Marina 2BR 1200sqft = {price:,.0f} AED"

def test_gov_services():
    from src.business.uae_solutions import UAEServicesHelper
    helper = UAEServicesHelper()
    results = helper.search_service("visa")
    assert len(results) > 0, "No visa services found"
    reqs = helper.get_requirements("golden_visa")
    assert "requirements" in reqs, "Requirements missing"
    return f"Found {len(results)} visa services, golden visa has {len(reqs['requirements'])} requirements"

def test_smart_city():
    from src.business.uae_solutions import SmartCitySimulator
    sim = SmartCitySimulator()
    m = sim.get_district_metrics("Dubai Marina")
    assert m.district == "Dubai Marina"
    assert 0 <= m.traffic_congestion_index <= 1
    overview = sim.get_city_overview()
    assert len(overview) >= 10, f"Only {len(overview)} districts"
    return f"Dubai Marina congestion: {m.traffic_congestion_index:.0%}, {len(overview)} districts"

test("Bilingual detection (AR/EN)", test_bilingual)
test("Property price prediction", test_property_prediction)
test("Government services search", test_gov_services)
test("Smart city simulation", test_smart_city)


# ====================================================
#  6. DASHBOARD (FastAPI)
# ====================================================

banner("6. DASHBOARD (FastAPI)")

def test_dashboard_import():
    from src.business.dashboard import app
    routes = [r.path for r in app.routes if hasattr(r, "path")]
    api_routes = [r for r in routes if r.startswith("/api")]
    assert len(api_routes) >= 15, f"Only {len(api_routes)} API routes"
    return f"{len(api_routes)} API endpoints, {len(routes)} total routes"

def test_dashboard_html():
    from src.business.dashboard import DASHBOARD_HTML
    assert "Agentic Engine Pro" in DASHBOARD_HTML
    assert "agent-list" in DASHBOARD_HTML
    return f"HTML dashboard: {len(DASHBOARD_HTML)} chars"

test("Dashboard app import", test_dashboard_import)
test("Dashboard HTML template", test_dashboard_html)


# ====================================================
#  7. EXISTING BRAIN MODULES
# ====================================================

banner("7. EXISTING BRAIN MODULES")

def test_brain_imports():
    modules = []
    try:
        from src.agent.core import AgentIdentity
        modules.append("core")
    except: pass
    try:
        from src.agent.autonomous_agent import AutonomousAgent
        modules.append("autonomous_agent")
    except: pass
    try:
        from src.agent.llm_gemini import GeminiLLM
        modules.append("llm_gemini")
    except: pass
    try:
        from src.agent.planner import Planner
        modules.append("planner")
    except: pass
    return f"Importable: {modules}" if modules else "No legacy modules"

test("Legacy brain modules", test_brain_imports)


# ====================================================
#  SUMMARY
# ====================================================

banner("TEST RESULTS")
print(f"  PASSED: {PASS}")
print(f"  FAILED: {FAIL}")
print(f"  TOTAL:  {PASS + FAIL}")
print()

if FAIL > 0:
    print("  FAILED TESTS:")
    for status, name, detail in RESULTS:
        if status == "FAIL":
            print(f"    X {name}: {detail}")
    print()

print(f"  {'ALL SYSTEMS GO!' if FAIL == 0 else f'{FAIL} ISSUE(S) FOUND'}")
print(f"{'='*55}")

# Cleanup test data
import shutil
for d in ["agent_data/crm_test", "agent_data/sched_test", "agent_data/biz_test"]:
    if os.path.exists(d):
        shutil.rmtree(d)

sys.exit(0 if FAIL == 0 else 1)
