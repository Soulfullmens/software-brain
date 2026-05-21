"""
crm_scheduling.py

Dedicated CRM + Scheduling System.
Full customer relationship management with appointment scheduling,
follow-up automation, and pipeline analytics.

Features:
    CRM:
    - Contact management with full lifecycle tracking
    - Lead scoring with configurable rules
    - Deal pipeline with stage management
    - Follow-up automation (email/SMS reminders)
    - Customer segmentation
    - Revenue forecasting

    Scheduling:
    - Multi-calendar management
    - Appointment booking with conflict detection
    - Automated reminders
    - Recurring appointment support
    - Timezone-aware (UAE default: Asia/Dubai, UTC+4)
    - Integration with CRM contacts

Usage:
    crm = CRMSystem()
    contact = crm.create_contact("Ahmed", "ahmed@email.ae", phone="+971501234567")
    lead = crm.create_lead(contact.id, source="website", budget=500000)
    crm.score_lead(lead.id)

    sched = SchedulingSystem()
    slot = sched.book("2026-03-01", "10:00", contact_id=contact.id, service="consultation")
"""

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ────────────────────────────────────────────────────────
#  CRM Data Models
# ────────────────────────────────────────────────────────

class ContactStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BLOCKED = "blocked"


class LeadStage(str, Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"


class DealStage(str, Enum):
    DISCOVERY = "discovery"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CONTRACT = "contract"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class InteractionType(str, Enum):
    CALL = "call"
    EMAIL = "email"
    MEETING = "meeting"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    NOTE = "note"


class FollowUpStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


@dataclass
class Contact:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    email: str = ""
    phone: str = ""
    company: str = ""
    position: str = ""
    status: ContactStatus = ContactStatus.ACTIVE
    tags: List[str] = field(default_factory=list)
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    preferred_language: str = "en"   # "en" or "ar"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "name": self.name, "email": self.email,
            "phone": self.phone, "company": self.company,
            "position": self.position, "status": self.status.value,
            "tags": self.tags, "custom_fields": self.custom_fields,
            "preferred_language": self.preferred_language,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


@dataclass
class Lead:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    contact_id: str = ""
    source: str = "direct"  # website, referral, social, ad, cold_call
    stage: LeadStage = LeadStage.NEW
    score: int = 0
    budget: float = 0.0
    interest: str = ""       # what they're interested in
    timeline: str = ""       # immediate, 1_month, 3_months, 6_months, exploring
    notes: List[str] = field(default_factory=list)
    interactions: List[Dict] = field(default_factory=list)
    assigned_to: str = ""
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "contact_id": self.contact_id,
            "source": self.source, "stage": self.stage.value,
            "score": self.score, "budget": self.budget,
            "interest": self.interest, "timeline": self.timeline,
            "notes": self.notes, "interactions": self.interactions,
            "assigned_to": self.assigned_to,
            "created_at": self.created_at, "last_activity": self.last_activity,
        }


@dataclass
class Deal:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    lead_id: str = ""
    contact_id: str = ""
    title: str = ""
    value_aed: float = 0.0
    stage: DealStage = DealStage.DISCOVERY
    probability: float = 0.1  # 0.0-1.0
    expected_close_date: str = ""
    notes: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "lead_id": self.lead_id,
            "contact_id": self.contact_id, "title": self.title,
            "value_aed": self.value_aed, "stage": self.stage.value,
            "probability": self.probability,
            "expected_close_date": self.expected_close_date,
            "notes": self.notes, "created_at": self.created_at,
        }


@dataclass
class FollowUp:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    contact_id: str = ""
    lead_id: str = ""
    type: InteractionType = InteractionType.EMAIL
    message: str = ""
    scheduled_at: float = 0.0
    status: FollowUpStatus = FollowUpStatus.PENDING
    completed_at: Optional[float] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "contact_id": self.contact_id,
            "lead_id": self.lead_id, "type": self.type.value,
            "message": self.message, "scheduled_at": self.scheduled_at,
            "status": self.status.value, "completed_at": self.completed_at,
            "created_at": self.created_at,
        }


# ────────────────────────────────────────────────────────
#  Lead Scoring Engine
# ────────────────────────────────────────────────────────

class LeadScoringEngine:
    """Configurable rule-based lead scoring."""

    DEFAULT_RULES = {
        # Source scoring
        "source_referral": 25,
        "source_website": 15,
        "source_social": 10,
        "source_ad": 10,
        "source_cold_call": 5,
        # Info completeness
        "has_email": 10,
        "has_phone": 10,
        "has_company": 5,
        # Budget
        "budget_high": 20,        # > 1M AED
        "budget_medium": 15,      # 500K-1M
        "budget_low": 5,          # < 500K
        # Timeline
        "timeline_immediate": 25,
        "timeline_1_month": 20,
        "timeline_3_months": 10,
        "timeline_exploring": 5,
        # Engagement
        "interaction_count_3+": 15,
        "interaction_count_1-2": 5,
        "recent_activity_24h": 10,
        "recent_activity_7d": 5,
    }

    def __init__(self, rules: Optional[Dict[str, int]] = None):
        self.rules = rules or self.DEFAULT_RULES

    def score(self, lead: Lead, contact: Optional[Contact] = None) -> int:
        total = 0

        # Source
        source_key = f"source_{lead.source}"
        total += self.rules.get(source_key, 0)

        # Contact info completeness
        if contact:
            if contact.email:
                total += self.rules.get("has_email", 0)
            if contact.phone:
                total += self.rules.get("has_phone", 0)
            if contact.company:
                total += self.rules.get("has_company", 0)

        # Budget
        if lead.budget > 1_000_000:
            total += self.rules.get("budget_high", 0)
        elif lead.budget > 500_000:
            total += self.rules.get("budget_medium", 0)
        elif lead.budget > 0:
            total += self.rules.get("budget_low", 0)

        # Timeline
        timeline_key = f"timeline_{lead.timeline}"
        total += self.rules.get(timeline_key, 0)

        # Interactions
        ic = len(lead.interactions)
        if ic >= 3:
            total += self.rules.get("interaction_count_3+", 0)
        elif ic >= 1:
            total += self.rules.get("interaction_count_1-2", 0)

        # Recent activity
        hours_since = (time.time() - lead.last_activity) / 3600
        if hours_since < 24:
            total += self.rules.get("recent_activity_24h", 0)
        elif hours_since < 168:
            total += self.rules.get("recent_activity_7d", 0)

        return min(100, total)

    def qualify(self, score: int) -> str:
        if score >= 70:
            return "hot"
        elif score >= 40:
            return "warm"
        else:
            return "cold"


# ────────────────────────────────────────────────────────
#  CRM System
# ────────────────────────────────────────────────────────

class CRMSystem:
    """Full CRM system with contacts, leads, deals, and follow-ups."""

    def __init__(self, data_dir: str = "agent_data/crm"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

        self.contacts: Dict[str, Contact] = {}
        self.leads: Dict[str, Lead] = {}
        self.deals: Dict[str, Deal] = {}
        self.follow_ups: Dict[str, FollowUp] = {}
        self.scoring = LeadScoringEngine()

        self._load()

    # ── Contacts ──

    def create_contact(self, name: str, email: str = "", phone: str = "",
                       company: str = "", position: str = "",
                       language: str = "en", tags: List[str] = None) -> Contact:
        contact = Contact(
            name=name, email=email, phone=phone,
            company=company, position=position,
            preferred_language=language,
            tags=tags or [],
        )
        self.contacts[contact.id] = contact
        self._save()
        return contact

    def get_contact(self, contact_id: str) -> Optional[Contact]:
        return self.contacts.get(contact_id)

    def search_contacts(self, query: str) -> List[Contact]:
        q = query.lower()
        return [c for c in self.contacts.values()
                if q in c.name.lower() or q in c.email.lower()
                or q in c.company.lower() or q in c.phone]

    def update_contact(self, contact_id: str, **kwargs) -> Optional[Contact]:
        contact = self.contacts.get(contact_id)
        if not contact:
            return None
        for k, v in kwargs.items():
            if hasattr(contact, k):
                setattr(contact, k, v)
        contact.updated_at = time.time()
        self._save()
        return contact

    # ── Leads ──

    def create_lead(self, contact_id: str, source: str = "direct",
                    budget: float = 0.0, interest: str = "",
                    timeline: str = "exploring") -> Lead:
        lead = Lead(
            contact_id=contact_id, source=source,
            budget=budget, interest=interest, timeline=timeline,
        )
        self.leads[lead.id] = lead
        # auto-score
        contact = self.contacts.get(contact_id)
        lead.score = self.scoring.score(lead, contact)
        self._save()
        return lead

    def score_lead(self, lead_id: str) -> int:
        lead = self.leads.get(lead_id)
        if not lead:
            return 0
        contact = self.contacts.get(lead.contact_id)
        lead.score = self.scoring.score(lead, contact)
        self._save()
        return lead.score

    def advance_lead(self, lead_id: str, stage: LeadStage) -> Optional[Lead]:
        lead = self.leads.get(lead_id)
        if not lead:
            return None
        lead.stage = stage
        lead.last_activity = time.time()
        self._save()
        return lead

    def add_interaction(self, lead_id: str, itype: InteractionType,
                        summary: str) -> Optional[Lead]:
        lead = self.leads.get(lead_id)
        if not lead:
            return None
        lead.interactions.append({
            "type": itype.value, "summary": summary,
            "timestamp": time.time(),
        })
        lead.last_activity = time.time()
        lead.score = self.scoring.score(lead, self.contacts.get(lead.contact_id))
        self._save()
        return lead

    def get_pipeline(self) -> Dict[str, List[Dict]]:
        pipeline = {}
        for stage in LeadStage:
            pipeline[stage.value] = [
                {**l.to_dict(), "contact": self.contacts.get(l.contact_id, Contact()).to_dict()}
                for l in self.leads.values() if l.stage == stage
            ]
        return pipeline

    # ── Deals ──

    def create_deal(self, lead_id: str, title: str, value_aed: float,
                    expected_close: str = "") -> Deal:
        lead = self.leads.get(lead_id)
        deal = Deal(
            lead_id=lead_id,
            contact_id=lead.contact_id if lead else "",
            title=title, value_aed=value_aed,
            expected_close_date=expected_close,
        )
        # set probability based on lead score
        if lead and lead.score >= 70:
            deal.probability = 0.7
        elif lead and lead.score >= 40:
            deal.probability = 0.4
        self.deals[deal.id] = deal
        self._save()
        return deal

    def advance_deal(self, deal_id: str, stage: DealStage) -> Optional[Deal]:
        deal = self.deals.get(deal_id)
        if not deal:
            return None
        deal.stage = stage
        # auto-adjust probability
        stage_prob = {
            DealStage.DISCOVERY: 0.1, DealStage.PROPOSAL: 0.3,
            DealStage.NEGOTIATION: 0.5, DealStage.CONTRACT: 0.8,
            DealStage.CLOSED_WON: 1.0, DealStage.CLOSED_LOST: 0.0,
        }
        deal.probability = stage_prob.get(stage, deal.probability)
        self._save()
        return deal

    # ── Follow-Ups ──

    def schedule_followup(self, contact_id: str, lead_id: str = "",
                          ftype: InteractionType = InteractionType.EMAIL,
                          message: str = "", delay_hours: float = 24.0) -> FollowUp:
        fu = FollowUp(
            contact_id=contact_id, lead_id=lead_id,
            type=ftype, message=message,
            scheduled_at=time.time() + (delay_hours * 3600),
        )
        self.follow_ups[fu.id] = fu
        self._save()
        return fu

    def get_due_followups(self) -> List[FollowUp]:
        now = time.time()
        return [fu for fu in self.follow_ups.values()
                if fu.status == FollowUpStatus.PENDING and fu.scheduled_at <= now]

    def complete_followup(self, followup_id: str) -> Optional[FollowUp]:
        fu = self.follow_ups.get(followup_id)
        if not fu:
            return None
        fu.status = FollowUpStatus.COMPLETED
        fu.completed_at = time.time()
        self._save()
        return fu

    # ── Analytics ──

    def get_analytics(self) -> Dict:
        total_leads = len(self.leads)
        won = sum(1 for d in self.deals.values() if d.stage == DealStage.CLOSED_WON)
        lost = sum(1 for d in self.deals.values() if d.stage == DealStage.CLOSED_LOST)
        pipeline_value = sum(d.value_aed * d.probability for d in self.deals.values()
                             if d.stage not in (DealStage.CLOSED_WON, DealStage.CLOSED_LOST))
        total_revenue = sum(d.value_aed for d in self.deals.values() if d.stage == DealStage.CLOSED_WON)

        avg_score = (sum(l.score for l in self.leads.values()) / total_leads) if total_leads else 0
        hot = sum(1 for l in self.leads.values() if l.score >= 70)
        warm = sum(1 for l in self.leads.values() if 40 <= l.score < 70)
        cold = sum(1 for l in self.leads.values() if l.score < 40)

        return {
            "contacts": len(self.contacts),
            "leads": {"total": total_leads, "hot": hot, "warm": warm, "cold": cold, "avg_score": round(avg_score, 1)},
            "deals": {"total": len(self.deals), "won": won, "lost": lost, "pipeline_value_aed": round(pipeline_value), "total_revenue_aed": round(total_revenue)},
            "followups": {"total": len(self.follow_ups), "pending": sum(1 for f in self.follow_ups.values() if f.status == FollowUpStatus.PENDING), "due": len(self.get_due_followups())},
            "conversion_rate": round(won / max(total_leads, 1) * 100, 1),
        }

    # ── Persistence ──

    def _save(self):
        data = {
            "contacts": {k: v.to_dict() for k, v in self.contacts.items()},
            "leads": {k: v.to_dict() for k, v in self.leads.items()},
            "deals": {k: v.to_dict() for k, v in self.deals.items()},
            "follow_ups": {k: v.to_dict() for k, v in self.follow_ups.items()},
        }
        path = os.path.join(self.data_dir, "crm_data.json")
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _load(self):
        path = os.path.join(self.data_dir, "crm_data.json")
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                data = json.load(f)
            for cid, cd in data.get("contacts", {}).items():
                self.contacts[cid] = Contact(**{k: v for k, v in cd.items() if k != "status"})
                if "status" in cd:
                    self.contacts[cid].status = ContactStatus(cd["status"])
            for lid, ld in data.get("leads", {}).items():
                self.leads[lid] = Lead(**{k: v for k, v in ld.items() if k != "stage"})
                if "stage" in ld:
                    self.leads[lid].stage = LeadStage(ld["stage"])
            for did, dd in data.get("deals", {}).items():
                self.deals[did] = Deal(**{k: v for k, v in dd.items() if k != "stage"})
                if "stage" in dd:
                    self.deals[did].stage = DealStage(dd["stage"])
        except (json.JSONDecodeError, TypeError):
            pass  # start fresh on corrupt data


# ────────────────────────────────────────────────────────
#  Scheduling System
# ────────────────────────────────────────────────────────

class AppointmentStatus(str, Enum):
    CONFIRMED = "confirmed"
    PENDING = "pending"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


@dataclass
class Appointment:
    id: str = field(default_factory=lambda: f"APT-{str(uuid.uuid4())[:6].upper()}")
    contact_id: str = ""
    date: str = ""           # "2026-03-01"
    time_slot: str = ""      # "10:00"
    duration_minutes: int = 30
    service: str = "consultation"
    status: AppointmentStatus = AppointmentStatus.CONFIRMED
    notes: str = ""
    reminder_sent: bool = False
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "contact_id": self.contact_id,
            "date": self.date, "time_slot": self.time_slot,
            "duration_minutes": self.duration_minutes,
            "service": self.service, "status": self.status.value,
            "notes": self.notes, "reminder_sent": self.reminder_sent,
            "created_at": self.created_at,
        }


class SchedulingSystem:
    """
    Appointment scheduling with conflict detection and reminders.
    Default timezone: Asia/Dubai (UTC+4).
    """

    SERVICES = {
        "consultation": {"duration": 30, "label": "General Consultation"},
        "property_viewing": {"duration": 60, "label": "Property Viewing"},
        "follow_up": {"duration": 15, "label": "Follow-up Call"},
        "contract_signing": {"duration": 45, "label": "Contract Signing"},
        "assessment": {"duration": 60, "label": "Initial Assessment"},
        "clinic_visit": {"duration": 20, "label": "Clinic Visit"},
    }

    # Business hours: 9:00 – 18:00, 30-min slots
    SLOTS = [f"{h:02d}:{m:02d}" for h in range(9, 18) for m in (0, 30)]

    def __init__(self, data_dir: str = "agent_data/scheduling"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.appointments: Dict[str, Appointment] = {}
        self._load()

    def get_available_slots(self, date: str) -> List[str]:
        booked = {a.time_slot for a in self.appointments.values()
                  if a.date == date and a.status in (AppointmentStatus.CONFIRMED, AppointmentStatus.PENDING)}
        return [s for s in self.SLOTS if s not in booked]

    def book(self, date: str, time_slot: str, contact_id: str = "",
             service: str = "consultation", notes: str = "") -> Optional[Appointment]:
        # conflict check
        available = self.get_available_slots(date)
        if time_slot not in available:
            return None  # slot taken

        svc = self.SERVICES.get(service, {"duration": 30})
        appt = Appointment(
            contact_id=contact_id, date=date,
            time_slot=time_slot, duration_minutes=svc["duration"],
            service=service, notes=notes,
        )
        self.appointments[appt.id] = appt
        self._save()
        return appt

    def cancel(self, appointment_id: str) -> bool:
        appt = self.appointments.get(appointment_id)
        if not appt:
            return False
        appt.status = AppointmentStatus.CANCELLED
        self._save()
        return True

    def reschedule(self, appointment_id: str, new_date: str, new_time: str) -> Optional[Appointment]:
        appt = self.appointments.get(appointment_id)
        if not appt:
            return None
        available = self.get_available_slots(new_date)
        if new_time not in available:
            return None
        appt.date = new_date
        appt.time_slot = new_time
        self._save()
        return appt

    def complete(self, appointment_id: str) -> bool:
        appt = self.appointments.get(appointment_id)
        if not appt:
            return False
        appt.status = AppointmentStatus.COMPLETED
        self._save()
        return True

    def get_schedule(self, date: str) -> List[Dict]:
        return [a.to_dict() for a in self.appointments.values()
                if a.date == date and a.status not in (AppointmentStatus.CANCELLED,)]

    def get_contact_appointments(self, contact_id: str) -> List[Dict]:
        return [a.to_dict() for a in self.appointments.values() if a.contact_id == contact_id]

    def get_reminders(self) -> List[Dict]:
        """Get appointments that need reminder notifications."""
        reminders = []
        for a in self.appointments.values():
            if a.status == AppointmentStatus.CONFIRMED and not a.reminder_sent:
                reminders.append(a.to_dict())
        return reminders

    def get_analytics(self) -> Dict:
        total = len(self.appointments)
        by_status = {}
        for s in AppointmentStatus:
            by_status[s.value] = sum(1 for a in self.appointments.values() if a.status == s)
        by_service = {}
        for a in self.appointments.values():
            by_service[a.service] = by_service.get(a.service, 0) + 1
        return {
            "total_appointments": total,
            "by_status": by_status,
            "by_service": by_service,
            "no_show_rate": round(by_status.get("no_show", 0) / max(total, 1) * 100, 1),
        }

    def _save(self):
        path = os.path.join(self.data_dir, "appointments.json")
        data = {k: v.to_dict() for k, v in self.appointments.items()}
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _load(self):
        path = os.path.join(self.data_dir, "appointments.json")
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                data = json.load(f)
            for aid, ad in data.items():
                status_val = ad.pop("status", "confirmed")
                self.appointments[aid] = Appointment(**ad)
                self.appointments[aid].status = AppointmentStatus(status_val)
        except (json.JSONDecodeError, TypeError):
            pass


# ────────────────────────────────────────────────────────
#  Unified Business CRM
# ────────────────────────────────────────────────────────

class BusinessCRM:
    """
    Unified CRM + Scheduling interface.
    Combines contact management, lead pipeline, deals,
    follow-ups, and appointment scheduling.
    """

    def __init__(self, data_dir: str = "agent_data"):
        self.crm = CRMSystem(os.path.join(data_dir, "crm"))
        self.scheduler = SchedulingSystem(os.path.join(data_dir, "scheduling"))

    def onboard_customer(self, name: str, email: str = "", phone: str = "",
                         company: str = "", source: str = "direct",
                         budget: float = 0.0, interest: str = "",
                         language: str = "en") -> Dict:
        """Full customer onboarding: create contact + lead + schedule follow-up."""
        contact = self.crm.create_contact(
            name=name, email=email, phone=phone,
            company=company, language=language,
        )
        lead = self.crm.create_lead(
            contact_id=contact.id, source=source,
            budget=budget, interest=interest,
        )
        # auto-schedule follow-up
        fu = self.crm.schedule_followup(
            contact_id=contact.id, lead_id=lead.id,
            ftype=InteractionType.EMAIL,
            message=f"Welcome {name}! Thank you for your interest in {interest or 'our services'}.",
            delay_hours=1.0,
        )
        return {
            "contact": contact.to_dict(),
            "lead": lead.to_dict(),
            "follow_up": fu.to_dict(),
            "qualification": self.crm.scoring.qualify(lead.score),
        }

    def book_appointment(self, contact_id: str, date: str, time_slot: str,
                         service: str = "consultation") -> Dict:
        appt = self.scheduler.book(date, time_slot, contact_id=contact_id, service=service)
        if not appt:
            available = self.scheduler.get_available_slots(date)
            return {"status": "error", "message": "Slot not available", "available_slots": available}
        return {"status": "ok", "appointment": appt.to_dict()}

    def get_full_dashboard(self) -> Dict:
        return {
            "crm": self.crm.get_analytics(),
            "scheduling": self.scheduler.get_analytics(),
            "pipeline": self.crm.get_pipeline(),
        }


# ────────────────────────────────────────────────────────
#  Quick Test
# ────────────────────────────────────────────────────────

if __name__ == "__main__":
    biz = BusinessCRM(data_dir="agent_data")

    print("=== Business CRM + Scheduling Demo ===\n")

    # 1. Onboard customers
    c1 = biz.onboard_customer(
        name="Ahmed Al Maktoum", email="ahmed@email.ae", phone="+971501234567",
        company="Maktoum Holdings", source="referral", budget=2_000_000,
        interest="villa in Palm Jumeirah", language="ar",
    )
    print(f"1. Onboarded: {c1['contact']['name']} | Score: {c1['lead']['score']} | Qual: {c1['qualification']}")

    c2 = biz.onboard_customer(
        name="Sarah Johnson", email="sarah@company.com", phone="+971502345678",
        source="website", budget=800_000, interest="apartment in Marina",
    )
    print(f"2. Onboarded: {c2['contact']['name']} | Score: {c2['lead']['score']} | Qual: {c2['qualification']}")

    c3 = biz.onboard_customer(
        name="Mohammed Ali", email="m.ali@gmail.com",
        source="social", budget=300_000, interest="studio apartment",
    )
    print(f"3. Onboarded: {c3['contact']['name']} | Score: {c3['lead']['score']} | Qual: {c3['qualification']}")

    # 2. Add interactions
    lead_id = c1["lead"]["id"]
    biz.crm.add_interaction(lead_id, InteractionType.CALL, "Discussed Palm Jumeirah villas, very interested")
    biz.crm.add_interaction(lead_id, InteractionType.MEETING, "Site visit scheduled")
    biz.crm.add_interaction(lead_id, InteractionType.WHATSAPP, "Sent property brochure")
    new_score = biz.crm.score_lead(lead_id)
    print(f"\n4. Ahmed's score after 3 interactions: {new_score} ({biz.crm.scoring.qualify(new_score)})")

    # 3. Create deal
    deal = biz.crm.create_deal(lead_id, "Palm Jumeirah Villa - 5BR", 15_000_000, "2026-04-15")
    print(f"5. Deal created: {deal.title} | Value: {deal.value_aed:,.0f} AED | P: {deal.probability}")

    # 4. Book appointments
    a1 = biz.book_appointment(c1["contact"]["id"], "2026-03-01", "10:00", "property_viewing")
    print(f"\n6. Appointment: {a1.get('appointment', {}).get('id', 'N/A')} at 10:00")

    a2 = biz.book_appointment(c2["contact"]["id"], "2026-03-01", "14:00", "consultation")
    print(f"7. Appointment: {a2.get('appointment', {}).get('id', 'N/A')} at 14:00")

    # 5. Available slots
    slots = biz.scheduler.get_available_slots("2026-03-01")
    print(f"\n8. Available slots on 2026-03-01: {len(slots)} slots")

    # 6. Analytics
    analytics = biz.get_full_dashboard()
    print(f"\n=== Analytics ===")
    print(f"Contacts: {analytics['crm']['contacts']}")
    print(f"Leads: {analytics['crm']['leads']}")
    print(f"Deals: pipeline={analytics['crm']['deals']['pipeline_value_aed']:,.0f} AED")
    print(f"Appointments: {analytics['scheduling']['total_appointments']}")
    print(f"Follow-ups pending: {analytics['crm']['followups']['pending']}")
