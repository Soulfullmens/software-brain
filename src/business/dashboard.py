"""
dashboard.py

FastAPI Web Dashboard for the AI Agent System.
Provides REST API + minimal HTML dashboard for monitoring and control.

Endpoints:
    GET  /                     — Dashboard HTML page
    GET  /api/status           — System status overview
    GET  /api/agents           — All agent statuses
    POST /api/task             — Submit a task
    POST /api/natural          — Submit natural language request
    GET  /api/crm/pipeline     — CRM pipeline data
    GET  /api/crm/leads        — All leads
    POST /api/crm/leads        — Create a lead
    GET  /api/support/tickets  — All tickets
    POST /api/support/tickets  — Create a ticket
    GET  /api/properties       — Search properties
    GET  /api/schedule/slots   — Available slots
    POST /api/schedule         — Book appointment
    GET  /api/campaigns        — All campaigns
    POST /api/campaigns        — Create campaign
    GET  /api/uae/property-estimate — UAE property price estimate
    GET  /api/uae/services     — UAE government services
    GET  /api/workflows        — Workflow definitions
    POST /api/workflows/run    — Start a workflow

Run:
    python -m src.business.dashboard
    # or: uvicorn src.business.dashboard:app --reload --port 8000
"""

import json
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
except ImportError:
    print("FastAPI not installed. Run: pip install fastapi uvicorn")
    sys.exit(1)

from src.business.multi_agent import Orchestrator
from src.business.workflow_engine import WorkflowEngine
from src.business.uae_solutions import UAEAISolutions


# ────────────────────────────────────────────────────────
#  App Setup
# ────────────────────────────────────────────────────────

app = FastAPI(
    title="Software Brain — AI Agent Dashboard",
    description="Multi-Agent Business AI System with UAE Specialization",
    version="1.0.0",
)

static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize systems
orchestrator = Orchestrator()
workflow_engine = WorkflowEngine()
uae = UAEAISolutions()

START_TIME = time.time()


# ────────────────────────────────────────────────────────
#  Pydantic Models
# ────────────────────────────────────────────────────────

class TaskRequest(BaseModel):
    action: str
    params: dict = {}

class NaturalRequest(BaseModel):
    text: str

class LeadCreate(BaseModel):
    name: str
    email: str = ""
    phone: str = ""
    source: str = "dashboard"

class TicketCreate(BaseModel):
    subject: str
    description: str = ""
    priority: str = "normal"

class AppointmentCreate(BaseModel):
    type: str = "general"
    client_name: str = ""
    preferred_time: str = ""
    notes: str = ""

class CampaignCreate(BaseModel):
    name: str
    type: str = "email"
    target_audience: str = "all"

class WorkflowRunRequest(BaseModel):
    template: str
    inputs: dict = {}

class PropertyEstimateRequest(BaseModel):
    area: str
    bedrooms: int = 2
    size_sqft: float = 1000.0
    property_type: str = "apartment"


# ────────────────────────────────────────────────────────
#  API Endpoints
# ────────────────────────────────────────────────────────

@app.get("/api/status")
def system_status():
    return {
        "status": "running",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "agents_active": len(orchestrator.agents),
        "total_tasks_processed": len(orchestrator.task_log),
        "version": "1.0.0",
    }


@app.get("/api/agents")
def list_agents():
    return {"agents": [a.get_status() for a in orchestrator.agents]}


@app.post("/api/task")
def submit_task(req: TaskRequest):
    task = {"action": req.action, **req.params}
    result = orchestrator.handle_task(task)
    return result


@app.post("/api/natural")
def natural_language(req: NaturalRequest):
    if not req.text.strip():
        raise HTTPException(400, "Text cannot be empty")
    result = orchestrator.handle_natural(req.text)
    return result


# ── CRM ──

@app.get("/api/crm/pipeline")
def crm_pipeline():
    return orchestrator.crm.handle({"action": "get_pipeline"})


@app.get("/api/crm/leads")
def list_leads():
    return {"leads": list(orchestrator.crm.leads.values())}


@app.post("/api/crm/leads")
def create_lead(lead: LeadCreate):
    result = orchestrator.handle_task({
        "action": "create_lead",
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "source": lead.source,
    })
    return result


# ── Support ──

@app.get("/api/support/tickets")
def list_tickets():
    return {"tickets": list(orchestrator.support.tickets.values())}


@app.post("/api/support/tickets")
def create_ticket(ticket: TicketCreate):
    result = orchestrator.handle_task({
        "action": "create_ticket",
        "subject": ticket.subject,
        "description": ticket.description,
        "priority": ticket.priority,
    })
    return result


# ── Properties ──

@app.get("/api/properties")
def search_properties(
    type: str = None,
    min_bedrooms: int = None,
    max_price: int = None,
    area: str = None,
):
    filters = {}
    if type:
        filters["type"] = type
    if min_bedrooms:
        filters["min_bedrooms"] = min_bedrooms
    if max_price:
        filters["max_price"] = max_price
    if area:
        filters["area"] = area
    return orchestrator.real_estate.handle({"action": "search", "filters": filters})


@app.get("/api/properties/analysis")
def market_analysis(area: str = "Dubai"):
    return orchestrator.real_estate.handle({"action": "market_analysis", "area": area})


# ── Scheduling ──

@app.get("/api/schedule/slots")
def available_slots(date: str = "today"):
    return orchestrator.scheduling.handle({"action": "list_slots", "date": date})


@app.post("/api/schedule")
def book_appointment(appt: AppointmentCreate):
    result = orchestrator.handle_task({
        "action": "create_appointment",
        "type": appt.type,
        "client": {"name": appt.client_name},
        "preferred_time": appt.preferred_time,
        "notes": appt.notes,
    })
    return result


# ── Campaigns ──

@app.get("/api/campaigns")
def list_campaigns():
    return {"campaigns": list(orchestrator.marketing.campaigns.values())}


@app.post("/api/campaigns")
def create_campaign(camp: CampaignCreate):
    result = orchestrator.handle_task({
        "action": "create_campaign",
        "name": camp.name,
        "type": camp.type,
        "target_audience": camp.target_audience,
    })
    return result


# ── UAE Solutions ──

@app.post("/api/uae/property-estimate")
def uae_property_estimate(req: PropertyEstimateRequest):
    estimate = uae.property_predictor.predict_price(
        area=req.area,
        bedrooms=req.bedrooms,
        size_sqft=req.size_sqft,
        property_type=req.property_type,
    )
    return estimate


@app.get("/api/uae/services")
def uae_services():
    return {"services": [s.__dict__ if hasattr(s, '__dict__') else s for s in uae.services.services]}


@app.get("/api/uae/smart-city")
def smart_city_metrics(district: str = "Dubai Marina"):
    metrics = uae.smart_city.get_district_metrics(district)
    return metrics if metrics else {"error": f"District '{district}' not found"}


# ── Workflows ──

@app.get("/api/workflows")
def list_workflows():
    return {"templates": list(workflow_engine.templates.keys())}


@app.post("/api/workflows/run")
def run_workflow(req: WorkflowRunRequest):
    if req.template not in workflow_engine.templates:
        raise HTTPException(404, f"Template '{req.template}' not found")
    execution = workflow_engine.start(req.template, req.inputs)
    return {
        "execution_id": execution.id,
        "status": execution.status.value,
        "steps_completed": len([s for s in execution.step_results if s.get("status") == "completed"]),
    }


# ── Dashboard ──

@app.get("/api/dashboard")
def dashboard_data():
    return orchestrator.get_dashboard_data()


# ────────────────────────────────────────────────────────
#  HTML Dashboard
# ────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agentic Engine Pro — Command Center</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#06060b;--surface:rgba(255,255,255,0.025);--surface-2:rgba(255,255,255,0.04);
  --border:rgba(255,255,255,0.06);--border-h:rgba(255,255,255,0.12);
  --green:#22c55e;--blue:#6366f1;--cyan:#06b6d4;--amber:#f59e0b;--rose:#f43f5e;--violet:#a78bfa;
  --text:#f1f5f9;--text-2:#94a3b8;--text-3:#64748b;
  --radius:14px;--glass:rgba(8,8,16,0.65);
}
html{scroll-behavior:smooth}
body{
  font-family:'Inter',system-ui,-apple-system,sans-serif;color:var(--text);
  min-height:100vh;overflow-x:hidden;
  background: url('/static/bg.png') no-repeat center center fixed;
  background-size: cover;
}
/* Blur overlay for depth */
body::before{
  content:'';position:fixed;inset:0;z-index:-1;
  background: rgba(6, 6, 11, 0.75);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}
/* Grain overlay */
body::after{
  content:'';position:fixed;inset:0;z-index:-1;
  background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.06'/%3E%3C/svg%3E");
  pointer-events:none;
}

/* HEADER */
.topbar{
  position:sticky;top:0;z-index:100;
  background:var(--glass);backdrop-filter:blur(20px) saturate(1.5);-webkit-backdrop-filter:blur(20px) saturate(1.5);
  border-bottom:1px solid var(--border);
}
.topbar-inner{
  max-width:1440px;margin:0 auto;padding:16px 32px;
  display:flex;justify-content:space-between;align-items:center;
}
.logo{display:flex;align-items:center;gap:14px}
.logo-icon{
  width:40px;height:40px;border-radius:12px;
  background:linear-gradient(135deg,#6366f1,#06b6d4);
  display:flex;align-items:center;justify-content:center;font-size:18px;
  box-shadow:0 0 20px rgba(99,102,241,0.3);
}
.logo h1{font-size:20px;font-weight:700;letter-spacing:-0.5px}
.logo span{display:block;font-size:12px;color:var(--text-3);font-weight:400;margin-top:2px;letter-spacing:0.5px;text-transform:uppercase}
.status-pill{
  display:flex;align-items:center;gap:8px;
  padding:8px 16px;border-radius:100px;
  background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.2);
}
.status-dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green);animation:blink 2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}
.status-pill span{font-size:12px;font-weight:600;color:var(--green);letter-spacing:0.5px}
.nav-pills{display:flex;gap:4px;background:var(--surface);border-radius:10px;padding:4px;border:1px solid var(--border)}
.nav-pill{
  padding:7px 16px;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;
  color:var(--text-3);transition:all .2s;border:none;background:none;
}
.nav-pill:hover{color:var(--text)}
.nav-pill.active{background:rgba(99,102,241,0.15);color:#a5b4fc}

/* LAYOUT */
.shell{max-width:1440px;margin:0 auto;padding:28px 32px 60px}
.row{display:grid;gap:20px}
.r4{grid-template-columns:repeat(4,1fr)}
.r3{grid-template-columns:repeat(3,1fr)}
.r2{grid-template-columns:1fr 2fr}
.r-auto{grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
@media(max-width:1024px){.r4,.r3,.r2{grid-template-columns:1fr 1fr}}
@media(max-width:640px){.r4,.r3,.r2{grid-template-columns:1fr}}

/* CARDS */
.card{
  background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
  padding:0;overflow:hidden;transition:all .25s ease;position:relative;
}
.card:hover{border-color:var(--border-h);transform:translateY(-2px);box-shadow:0 8px 32px rgba(0,0,0,.2)}
.card-body{padding:22px 24px}
.card-lg .card-body{padding:28px 28px}

/* KPI Cards */
.kpi{position:relative;overflow:hidden}
.kpi .card-body{position:relative;z-index:1}
.kpi .kpi-glow{
  position:absolute;top:-20px;right:-20px;width:100px;height:100px;border-radius:50%;
  filter:blur(40px);opacity:.15;pointer-events:none;
}
.kpi .label{font-size:12px;font-weight:600;color:var(--text-3);text-transform:uppercase;letter-spacing:1.2px;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.kpi .label svg{width:16px;height:16px;opacity:.5}
.kpi .num{font-family:'JetBrains Mono','Inter',monospace;font-size:40px;font-weight:700;line-height:1;letter-spacing:-2px}
.kpi .sub{font-size:12px;color:var(--text-3);margin-top:8px;font-weight:400}
.kpi .num.c-green{color:var(--green)}.kpi .num.c-blue{color:var(--blue)}
.kpi .num.c-amber{color:var(--amber)}.kpi .num.c-cyan{color:var(--cyan)}

/* Agent cards */
.agent-card{
  display:flex;align-items:center;gap:16px;padding:16px 20px;
  background:var(--surface);border:1px solid var(--border);border-radius:12px;
  transition:all .2s;cursor:default;
}
.agent-card:hover{background:var(--surface-2);border-color:var(--border-h)}
.agent-icon{
  width:42px;height:42px;border-radius:10px;display:flex;align-items:center;justify-content:center;
  font-size:18px;flex-shrink:0;
}
.agent-meta{flex:1;min-width:0}
.agent-meta h4{font-size:14px;font-weight:600;margin-bottom:3px}
.agent-meta p{font-size:12px;color:var(--text-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.agent-stat{
  font-family:'JetBrains Mono',monospace;font-size:13px;font-weight:600;
  padding:4px 12px;border-radius:8px;background:rgba(34,197,94,.08);color:var(--green);white-space:nowrap;
}

/* Badge */
.badge{display:inline-flex;align-items:center;padding:3px 10px;border-radius:6px;font-size:11px;font-weight:600;letter-spacing:.3px}
.b-green{background:rgba(34,197,94,.1);color:var(--green)}.b-blue{background:rgba(99,102,241,.1);color:var(--violet)}
.b-amber{background:rgba(245,158,11,.1);color:var(--amber)}.b-rose{background:rgba(244,63,94,.1);color:var(--rose)}
.b-cyan{background:rgba(6,182,212,.1);color:var(--cyan)}

/* TABLE */
.tbl{width:100%;border-collapse:collapse}
.tbl th{text-align:left;padding:10px 16px;font-size:11px;font-weight:600;color:var(--text-3);text-transform:uppercase;letter-spacing:.8px;border-bottom:1px solid var(--border)}
.tbl td{padding:12px 16px;font-size:13px;border-bottom:1px solid rgba(255,255,255,.03)}
.tbl tr:hover td{background:rgba(255,255,255,.015)}
.tbl .empty{text-align:center;padding:40px 16px;color:var(--text-3);font-size:13px}

/* TABS */
.tab-bar{display:flex;gap:2px;background:var(--surface);border-radius:10px;padding:4px;border:1px solid var(--border);margin-bottom:20px;overflow-x:auto}
.tab-btn{
  padding:8px 18px;border-radius:8px;font-size:13px;font-weight:500;
  cursor:pointer;color:var(--text-3);transition:all .15s;border:none;background:none;white-space:nowrap;
}
.tab-btn:hover{color:var(--text)}
.tab-btn.on{background:rgba(99,102,241,.12);color:#a5b4fc}
.tab-pane{display:none;animation:slideUp .3s ease}.tab-pane.vis{display:block}
@keyframes slideUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}

/* COMMAND CENTER */
.cmd{
  background:linear-gradient(135deg,rgba(99,102,241,.06),rgba(6,182,212,.04));
  border:1px solid rgba(99,102,241,.15);border-radius:var(--radius);
  padding:28px;position:relative;overflow:hidden;
}
.cmd::before{
  content:'';position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,rgba(99,102,241,.5),rgba(6,182,212,.5),transparent);
}
.cmd-title{font-size:16px;font-weight:700;margin-bottom:4px;display:flex;align-items:center;gap:10px}
.cmd-title svg{color:var(--blue);width:20px;height:20px}
.cmd-sub{font-size:13px;color:var(--text-3);margin-bottom:18px}
.cmd-row{display:flex;gap:10px}
.cmd-input{
  flex:1;background:rgba(0,0,0,.25);border:1px solid var(--border);border-radius:10px;
  padding:13px 18px;color:var(--text);font-size:14px;font-family:'Inter',sans-serif;outline:none;
  transition:border-color .2s,box-shadow .2s;
}
.cmd-input:focus{border-color:rgba(99,102,241,.4);box-shadow:0 0 0 3px rgba(99,102,241,.1)}
.cmd-input::placeholder{color:var(--text-3)}
.cmd-btn{
  background:linear-gradient(135deg,#6366f1,#4f46e5);color:#fff;border:none;
  border-radius:10px;padding:13px 26px;font-size:14px;font-weight:600;cursor:pointer;
  transition:transform .15s,box-shadow .15s;font-family:'Inter',sans-serif;
}
.cmd-btn:hover{transform:translateY(-1px);box-shadow:0 6px 20px rgba(99,102,241,.35)}
.cmd-btn:active{transform:translateY(0)}
.cmd-out{
  margin-top:16px;max-height:340px;overflow-y:auto;
  background:rgba(0,0,0,.35);border:1px solid var(--border);border-radius:10px;
  padding:16px;font-family:'JetBrains Mono',monospace;font-size:13px;line-height:1.6;
  color:#cbd5e1;white-space:pre-wrap;
}
.cmd-out .u{color:var(--blue)}.cmd-out .s{color:var(--green)}.cmd-out .w{color:var(--text-3)}

/* Section headers */
.sec{margin-top:32px}.sec-h{font-size:15px;font-weight:700;margin-bottom:16px;display:flex;align-items:center;gap:10px;letter-spacing:-.3px}
.sec-h svg{width:18px;height:18px;color:var(--blue);opacity:.7}

/* Scrollbar */
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,.08);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:rgba(255,255,255,.15)}

/* Slot chips */
.slot{
  padding:8px 16px;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;
  background:rgba(6,182,212,.06);border:1px solid rgba(6,182,212,.2);color:var(--cyan);
  transition:all .15s;
}
.slot:hover{background:rgba(6,182,212,.12);border-color:rgba(6,182,212,.4)}

/* Footer */
.foot{text-align:center;padding:36px 24px;font-size:12px;color:var(--text-3);border-top:1px solid var(--border);margin-top:48px;letter-spacing:.3px}
</style>
</head>
<body>

<!-- TOPBAR -->
<header class="topbar">
  <div class="topbar-inner">
    <div class="logo">
      <div class="logo-icon">&#9672;</div>
      <div>
        <h1>Agentic Engine Pro</h1>
        <span>Multi-Agent Cognitive Platform</span>
      </div>
    </div>
    <nav class="nav-pills" id="main-nav">
      <button class="nav-pill active" onclick="showPage('overview')">Overview</button>
      <button class="nav-pill" onclick="showPage('agents')">Agents</button>
      <button class="nav-pill" onclick="showPage('data')">Data Hub</button>
      <button class="nav-pill" onclick="showPage('command')">Command</button>
    </nav>
    <div class="status-pill"><span class="status-dot"></span><span>SYSTEM ONLINE</span></div>
  </div>
</header>

<main class="shell">

<!-- PAGE: OVERVIEW -->
<div id="page-overview">

  <!-- KPIs -->
  <div class="row r4">
    <div class="card kpi">
      <div class="kpi-glow" style="background:var(--blue)"></div>
      <div class="card-body">
        <div class="label"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>Active Agents</div>
        <div class="num c-blue" id="kpi-agents">-</div>
        <div class="sub">autonomous operators online</div>
      </div>
    </div>
    <div class="card kpi">
      <div class="kpi-glow" style="background:var(--green)"></div>
      <div class="card-body">
        <div class="label"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>Tasks Processed</div>
        <div class="num c-green" id="kpi-tasks">-</div>
        <div class="sub">total orchestrated actions</div>
      </div>
    </div>
    <div class="card kpi">
      <div class="kpi-glow" style="background:var(--amber)"></div>
      <div class="card-body">
        <div class="label"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>Open Tickets</div>
        <div class="num c-amber" id="kpi-tickets">-</div>
        <div class="sub">active support requests</div>
      </div>
    </div>
    <div class="card kpi">
      <div class="kpi-glow" style="background:var(--cyan)"></div>
      <div class="card-body">
        <div class="label"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>Properties</div>
        <div class="num c-cyan" id="kpi-properties">-</div>
        <div class="sub">listed in UAE database</div>
      </div>
    </div>
  </div>

  <!-- Command Center -->
  <div class="sec">
    <div class="cmd">
      <div class="cmd-title">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        Command Center
      </div>
      <div class="cmd-sub">Send natural language instructions to the multi-agent orchestrator.</div>
      <div class="cmd-row">
        <input class="cmd-input" id="chat-in" placeholder="e.g. 'Find a 3BR villa in Dubai Hills' or 'Create a lead for Ahmed'" onkeydown="if(event.key==='Enter')sendChat()">
        <button class="cmd-btn" onclick="sendChat()">Execute &#8594;</button>
      </div>
      <div class="cmd-out" id="chat-out"><span class="w">System initialized. Awaiting commands...</span></div>
    </div>
  </div>

  <!-- Agent Fleet + Quick Stats -->
  <div class="sec">
    <div class="row r2" style="gap:24px;align-items:start">
      <div>
        <div class="sec-h"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>Agent Fleet</div>
        <div style="display:flex;flex-direction:column;gap:10px" id="agent-list"></div>
      </div>
      <div>
        <div class="sec-h"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/></svg>Architecture Overview</div>
        <div class="card card-lg">
          <div class="card-body" style="font-size:13px;color:var(--text-2);line-height:1.7">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
              <div>
                <div style="font-weight:700;color:var(--text);margin-bottom:8px;font-size:14px">Cognitive Stack</div>
                <div style="display:flex;flex-direction:column;gap:6px">
                  <div><span class="badge b-blue">L7</span> Owner Authority</div>
                  <div><span class="badge b-blue">L6</span> Executive Brain</div>
                  <div><span class="badge b-blue">L5</span> Learning Loop</div>
                  <div><span class="badge b-blue">L4</span> Reasoning Engine</div>
                  <div><span class="badge b-blue">L3</span> Memory System</div>
                  <div><span class="badge b-blue">L2</span> Perception</div>
                  <div><span class="badge b-blue">L1</span> Tools & Embodiment</div>
                  <div><span class="badge b-green">L0</span> Identity Core</div>
                </div>
              </div>
              <div>
                <div style="font-weight:700;color:var(--text);margin-bottom:8px;font-size:14px">LLM Providers</div>
                <div style="display:flex;flex-direction:column;gap:6px">
                  <div><span class="badge b-cyan">P1</span> Google Gemini (active)</div>
                  <div><span class="badge b-amber">P2</span> Anthropic Claude</div>
                  <div><span class="badge b-green">P3</span> Ollama / Local</div>
                </div>
                <div style="font-weight:700;color:var(--text);margin-bottom:8px;margin-top:16px;font-size:14px">Business Modules</div>
                <div style="display:flex;flex-direction:column;gap:6px">
                  <div><span class="badge b-green">&#10003;</span> CRM + Lead Scoring</div>
                  <div><span class="badge b-green">&#10003;</span> Workflow Engine</div>
                  <div><span class="badge b-green">&#10003;</span> UAE Intelligence</div>
                  <div><span class="badge b-green">&#10003;</span> Multi-Agent System</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- PAGE: AGENTS (hidden by default) -->
<div id="page-agents" style="display:none">
  <div class="sec-h"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>All Agent Details</div>
  <div class="row r-auto" id="agents-detail"></div>
</div>

<!-- PAGE: DATA HUB (hidden by default) -->
<div id="page-data" style="display:none">
  <div class="tab-bar">
    <button class="tab-btn on" onclick="showTab('crm',this)">CRM Pipeline</button>
    <button class="tab-btn" onclick="showTab('support',this)">Support</button>
    <button class="tab-btn" onclick="showTab('properties',this)">Properties</button>
    <button class="tab-btn" onclick="showTab('schedule',this)">Schedule</button>
    <button class="tab-btn" onclick="showTab('uae',this)">UAE Intel</button>
    <button class="tab-btn" onclick="showTab('workflows',this)">Workflows</button>
  </div>

  <div id="tab-crm" class="tab-pane vis">
    <div class="card card-lg"><div class="card-body">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <span style="font-weight:700;font-size:15px">Lead Pipeline</span>
        <button class="cmd-btn" style="padding:8px 18px;font-size:12px" onclick="quickLead()">+ Add Lead</button>
      </div>
      <table class="tbl"><thead><tr><th>Name</th><th>Email</th><th>Source</th><th>Status</th><th>Score</th></tr></thead>
      <tbody id="crm-table"><tr><td class="empty" colspan="5">No leads yet. Use the command center to create one.</td></tr></tbody></table>
    </div></div>
  </div>

  <div id="tab-support" class="tab-pane">
    <div class="card card-lg"><div class="card-body">
      <span style="font-weight:700;font-size:15px;display:block;margin-bottom:16px">Support Tickets</span>
      <table class="tbl"><thead><tr><th>ID</th><th>Subject</th><th>Category</th><th>Priority</th><th>Status</th></tr></thead>
      <tbody id="support-table"><tr><td class="empty" colspan="5">No open tickets.</td></tr></tbody></table>
    </div></div>
  </div>

  <div id="tab-properties" class="tab-pane">
    <div class="card card-lg"><div class="card-body">
      <span style="font-weight:700;font-size:15px;display:block;margin-bottom:16px">Property Listings</span>
      <table class="tbl"><thead><tr><th>ID</th><th>Type</th><th>Area</th><th>Beds</th><th>Size (sqft)</th><th>Price (AED)</th></tr></thead>
      <tbody id="property-table"></tbody></table>
    </div></div>
  </div>

  <div id="tab-schedule" class="tab-pane">
    <div class="card card-lg"><div class="card-body">
      <span style="font-weight:700;font-size:15px;display:block;margin-bottom:16px">Available Time Slots</span>
      <div id="slots-grid" style="display:flex;flex-wrap:wrap;gap:10px;margin-top:8px"></div>
    </div></div>
  </div>

  <div id="tab-uae" class="tab-pane">
    <div class="card card-lg"><div class="card-body">
      <span style="font-weight:700;font-size:15px;display:block;margin-bottom:16px">UAE Government Services</span>
      <table class="tbl"><thead><tr><th>Service</th><th>Department</th><th>Fee</th></tr></thead>
      <tbody id="uae-table"></tbody></table>
    </div></div>
  </div>

  <div id="tab-workflows" class="tab-pane">
    <div class="card card-lg"><div class="card-body">
      <span style="font-weight:700;font-size:15px;display:block;margin-bottom:16px">Workflow Templates</span>
      <div id="wf-list" style="display:flex;flex-direction:column;gap:10px"></div>
    </div></div>
  </div>
</div>

<!-- PAGE: COMMAND (hidden by default) -->
<div id="page-command" style="display:none">
  <div class="cmd" style="max-width:100%">
    <div class="cmd-title">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
      Full Terminal
    </div>
    <div class="cmd-sub">Multi-agent orchestrator terminal. Responses are routed to the best specialist agent.</div>
    <div class="cmd-row">
      <input class="cmd-input" id="chat-in-2" placeholder="Send a command to the orchestrator..." onkeydown="if(event.key==='Enter')sendChat2()">
      <button class="cmd-btn" onclick="sendChat2()">Run &#9654;</button>
    </div>
    <div class="cmd-out" id="chat-out-2" style="max-height:500px;min-height:200px"><span class="w">Terminal ready. Type a natural language command.</span></div>
  </div>
</div>

</main>

<footer class="foot">&copy; 2026 Agentic Engine Pro &mdash; Autonomous Multi-Agent Cognitive Platform &mdash; Built by Abdul Rahaman</footer>

<script>
const B='';
async function api(p,o){try{const r=await fetch(B+p,o);return await r.json()}catch(e){return{error:e.message}}}

/* Navigation */
function showPage(name){
  ['overview','agents','data','command'].forEach(p=>{
    document.getElementById('page-'+p).style.display=p===name?'block':'none';
  });
  document.querySelectorAll('.nav-pill').forEach(el=>el.classList.remove('active'));
  event.target.classList.add('active');
  if(name==='data')loadData();
  if(name==='agents')loadAgentDetails();
}

/* Tabs */
function showTab(name,btn){
  document.querySelectorAll('.tab-pane').forEach(el=>el.classList.remove('vis'));
  document.getElementById('tab-'+name).classList.add('vis');
  document.querySelectorAll('.tab-btn').forEach(el=>el.classList.remove('on'));
  if(btn)btn.classList.add('on');
}

/* Animated counter */
function animateNum(el,target){
  const start=parseInt(el.textContent)||0;
  if(start===target)return;
  const dur=600,step=Math.ceil(Math.abs(target-start)/30);
  let cur=start;
  const t=setInterval(()=>{
    cur+=(target>start?1:-1)*step;
    if((target>start&&cur>=target)||(target<start&&cur<=target)){cur=target;clearInterval(t)}
    el.textContent=cur;
  },dur/30);
}

const AGENT_ICONS={crm_agent:'&#128188;',support_agent:'&#127384;',real_estate_agent:'&#127969;',scheduling_agent:'&#128197;',marketing_agent:'&#128226;'};
const AGENT_COLORS={crm_agent:'rgba(99,102,241,.12)',support_agent:'rgba(245,158,11,.12)',real_estate_agent:'rgba(6,182,212,.12)',scheduling_agent:'rgba(34,197,94,.12)',marketing_agent:'rgba(244,63,94,.12)'};

async function refresh(){
  const d=await api('/api/dashboard');
  if(!d.agents)return;
  animateNum(document.getElementById('kpi-agents'),d.agents.length);
  animateNum(document.getElementById('kpi-tasks'),d.total_tasks||0);
  animateNum(document.getElementById('kpi-tickets'),d.active_tickets||0);
  animateNum(document.getElementById('kpi-properties'),d.property_listings||0);

  const al=document.getElementById('agent-list');
  al.innerHTML=d.agents.map(a=>`
    <div class="agent-card">
      <div class="agent-icon" style="background:${AGENT_COLORS[a.id]||'var(--surface-2)'}">${AGENT_ICONS[a.id]||'&#9679;'}</div>
      <div class="agent-meta"><h4>${a.name}</h4><p>${(a.capabilities||[]).join(' &middot; ')}</p></div>
      <div class="agent-stat">${a.stats.tasks_handled}</div>
    </div>`).join('');
}

async function loadAgentDetails(){
  const d=await api('/api/agents');
  if(!d.agents)return;
  const el=document.getElementById('agents-detail');
  el.innerHTML=d.agents.map(a=>`
    <div class="card card-lg">
      <div class="card-body">
        <div style="display:flex;align-items:center;gap:14px;margin-bottom:16px">
          <div class="agent-icon" style="background:${AGENT_COLORS[a.id]||'var(--surface-2)'};font-size:24px">${AGENT_ICONS[a.id]||'&#9679;'}</div>
          <div><div style="font-size:16px;font-weight:700">${a.name}</div><div style="font-size:12px;color:var(--text-3)">${a.id}</div></div>
        </div>
        <div style="font-size:13px;color:var(--text-2);margin-bottom:12px">Capabilities:</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px">${(a.capabilities||[]).map(c=>'<span class="badge b-blue">'+c+'</span>').join('')}</div>
        <div style="margin-top:16px;display:flex;gap:16px">
          <div style="text-align:center"><div style="font-family:'JetBrains Mono',monospace;font-size:24px;font-weight:700;color:var(--green)">${a.stats.tasks_handled}</div><div style="font-size:11px;color:var(--text-3)">Tasks</div></div>
          <div style="text-align:center"><div style="font-family:'JetBrains Mono',monospace;font-size:24px;font-weight:700;color:var(--amber)">${a.stats.errors||0}</div><div style="font-size:11px;color:var(--text-3)">Errors</div></div>
        </div>
      </div>
    </div>`).join('');
}

async function loadData(){
  const [p,leads,tix,slots,srv,wf]=await Promise.all([
    api('/api/properties'),api('/api/crm/leads'),api('/api/support/tickets'),
    api('/api/schedule/slots'),api('/api/uae/services'),api('/api/workflows')
  ]);

  if(p.properties){
    document.getElementById('property-table').innerHTML=p.properties.map(pr=>`
      <tr><td style="font-family:'JetBrains Mono',monospace;font-size:12px">#${pr.id.split('-')[0]}</td><td>${pr.type}</td><td>${pr.area}</td><td>${pr.bedrooms}</td><td>${pr.size_sqft.toLocaleString()}</td><td style="color:var(--green);font-weight:600;font-family:'JetBrains Mono',monospace">AED ${pr.price_aed.toLocaleString()}</td></tr>`).join('');
  }

  if(leads.leads&&leads.leads.length){
    document.getElementById('crm-table').innerHTML=leads.leads.map(l=>`
      <tr><td style="font-weight:600">${l.name}</td><td>${l.email||'-'}</td><td><span class="badge b-cyan">${l.source||'web'}</span></td><td><span class="badge ${l.status==='qualified'?'b-green':(l.status==='new'?'b-blue':'b-amber')}">${l.status}</span></td><td><span style="font-family:'JetBrains Mono',monospace;font-weight:600">${l.score}/100</span></td></tr>`).join('');
  }

  if(tix.tickets&&tix.tickets.length){
    document.getElementById('support-table').innerHTML=tix.tickets.map(t=>`
      <tr><td style="font-family:'JetBrains Mono',monospace;font-size:12px">#${t.id.split('-')[0]}</td><td>${t.subject}</td><td><span class="badge b-amber">${t.category}</span></td><td><span class="badge ${t.priority==='high'?'b-rose':(t.priority==='normal'?'b-blue':'b-green')}">${t.priority}</span></td><td>${t.status}</td></tr>`).join('');
  }

  if(slots.available_slots){
    document.getElementById('slots-grid').innerHTML=slots.available_slots.map(s=>
      `<div class="slot" onclick="bookSlot('${s}')">${s}</div>`).join('');
  }

  if(srv.services){
    document.getElementById('uae-table').innerHTML=srv.services.map(s=>`
      <tr><td style="font-weight:500">${s.name_en||s.name||'-'}</td><td>${s.department||'-'}</td><td style="color:var(--green);font-family:'JetBrains Mono',monospace">${s.fee_aed?s.fee_aed+' AED':'Free'}</td></tr>`).join('');
  }

  if(wf.templates){
    document.getElementById('wf-list').innerHTML=wf.templates.map(t=>`
      <div class="agent-card"><div class="agent-icon" style="background:rgba(99,102,241,.1)">&#9881;</div><div class="agent-meta"><h4>${t.replace(/_/g,' ').replace(/\\b\\w/g,c=>c.toUpperCase())}</h4><p>Automated business workflow template</p></div><button class="cmd-btn" style="padding:6px 14px;font-size:12px" onclick="runWf('${t}')">Run</button></div>`).join('');
  }
}

async function sendChat(){
  const inp=document.getElementById('chat-in'),out=document.getElementById('chat-out');
  const text=inp.value.trim();if(!text)return;inp.value='';
  out.innerHTML+='\\n\\n<span class="u">&gt; '+text+'</span>\\n<span class="w">Processing...</span>';
  out.scrollTop=out.scrollHeight;
  const r=await api('/api/natural',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
  out.innerHTML+='\\n<span class="s">&gt; RESULT:</span>\\n'+JSON.stringify(r,null,2);
  out.scrollTop=out.scrollHeight;setTimeout(refresh,500);
}

async function sendChat2(){
  const inp=document.getElementById('chat-in-2'),out=document.getElementById('chat-out-2');
  const text=inp.value.trim();if(!text)return;inp.value='';
  out.innerHTML+='\\n\\n<span class="u">&gt; '+text+'</span>\\n<span class="w">Routing to specialist agent...</span>';
  out.scrollTop=out.scrollHeight;
  const r=await api('/api/natural',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
  out.innerHTML+='\\n<span class="s">&gt; RESPONSE:</span>\\n'+JSON.stringify(r,null,2);
  out.scrollTop=out.scrollHeight;setTimeout(refresh,500);
}

async function bookSlot(time){
  const name=prompt('Client name for '+time+' slot:');if(!name)return;
  await api('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'consultation',client_name:name,preferred_time:time})});
  loadData();
}

async function quickLead(){
  const name=prompt('Lead name:');if(!name)return;
  const email=prompt('Email (optional):')||'';
  await api('/api/crm/leads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,email,source:'dashboard'})});
  loadData();
}

async function runWf(template){
  const r=await api('/api/workflows/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({template,inputs:{}})});
  alert('Workflow started: '+JSON.stringify(r));
}

refresh();setInterval(refresh,6000);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    return DASHBOARD_HTML


# ────────────────────────────────────────────────────────
#  Run
# ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("\n🧠 Software Brain Dashboard starting on http://localhost:8000\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
