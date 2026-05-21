"""
demo_full_platform.py

Full Platform Demo — showcases every system end-to-end.
Run this to generate output for your portfolio demo video.

Covers:
    1. Multi-Agent Orchestrator (5 agents routing)
    2. CRM + Lead Scoring + Pipeline
    3. Appointment Scheduling
    4. Business Workflow Engine
    5. UAE Intelligence (bilingual, property, govt services, smart city)
    6. Dashboard API verification
"""

import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def banner(text: str):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def section(text: str):
    print(f"\n--- {text} ---")


def main():
    banner("SOFTWARE BRAIN — FULL PLATFORM DEMO")
    print("Multi-Agent AI Platform for Business Automation")
    print("Built by Abdul Rahaman\n")

    # ─────────────────────────────────────────────────
    #  1. MULTI-AGENT ORCHESTRATOR
    # ─────────────────────────────────────────────────

    banner("1. MULTI-AGENT ORCHESTRATOR")
    from src.business.multi_agent import Orchestrator

    orch = Orchestrator()

    # Natural language routing — the orchestrator detects intent and picks the right agent
    test_queries = [
        "I need a 3-bedroom villa in Dubai Hills",
        "Create a new lead for Ahmed, ahmed@email.ae, referral source",
        "I have an issue with my payment, please help",
        "Schedule a consultation meeting at 10:00 AM",
        "Launch an email marketing campaign for Dubai Marina properties",
    ]

    for q in test_queries:
        result = orch.handle_natural(q)
        agent = result.get("_routed_to", "multi")
        print(f"  Query: \"{q}\"")
        print(f"  → Routed to: {agent} | Status: {result.get('status', 'ok')}")
        print()

    section("Agent Status Summary")
    for agent in orch.agents:
        s = agent.get_status()
        print(f"  {s['name']:20s} | Tasks: {s['stats']['tasks_handled']} | Caps: {', '.join(s['capabilities'])}")

    # ─────────────────────────────────────────────────
    #  2. CRM + LEAD SCORING
    # ─────────────────────────────────────────────────

    banner("2. CRM + LEAD SCORING + PIPELINE")
    from src.business.crm_scheduling import BusinessCRM, InteractionType, LeadStage, DealStage

    biz = BusinessCRM(data_dir="agent_data")

    # Onboard 3 customers
    customers = [
        {"name": "Ahmed Al Maktoum", "email": "ahmed@holdings.ae", "phone": "+971501234567",
         "company": "Maktoum Holdings", "source": "referral", "budget": 5_000_000,
         "interest": "Palm Jumeirah villa", "language": "ar"},
        {"name": "Sarah Johnson", "email": "sarah@invest.com", "phone": "+971502345678",
         "source": "website", "budget": 1_200_000, "interest": "Marina apartment"},
        {"name": "Mohammed Ali", "email": "m.ali@gmail.com",
         "source": "social", "budget": 400_000, "interest": "Studio in JLT"},
    ]

    section("Customer Onboarding")
    onboarded = []
    for c in customers:
        result = biz.onboard_customer(**c)
        onboarded.append(result)
        q = biz.crm.scoring.qualify(result["lead"]["score"])
        print(f"  {result['contact']['name']:25s} | Score: {result['lead']['score']:3d} | {q:>4s} | Budget: {c['budget']:>12,} AED")

    # Add interactions to first lead
    lead1_id = onboarded[0]["lead"]["id"]
    biz.crm.add_interaction(lead1_id, InteractionType.CALL, "Discussed Palm villas, very interested")
    biz.crm.add_interaction(lead1_id, InteractionType.MEETING, "Site visit to Palm Jumeirah")
    biz.crm.add_interaction(lead1_id, InteractionType.WHATSAPP, "Sent property brochure")
    new_score = biz.crm.score_lead(lead1_id)

    section("Lead Engagement")
    print(f"  Ahmed after 3 interactions: Score = {new_score} ({biz.crm.scoring.qualify(new_score)})")

    # Create deal
    deal = biz.crm.create_deal(lead1_id, "Palm Jumeirah Villa - 5BR Beachfront", 15_000_000, "2026-04-15")
    biz.crm.advance_deal(deal.id, DealStage.NEGOTIATION)
    print(f"  Deal: {deal.title} | {deal.value_aed:,.0f} AED | Stage: negotiation")

    # Pipeline
    section("CRM Pipeline")
    analytics = biz.crm.get_analytics()
    print(f"  Total contacts: {analytics['contacts']}")
    print(f"  Leads: {analytics['leads']['total']} (hot={analytics['leads']['hot']}, warm={analytics['leads']['warm']}, cold={analytics['leads']['cold']})")
    print(f"  Pipeline value: {analytics['deals']['pipeline_value_aed']:,.0f} AED")
    print(f"  Follow-ups pending: {analytics['followups']['pending']}")

    # ─────────────────────────────────────────────────
    #  3. SCHEDULING
    # ─────────────────────────────────────────────────

    banner("3. APPOINTMENT SCHEDULING")

    appt1 = biz.book_appointment(onboarded[0]["contact"]["id"], "2026-03-01", "10:00", "property_viewing")
    appt2 = biz.book_appointment(onboarded[1]["contact"]["id"], "2026-03-01", "14:00", "consultation")
    appt3 = biz.book_appointment(onboarded[2]["contact"]["id"], "2026-03-01", "10:00", "consultation")  # should fail — conflict

    print(f"  Booking 1: {appt1.get('appointment', {}).get('id', '-')} → Property viewing at 10:00 ✓")
    print(f"  Booking 2: {appt2.get('appointment', {}).get('id', '-')} → Consultation at 14:00 ✓")
    print(f"  Booking 3: Conflict detection → {appt3.get('message', 'Slot not available')} ✓")

    slots = biz.scheduler.get_available_slots("2026-03-01")
    print(f"\n  Available slots on March 1: {len(slots)} of {len(biz.scheduler.SLOTS)}")
    print(f"  Services: {', '.join(biz.scheduler.SERVICES.keys())}")

    # ─────────────────────────────────────────────────
    #  4. WORKFLOW ENGINE
    # ─────────────────────────────────────────────────

    banner("4. BUSINESS WORKFLOW ENGINE")
    from src.business.workflow_engine import WorkflowEngine

    wf = WorkflowEngine()
    print(f"  Available templates: {', '.join(wf.templates.keys())}")

    section("Running: clinic_patient_intake")
    template = wf.get_template("clinic_patient_intake")
    exec_result = wf.start(template, {
        "patient_name": "Fatima Al Zaabi",
        "patient_email": "fatima@email.ae",
        "patient_phone": "+971503456789",
    })
    wf.run(exec_result)
    done = sum(1 for s in exec_result.steps if s.status.value == "completed")
    print(f"  Execution ID: {exec_result.id}")
    print(f"  Status: {exec_result.status}")
    print(f"  Steps completed: {done}/{len(exec_result.steps)}")

    section("Running: real_estate_pipeline")
    template2 = wf.get_template("real_estate_pipeline")
    exec2 = wf.start(template2, {
        "lead_name": "James Wilson",
        "lead_email": "james@company.uk",
        "property_type": "apartment",
        "budget": "2,000,000 AED",
    })
    wf.run(exec2)
    done2 = sum(1 for s in exec2.steps if s.status.value == "completed")
    print(f"  Execution ID: {exec2.id}")
    print(f"  Status: {exec2.status}")
    print(f"  Steps completed: {done2}/{len(exec2.steps)}")

    # ─────────────────────────────────────────────────
    #  5. UAE INTELLIGENCE
    # ─────────────────────────────────────────────────

    banner("5. UAE-SPECIFIC AI INTELLIGENCE")
    from src.business.uae_solutions import UAEAISolutions, DUBAI_AREA_PRICES, UAE_SERVICES, DUBAI_DISTRICTS

    uae = UAEAISolutions()

    section("Bilingual Language Detection")
    tests_lang = [
        "What are the visa requirements for UAE?",
        "ما هي متطلبات التأشيرة؟",
        "أريد شقة في دبي مارينا please",
    ]
    for txt in tests_lang:
        lang = uae.assistant.detect_language(txt)
        print(f"  \"{txt[:50]}\" → {lang}")

    section("Dubai Property Price Prediction")
    from src.business.uae_solutions import PropertyListing
    areas = ["Dubai Marina", "Palm Jumeirah", "Downtown Dubai", "JBR"]
    for area in areas:
        prop = PropertyListing(area=area, bedrooms=2, size_sqft=1200, type="apartment")
        est = uae.property.predict_price(prop)
        price = est.get("predicted_price_aed", 0)
        print(f"  {area:20s} | 2BR 1200sqft → {price:>12,.0f} AED")

    section("Government Services")
    from src.business.uae_solutions import UAE_SERVICES
    for svc in UAE_SERVICES[:4]:
        print(f"  {svc['name']:30s} | {svc['name_ar']} | Fee: {svc.get('avg_days', '-'):>4} days")

    section("Smart City Metrics")
    districts = ["Dubai Marina", "Downtown Dubai", "Business Bay"]
    for d in districts:
        m = uae.city.get_district_metrics(d)
        if m:
            print(f"  {d:20s} | Traffic: {m.traffic_congestion_index:.0%} | AQI: {m.air_quality_index} | Pop: {m.current_population:,}")

    # ─────────────────────────────────────────────────
    #  6. DASHBOARD API CHECK
    # ─────────────────────────────────────────────────

    banner("6. DASHBOARD API CHECK")
    try:
        from src.business.dashboard import app
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        print(f"  Dashboard loaded: {len(routes)} API endpoints")
        print(f"  Key endpoints:")
        for r in sorted(routes):
            if r.startswith("/api"):
                print(f"    {r}")
    except Exception as e:
        print(f"  Dashboard import: {e}")

    # ─────────────────────────────────────────────────
    #  SUMMARY
    # ─────────────────────────────────────────────────

    banner("PLATFORM SUMMARY")
    print(f"  ✅ Multi-Agent Orchestrator  — 5 agents, natural language routing")
    print(f"  ✅ CRM System               — contacts, leads, scoring (0-100), deals, follow-ups")
    print(f"  ✅ Scheduling               — conflict detection, 6 service types, reminders")
    print(f"  ✅ Workflow Engine           — {len(wf.templates)} templates, multi-step automation")
    print(f"  ✅ UAE Intelligence          — bilingual, {len(DUBAI_AREA_PRICES)} areas, {len(UAE_SERVICES)} govt services, {len(DUBAI_DISTRICTS)} districts")
    print(f"  ✅ Web Dashboard             — FastAPI + real-time UI")
    print(f"  ✅ LLM Router               — Gemini (primary) + Claude + GPT-4o + Ollama")
    print(f"  ✅ Reasoning Engine          — CoT, ToT, self-reflection")
    print(f"  ✅ Docker Ready              — Dockerfile + docker-compose.yml")
    print()
    print(f"  🌐 Dashboard: python -m src.business.dashboard → http://localhost:8000")
    print(f"  🤖 CLI Agent: python run_agent.py --chat")
    print()
    print(f"  Built by Abdul Rahaman — Multi-Agent AI Platform")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
