"""
multi_agent.py

Multi-Agent Orchestrator for Business Operations.
Coordinates specialized agents that each handle a domain.

Architecture:
    Orchestrator
    ├── CRMAgent          — Manages leads, contacts, deals
    ├── SupportAgent      — Handles customer tickets & queries
    ├── RealEstateAgent   — Property matching & market analysis
    ├── SchedulingAgent   — Appointments, calendars, reminders
    ├── MarketingAgent    — Campaigns, content, analytics
    └── UAELocalAgent     — Bilingual, government services, local context

Communication:
    Agents communicate through a message bus. The orchestrator
    routes tasks to the best agent, handles escalation, and
    merges results.

Example:
    orch = Orchestrator()
    result = await orch.handle("I need to schedule a property viewing
        for a client who called in Arabic about a villa in Dubai Marina")
    # → Routes to: UAELocalAgent (Arabic handling)
    #            + RealEstateAgent (property lookup)
    #            + SchedulingAgent (viewing slot)
    #   Orchestrator merges and returns unified response.
"""

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


# ────────────────────────────────────────────────────────
#  Message Bus
# ────────────────────────────────────────────────────────

class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class MessageType(str, Enum):
    TASK = "task"
    RESULT = "result"
    QUERY = "query"
    EVENT = "event"
    ESCALATION = "escalation"


@dataclass
class AgentMessage:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    sender: str = ""
    recipient: str = ""
    msg_type: MessageType = MessageType.TASK
    priority: Priority = Priority.NORMAL
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    correlation_id: str = ""       # links related messages
    requires_response: bool = False
    ttl_seconds: float = 300.0     # message expires after this


class MessageBus:
    """In-process message bus for agent-to-agent communication."""

    def __init__(self):
        self.queues: Dict[str, List[AgentMessage]] = {}
        self.subscribers: Dict[str, List[Callable]] = {}
        self.history: List[AgentMessage] = []

    def register(self, agent_name: str):
        self.queues.setdefault(agent_name, [])

    def send(self, msg: AgentMessage):
        self.history.append(msg)
        if msg.recipient in self.queues:
            self.queues[msg.recipient].append(msg)
        # notify subscribers
        for sub in self.subscribers.get(msg.recipient, []):
            sub(msg)
        # broadcast subscribers
        for sub in self.subscribers.get("*", []):
            sub(msg)

    def receive(self, agent_name: str) -> List[AgentMessage]:
        msgs = self.queues.get(agent_name, [])
        # filter expired
        now = time.time()
        valid = [m for m in msgs if now - m.timestamp < m.ttl_seconds]
        self.queues[agent_name] = []
        return valid

    def subscribe(self, agent_name: str, callback: Callable):
        self.subscribers.setdefault(agent_name, []).append(callback)


# ────────────────────────────────────────────────────────
#  Base Agent
# ────────────────────────────────────────────────────────

class AgentCapability(str, Enum):
    CRM = "crm"
    SUPPORT = "support"
    REAL_ESTATE = "real_estate"
    SCHEDULING = "scheduling"
    MARKETING = "marketing"
    UAE_LOCAL = "uae_local"
    BILLING = "billing"
    ANALYTICS = "analytics"
    COMMUNICATION = "communication"


@dataclass
class AgentProfile:
    name: str
    capabilities: Set[AgentCapability]
    description: str = ""
    max_concurrent: int = 5
    priority: int = 50


class BaseAgent:
    """Base class for all specialized agents."""

    def __init__(self, profile: AgentProfile, bus: MessageBus, llm_fn: Optional[Callable] = None):
        self.profile = profile
        self.bus = bus
        self.llm_fn = llm_fn   # async fn(prompt) -> str
        self.bus.register(profile.name)
        self.active_tasks: Dict[str, Dict] = {}
        self.completed_tasks: List[Dict] = []
        self.stats = {"tasks_handled": 0, "tasks_failed": 0, "avg_response_ms": 0}

    @property
    def name(self) -> str:
        return self.profile.name

    def can_handle(self, task: Dict) -> float:
        """Return confidence 0.0–1.0 that this agent can handle the task."""
        return 0.0

    def handle(self, task: Dict) -> Dict:
        """Process a task and return result."""
        raise NotImplementedError

    def _llm(self, prompt: str) -> str:
        if self.llm_fn:
            return self.llm_fn(prompt)
        return f"[{self.name}] No LLM configured — would process: {prompt[:100]}"

    def _send(self, recipient: str, payload: Dict, msg_type: MessageType = MessageType.QUERY):
        msg = AgentMessage(
            sender=self.name,
            recipient=recipient,
            msg_type=msg_type,
            payload=payload,
        )
        self.bus.send(msg)

    def get_status(self) -> Dict:
        return {
            "name": self.name,
            "capabilities": [c.value for c in self.profile.capabilities],
            "active_tasks": len(self.active_tasks),
            "stats": self.stats,
        }


# ────────────────────────────────────────────────────────
#  Specialized Agents
# ────────────────────────────────────────────────────────

class CRMAgent(BaseAgent):
    """Manages leads, contacts, deals, and sales pipeline."""

    def __init__(self, bus: MessageBus, llm_fn: Optional[Callable] = None):
        super().__init__(
            AgentProfile(
                name="crm_agent",
                capabilities={AgentCapability.CRM, AgentCapability.ANALYTICS},
                description="CRM pipeline management — leads, contacts, deals",
            ),
            bus, llm_fn,
        )
        self.leads: Dict[str, Dict] = {}
        self.contacts: Dict[str, Dict] = {}
        self.deals: Dict[str, Dict] = {}

    def can_handle(self, task: Dict) -> float:
        keywords = {"lead", "contact", "deal", "pipeline", "crm", "sales", "prospect", "customer", "client"}
        text = json.dumps(task).lower()
        matches = sum(1 for k in keywords if k in text)
        return min(1.0, matches * 0.2)

    def handle(self, task: Dict) -> Dict:
        action = task.get("action", "process")
        self.stats["tasks_handled"] += 1

        if action == "create_lead":
            lead_id = str(uuid.uuid4())[:8]
            lead = {
                "id": lead_id,
                "name": task.get("name", "Unknown"),
                "email": task.get("email", ""),
                "phone": task.get("phone", ""),
                "source": task.get("source", "direct"),
                "status": "new",
                "score": 0,
                "created": time.time(),
                "notes": [],
            }
            self.leads[lead_id] = lead
            return {"status": "ok", "lead_id": lead_id, "lead": lead}

        elif action == "qualify_lead":
            lead_id = task.get("lead_id", "")
            lead = self.leads.get(lead_id)
            if not lead:
                return {"status": "error", "message": f"Lead {lead_id} not found"}
            # score based on available info
            score = 0
            if lead.get("email"):
                score += 20
            if lead.get("phone"):
                score += 20
            if task.get("budget"):
                score += 30
            if task.get("timeline", "") in ("immediate", "1_month"):
                score += 30
            lead["score"] = score
            lead["status"] = "qualified" if score >= 50 else "nurture"
            return {"status": "ok", "lead_id": lead_id, "score": score, "qualification": lead["status"]}

        elif action == "get_pipeline":
            return {
                "status": "ok",
                "pipeline": {
                    "new": [l for l in self.leads.values() if l["status"] == "new"],
                    "qualified": [l for l in self.leads.values() if l["status"] == "qualified"],
                    "nurture": [l for l in self.leads.values() if l["status"] == "nurture"],
                },
                "deals": list(self.deals.values()),
                "total_leads": len(self.leads),
            }

        else:
            prompt = f"CRM task: {json.dumps(task)}\nProcess this CRM request and return structured JSON."
            return {"status": "ok", "response": self._llm(prompt)}


class SupportAgent(BaseAgent):
    """Handles customer support tickets and queries."""

    def __init__(self, bus: MessageBus, llm_fn: Optional[Callable] = None):
        super().__init__(
            AgentProfile(
                name="support_agent",
                capabilities={AgentCapability.SUPPORT, AgentCapability.COMMUNICATION},
                description="Customer support — tickets, queries, resolution",
            ),
            bus, llm_fn,
        )
        self.tickets: Dict[str, Dict] = {}
        self.kb: List[Dict] = [
            {"q": "hours", "a": "Our business hours are Sunday-Thursday, 9 AM - 6 PM (UAE time)."},
            {"q": "refund", "a": "Refund requests are processed within 5-7 business days."},
            {"q": "contact", "a": "Email: support@company.ae | Phone: +971-4-XXX-XXXX"},
            {"q": "location", "a": "Our office is located in Dubai Internet City, Building 12."},
        ]

    def can_handle(self, task: Dict) -> float:
        keywords = {"ticket", "support", "help", "issue", "problem", "complaint", "query", "question", "feedback"}
        text = json.dumps(task).lower()
        matches = sum(1 for k in keywords if k in text)
        return min(1.0, matches * 0.2)

    def handle(self, task: Dict) -> Dict:
        action = task.get("action", "process")
        self.stats["tasks_handled"] += 1

        if action == "create_ticket":
            ticket_id = f"TKT-{str(uuid.uuid4())[:6].upper()}"
            ticket = {
                "id": ticket_id,
                "subject": task.get("subject", "General inquiry"),
                "description": task.get("description", ""),
                "priority": task.get("priority", "normal"),
                "status": "open",
                "category": self._classify(task.get("description", "")),
                "created": time.time(),
                "resolution": None,
            }
            self.tickets[ticket_id] = ticket
            return {"status": "ok", "ticket_id": ticket_id, "ticket": ticket}

        elif action == "resolve_ticket":
            ticket_id = task.get("ticket_id", "")
            ticket = self.tickets.get(ticket_id)
            if not ticket:
                return {"status": "error", "message": f"Ticket {ticket_id} not found"}
            ticket["status"] = "resolved"
            ticket["resolution"] = task.get("resolution", "Resolved by agent")
            ticket["resolved_at"] = time.time()
            return {"status": "ok", "ticket": ticket}

        elif action == "kb_search":
            query = task.get("query", "").lower()
            results = [item for item in self.kb if query in item["q"].lower() or any(w in item["a"].lower() for w in query.split())]
            return {"status": "ok", "results": results}

        else:
            prompt = f"Customer support request: {json.dumps(task)}\nProvide a helpful response."
            return {"status": "ok", "response": self._llm(prompt), "action": "general_support"}

    def _classify(self, text: str) -> str:
        text_lower = text.lower()
        if any(w in text_lower for w in ["refund", "money", "payment", "charge"]):
            return "billing"
        if any(w in text_lower for w in ["bug", "error", "crash", "broken"]):
            return "technical"
        if any(w in text_lower for w in ["appointment", "schedule", "booking"]):
            return "scheduling"
        return "general"


class RealEstateAgent(BaseAgent):
    """Property matching, market analysis, and real estate operations."""

    def __init__(self, bus: MessageBus, llm_fn: Optional[Callable] = None):
        super().__init__(
            AgentProfile(
                name="real_estate_agent",
                capabilities={AgentCapability.REAL_ESTATE, AgentCapability.ANALYTICS},
                description="Real estate — property matching, market analysis, Dubai focus",
            ),
            bus, llm_fn,
        )
        # sample property inventory
        self.properties: List[Dict] = [
            {"id": "P001", "type": "apartment", "bedrooms": 2, "area": "Dubai Marina", "price_aed": 1_800_000, "size_sqft": 1200, "status": "available"},
            {"id": "P002", "type": "villa", "bedrooms": 4, "area": "Arabian Ranches", "price_aed": 5_500_000, "size_sqft": 3500, "status": "available"},
            {"id": "P003", "type": "apartment", "bedrooms": 1, "area": "Downtown Dubai", "price_aed": 1_200_000, "size_sqft": 750, "status": "available"},
            {"id": "P004", "type": "apartment", "bedrooms": 3, "area": "JBR", "price_aed": 3_200_000, "size_sqft": 1800, "status": "available"},
            {"id": "P005", "type": "villa", "bedrooms": 5, "area": "Palm Jumeirah", "price_aed": 15_000_000, "size_sqft": 5000, "status": "available"},
            {"id": "P006", "type": "townhouse", "bedrooms": 3, "area": "Dubai Hills", "price_aed": 2_800_000, "size_sqft": 2200, "status": "available"},
            {"id": "P007", "type": "apartment", "bedrooms": 2, "area": "Business Bay", "price_aed": 1_500_000, "size_sqft": 1100, "status": "available"},
            {"id": "P008", "type": "villa", "bedrooms": 6, "area": "Emirates Hills", "price_aed": 25_000_000, "size_sqft": 8000, "status": "available"},
        ]

    def can_handle(self, task: Dict) -> float:
        keywords = {"property", "villa", "apartment", "real estate", "rent", "buy", "bedroom", "area", "dubai", "viewing", "listing", "sqft"}
        text = json.dumps(task).lower()
        matches = sum(1 for k in keywords if k in text)
        return min(1.0, matches * 0.15)

    def handle(self, task: Dict) -> Dict:
        action = task.get("action", "search")
        self.stats["tasks_handled"] += 1

        if action == "search":
            filters = task.get("filters", {})
            results = self.properties[:]
            if "type" in filters:
                results = [p for p in results if p["type"] == filters["type"]]
            if "min_bedrooms" in filters:
                results = [p for p in results if p["bedrooms"] >= filters["min_bedrooms"]]
            if "max_price" in filters:
                results = [p for p in results if p["price_aed"] <= filters["max_price"]]
            if "area" in filters:
                area_lower = filters["area"].lower()
                results = [p for p in results if area_lower in p["area"].lower()]
            if "min_size" in filters:
                results = [p for p in results if p["size_sqft"] >= filters["min_size"]]
            return {"status": "ok", "count": len(results), "properties": results}

        elif action == "market_analysis":
            area = task.get("area", "Dubai")
            # simulated market data
            area_data = {
                "area": area,
                "avg_price_sqft": 1450,
                "yoy_change": "+8.2%",
                "inventory": len([p for p in self.properties if area.lower() in p["area"].lower()]),
                "demand_score": 78,
                "recommendation": "Strong buy signal — prices rising with steady demand",
            }
            return {"status": "ok", "analysis": area_data}

        elif action == "schedule_viewing":
            prop_id = task.get("property_id")
            prop = next((p for p in self.properties if p["id"] == prop_id), None)
            if not prop:
                return {"status": "error", "message": f"Property {prop_id} not found"}
            # delegate scheduling to scheduling agent
            self._send("scheduling_agent", {
                "action": "create_appointment",
                "type": "property_viewing",
                "property": prop,
                "client": task.get("client", {}),
                "preferred_time": task.get("preferred_time", ""),
            })
            return {"status": "ok", "message": f"Viewing request sent for {prop['area']} {prop['type']}", "property": prop}

        else:
            prompt = f"Real estate task: {json.dumps(task)}\nProvide analysis."
            return {"status": "ok", "response": self._llm(prompt)}


class SchedulingAgent(BaseAgent):
    """Appointment scheduling, calendar management, and reminders."""

    def __init__(self, bus: MessageBus, llm_fn: Optional[Callable] = None):
        super().__init__(
            AgentProfile(
                name="scheduling_agent",
                capabilities={AgentCapability.SCHEDULING, AgentCapability.COMMUNICATION},
                description="Scheduling — appointments, calendar, reminders",
            ),
            bus, llm_fn,
        )
        self.appointments: Dict[str, Dict] = {}
        self.available_slots: List[str] = [
            "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
            "14:00", "14:30", "15:00", "15:30", "16:00", "16:30",
        ]

    def can_handle(self, task: Dict) -> float:
        keywords = {"schedule", "appointment", "calendar", "booking", "slot", "reminder", "meeting", "time"}
        text = json.dumps(task).lower()
        matches = sum(1 for k in keywords if k in text)
        return min(1.0, matches * 0.25)

    def handle(self, task: Dict) -> Dict:
        action = task.get("action", "process")
        self.stats["tasks_handled"] += 1

        if action == "create_appointment":
            appt_id = f"APT-{str(uuid.uuid4())[:6].upper()}"
            appt = {
                "id": appt_id,
                "type": task.get("type", "general"),
                "client": task.get("client", {}),
                "preferred_time": task.get("preferred_time", ""),
                "assigned_slot": self._find_slot(task.get("preferred_time", "")),
                "status": "confirmed",
                "notes": task.get("notes", ""),
                "created": time.time(),
            }
            if task.get("property"):
                appt["property"] = task["property"]
            self.appointments[appt_id] = appt
            return {"status": "ok", "appointment_id": appt_id, "appointment": appt}

        elif action == "list_slots":
            booked = {a["assigned_slot"] for a in self.appointments.values() if a.get("assigned_slot")}
            available = [s for s in self.available_slots if s not in booked]
            return {"status": "ok", "available_slots": available, "date": task.get("date", "today")}

        elif action == "cancel_appointment":
            appt_id = task.get("appointment_id", "")
            if appt_id in self.appointments:
                self.appointments[appt_id]["status"] = "cancelled"
                return {"status": "ok", "message": f"Appointment {appt_id} cancelled"}
            return {"status": "error", "message": f"Appointment {appt_id} not found"}

        elif action == "reschedule":
            appt_id = task.get("appointment_id", "")
            if appt_id in self.appointments:
                new_slot = self._find_slot(task.get("new_time", ""))
                self.appointments[appt_id]["assigned_slot"] = new_slot
                return {"status": "ok", "appointment_id": appt_id, "new_slot": new_slot}
            return {"status": "error", "message": f"Appointment {appt_id} not found"}

        else:
            return {"status": "ok", "response": self._llm(f"Scheduling task: {json.dumps(task)}")}

    def _find_slot(self, preferred: str) -> str:
        booked = {a["assigned_slot"] for a in self.appointments.values() if a.get("assigned_slot")}
        if preferred and preferred in self.available_slots and preferred not in booked:
            return preferred
        available = [s for s in self.available_slots if s not in booked]
        return available[0] if available else "waitlist"


class MarketingAgent(BaseAgent):
    """Marketing campaigns, content generation, and analytics."""

    def __init__(self, bus: MessageBus, llm_fn: Optional[Callable] = None):
        super().__init__(
            AgentProfile(
                name="marketing_agent",
                capabilities={AgentCapability.MARKETING, AgentCapability.ANALYTICS, AgentCapability.COMMUNICATION},
                description="Marketing — campaigns, content, analytics",
            ),
            bus, llm_fn,
        )
        self.campaigns: Dict[str, Dict] = {}

    def can_handle(self, task: Dict) -> float:
        keywords = {"marketing", "campaign", "email blast", "newsletter", "content", "social media", "ad", "promotion"}
        text = json.dumps(task).lower()
        matches = sum(1 for k in keywords if k in text)
        return min(1.0, matches * 0.2)

    def handle(self, task: Dict) -> Dict:
        action = task.get("action", "process")
        self.stats["tasks_handled"] += 1

        if action == "create_campaign":
            camp_id = f"CAMP-{str(uuid.uuid4())[:6].upper()}"
            campaign = {
                "id": camp_id,
                "name": task.get("name", "Untitled Campaign"),
                "type": task.get("type", "email"),
                "target_audience": task.get("target_audience", "all"),
                "status": "draft",
                "metrics": {"sent": 0, "opened": 0, "clicked": 0, "converted": 0},
                "created": time.time(),
            }
            self.campaigns[camp_id] = campaign
            return {"status": "ok", "campaign_id": camp_id, "campaign": campaign}

        elif action == "generate_content":
            topic = task.get("topic", "business update")
            content_type = task.get("content_type", "email")
            prompt = f"Generate a {content_type} about: {topic}\nTarget audience: {task.get('audience', 'general')}\nTone: professional, engaging\nKeep it concise."
            return {"status": "ok", "content": self._llm(prompt), "type": content_type}

        elif action == "campaign_analytics":
            camp_id = task.get("campaign_id")
            if camp_id and camp_id in self.campaigns:
                return {"status": "ok", "analytics": self.campaigns[camp_id]["metrics"]}
            # summary
            return {
                "status": "ok",
                "total_campaigns": len(self.campaigns),
                "campaigns": list(self.campaigns.values()),
            }

        else:
            return {"status": "ok", "response": self._llm(f"Marketing task: {json.dumps(task)}")}


# ────────────────────────────────────────────────────────
#  Orchestrator
# ────────────────────────────────────────────────────────

class TaskRouter:
    """Routes tasks to the best agent(s) based on capability matching."""

    def __init__(self, agents: List[BaseAgent]):
        self.agents = agents

    def route(self, task: Dict) -> List[tuple]:
        """Return [(agent, confidence)] sorted by confidence desc."""
        scored = []
        for agent in self.agents:
            conf = agent.can_handle(task)
            if conf > 0.05:
                scored.append((agent, conf))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def best_agent(self, task: Dict) -> Optional[BaseAgent]:
        routes = self.route(task)
        return routes[0][0] if routes else None


class Orchestrator:
    """
    Multi-Agent Orchestrator.

    Routes tasks, coordinates between agents, handles multi-agent tasks,
    and provides a unified interface.

    Usage:
        orch = Orchestrator()
        result = orch.handle_task({"action": "create_lead", "name": "Ahmed"})
        # → routed to CRMAgent

        result = orch.handle_natural("I need a 3-bedroom villa in Dubai Hills")
        # → routed to RealEstateAgent via intent detection
    """

    def __init__(self, llm_fn: Optional[Callable] = None):
        self.bus = MessageBus()
        self.llm_fn = llm_fn

        # initialize all agents
        self.crm = CRMAgent(self.bus, llm_fn)
        self.support = SupportAgent(self.bus, llm_fn)
        self.real_estate = RealEstateAgent(self.bus, llm_fn)
        self.scheduling = SchedulingAgent(self.bus, llm_fn)
        self.marketing = MarketingAgent(self.bus, llm_fn)

        self.agents: List[BaseAgent] = [
            self.crm, self.support, self.real_estate,
            self.scheduling, self.marketing,
        ]
        self.router = TaskRouter(self.agents)

        self.task_log: List[Dict] = []

    def handle_task(self, task: Dict) -> Dict:
        """Route and execute a structured task."""
        start = time.time()
        agent = self.router.best_agent(task)
        if not agent:
            return {"status": "error", "message": "No agent available for this task"}

        result = agent.handle(task)
        elapsed = time.time() - start

        log_entry = {
            "task": task,
            "agent": agent.name,
            "result_status": result.get("status"),
            "elapsed_ms": round(elapsed * 1000, 1),
            "timestamp": time.time(),
        }
        self.task_log.append(log_entry)
        result["_routed_to"] = agent.name
        result["_elapsed_ms"] = round(elapsed * 1000, 1)
        return result

    def handle_multi(self, task: Dict) -> Dict:
        """Handle a task that may require multiple agents."""
        routes = self.router.route(task)
        if not routes:
            return {"status": "error", "message": "No agents matched"}

        results = {}
        for agent, confidence in routes:
            if confidence >= 0.2:
                result = agent.handle(task)
                results[agent.name] = {
                    "confidence": confidence,
                    "result": result,
                }
        return {"status": "ok", "agents_involved": len(results), "results": results}

    def handle_natural(self, text: str) -> Dict:
        """
        Handle a natural language request.
        Detects intent and routes to appropriate agent(s).
        """
        intent = self._detect_intent(text)
        task = {"action": intent["action"], "text": text, **intent.get("params", {})}

        if intent.get("multi_agent"):
            return self.handle_multi(task)
        return self.handle_task(task)

    def _detect_intent(self, text: str) -> Dict:
        """Rule-based intent detection (LLM-enhanced when available)."""
        text_lower = text.lower()

        # property search
        if any(w in text_lower for w in ["villa", "apartment", "property", "bedroom", "rent", "buy"]):
            filters = {}
            if "villa" in text_lower:
                filters["type"] = "villa"
            elif "apartment" in text_lower:
                filters["type"] = "apartment"
            elif "townhouse" in text_lower:
                filters["type"] = "townhouse"
            # extract bedrooms
            for i in range(1, 10):
                if f"{i} bedroom" in text_lower or f"{i}-bedroom" in text_lower or f"{i}br" in text_lower:
                    filters["min_bedrooms"] = i
                    break
            # extract area
            areas = ["dubai marina", "downtown", "jbr", "palm jumeirah", "dubai hills",
                      "arabian ranches", "business bay", "emirates hills"]
            for area in areas:
                if area in text_lower:
                    filters["area"] = area
                    break
            return {"action": "search", "params": {"filters": filters}}

        # scheduling
        if any(w in text_lower for w in ["schedule", "appointment", "book", "meeting"]):
            return {"action": "create_appointment", "params": {"type": "general", "client": {"name": text}}}

        # support
        if any(w in text_lower for w in ["help", "issue", "problem", "complaint", "support"]):
            return {"action": "create_ticket", "params": {"subject": text[:100], "description": text}}

        # CRM
        if any(w in text_lower for w in ["lead", "client", "customer", "prospect", "sales"]):
            return {"action": "create_lead", "params": {"name": text[:50], "source": "natural_language"}}

        # marketing
        if any(w in text_lower for w in ["campaign", "marketing", "newsletter", "promotion"]):
            return {"action": "create_campaign", "params": {"name": text[:50]}}

        # multi-domain: property + scheduling
        if any(w in text_lower for w in ["viewing"]):
            return {"action": "schedule_viewing", "params": {}, "multi_agent": True}

        # default: general support
        return {"action": "process", "params": {"text": text}}

    def get_dashboard_data(self) -> Dict:
        """Return all agent statuses and metrics for the dashboard."""
        return {
            "agents": [a.get_status() for a in self.agents],
            "total_tasks": len(self.task_log),
            "recent_tasks": self.task_log[-10:],
            "crm_pipeline": self.crm.handle({"action": "get_pipeline"}),
            "active_tickets": len([t for t in self.support.tickets.values() if t["status"] == "open"]),
            "appointments_today": len(self.scheduling.appointments),
            "active_campaigns": len([c for c in self.marketing.campaigns.values() if c["status"] != "completed"]),
            "property_listings": len(self.real_estate.properties),
        }

    def export_log(self, path: str = "agent_data/orchestrator_log.json"):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.task_log, f, indent=2)


# ────────────────────────────────────────────────────────
#  Quick Test
# ────────────────────────────────────────────────────────

if __name__ == "__main__":
    orch = Orchestrator()

    print("=== Multi-Agent Orchestrator Demo ===\n")

    # 1. Create a lead
    r = orch.handle_task({"action": "create_lead", "name": "Ahmed Al Maktoum", "email": "ahmed@email.ae", "phone": "+971501234567"})
    print(f"1. Create Lead → Agent: {r['_routed_to']}, Lead ID: {r.get('lead_id')}")

    # 2. Search properties
    r = orch.handle_natural("I need a 3-bedroom villa in Dubai Hills")
    print(f"2. Property Search → Agent: {r['_routed_to']}, Found: {r.get('count')} properties")

    # 3. Create support ticket
    r = orch.handle_natural("I have an issue with my payment, please help")
    print(f"3. Support Ticket → Agent: {r['_routed_to']}, Ticket: {r.get('ticket_id')}")

    # 4. Schedule appointment
    r = orch.handle_task({"action": "create_appointment", "type": "consultation", "client": {"name": "Sarah"}, "preferred_time": "10:00"})
    print(f"4. Appointment → Agent: {r['_routed_to']}, Slot: {r.get('appointment', {}).get('assigned_slot')}")

    # 5. Create campaign
    r = orch.handle_task({"action": "create_campaign", "name": "Dubai Marina Launch", "type": "email", "target_audience": "investors"})
    print(f"5. Campaign → Agent: {r['_routed_to']}, Campaign: {r.get('campaign_id')}")

    # 6. Dashboard
    dash = orch.get_dashboard_data()
    print(f"\n=== Dashboard ===")
    print(f"Total tasks processed: {dash['total_tasks']}")
    print(f"Active agents: {len(dash['agents'])}")
    for a in dash["agents"]:
        print(f"  - {a['name']}: {a['stats']['tasks_handled']} tasks | capabilities: {a['capabilities']}")
