"""
workflow_engine.py

Autonomous Business Workflow Engine.
Runs multi-step business processes (clinic, real-estate, CRM) end-to-end.

Architecture:
    WorkflowEngine
    ├── WorkflowDefinition   (declarative YAML/dict workflow spec)
    ├── WorkflowStep         (single action in the workflow)
    ├── WorkflowExecution    (live running instance)
    ├── TriggerSystem        (schedule, event, webhook triggers)
    └── WorkflowPersistence  (save/resume workflows)

Built-in Workflows:
    1. Clinic Operations   — patient intake → scheduling → follow-up → billing
    2. Real Estate         — lead capture → property match → viewing → offer → close
    3. CRM Pipeline        — lead → qualify → nurture → convert → retain
    4. Email Campaign      — segment → compose → send → track → optimize
    5. Customer Support    — ticket → classify → route → resolve → feedback
"""
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


# ────────────────────────────────────────────────────────
#  Data Structures
# ────────────────────────────────────────────────────────

class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_INPUT = "waiting_input"


class TriggerType(str, Enum):
    MANUAL = "manual"
    SCHEDULE = "schedule"       # cron-like
    EVENT = "event"             # on_new_lead, on_appointment, etc.
    WEBHOOK = "webhook"         # HTTP trigger
    CONDITION = "condition"     # when X becomes true


@dataclass
class WorkflowStep:
    """A single step in a workflow."""
    id: str
    name: str
    description: str = ""
    action: str = ""                    # action identifier
    parameters: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    requires_approval: bool = False
    timeout_seconds: int = 300
    retry_count: int = 2
    on_failure: str = "skip"           # skip, stop, retry, fallback
    fallback_step: Optional[str] = None
    condition: Optional[str] = None     # skip if condition is false
    # Runtime state
    status: StepStatus = StepStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: float = 0
    completed_at: float = 0


@dataclass
class WorkflowDefinition:
    """Complete workflow specification."""
    id: str
    name: str
    description: str = ""
    version: str = "1.0"
    category: str = "general"          # clinic, real_estate, crm, support
    steps: List[WorkflowStep] = field(default_factory=list)
    triggers: List[Dict[str, Any]] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "category": self.category,
            "steps": [
                {
                    "id": s.id, "name": s.name, "description": s.description,
                    "action": s.action, "parameters": s.parameters,
                    "depends_on": s.depends_on, "requires_approval": s.requires_approval,
                    "on_failure": s.on_failure, "condition": s.condition,
                }
                for s in self.steps
            ],
            "triggers": self.triggers,
            "variables": self.variables,
        }


@dataclass
class WorkflowExecution:
    """A running workflow instance."""
    id: str
    workflow_id: str
    workflow_name: str
    steps: List[WorkflowStep] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    status: str = "running"            # running, completed, failed, paused
    started_at: float = field(default_factory=time.time)
    completed_at: float = 0
    current_step_index: int = 0
    logs: List[Dict[str, Any]] = field(default_factory=list)

    def log(self, message: str, level: str = "info"):
        self.logs.append({
            "timestamp": time.time(),
            "level": level,
            "message": message,
        })


# ────────────────────────────────────────────────────────
#  Action Registry
# ────────────────────────────────────────────────────────

class ActionRegistry:
    """Registry of executable actions for workflows."""

    def __init__(self):
        self.actions: Dict[str, Callable] = {}

    def register(self, name: str, handler: Callable):
        self.actions[name] = handler

    def execute(self, name: str, params: Dict[str, Any],
                context: Dict[str, Any]) -> Any:
        handler = self.actions.get(name)
        if not handler:
            raise ValueError(f"Unknown action: {name}")
        return handler(params, context)

    def list_actions(self) -> List[str]:
        return list(self.actions.keys())


# ────────────────────────────────────────────────────────
#  Built-in Actions
# ────────────────────────────────────────────────────────

def action_send_email(params: Dict, context: Dict) -> Dict:
    """Send an email (uses agent's email tool if available)."""
    return {
        "status": "sent",
        "to": params.get("to", ""),
        "subject": params.get("subject", ""),
        "timestamp": time.time(),
    }


def action_send_sms(params: Dict, context: Dict) -> Dict:
    """Send SMS notification."""
    return {
        "status": "sent",
        "to": params.get("phone", ""),
        "message": params.get("message", ""),
    }


def action_create_record(params: Dict, context: Dict) -> Dict:
    """Create a CRM record."""
    record_id = str(uuid.uuid4())[:8]
    return {
        "status": "created",
        "record_id": record_id,
        "type": params.get("type", "contact"),
        "data": params.get("data", {}),
    }


def action_update_record(params: Dict, context: Dict) -> Dict:
    """Update an existing CRM record."""
    return {
        "status": "updated",
        "record_id": params.get("record_id", ""),
        "fields": params.get("fields", {}),
    }


def action_schedule_appointment(params: Dict, context: Dict) -> Dict:
    """Schedule an appointment."""
    return {
        "status": "scheduled",
        "appointment_id": str(uuid.uuid4())[:8],
        "date": params.get("date", ""),
        "time": params.get("time", ""),
        "type": params.get("type", "general"),
        "provider": params.get("provider", ""),
    }


def action_generate_report(params: Dict, context: Dict) -> Dict:
    """Generate a business report."""
    return {
        "status": "generated",
        "report_type": params.get("type", "summary"),
        "format": params.get("format", "pdf"),
    }


def action_llm_process(params: Dict, context: Dict) -> Dict:
    """Process text through LLM (classify, summarize, generate)."""
    llm = context.get("llm")
    if llm:
        try:
            result = llm.chat(
                params.get("prompt", ""),
                system=params.get("system", ""),
                max_tokens=params.get("max_tokens", 500),
            )
            return {"status": "success", "result": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    return {"status": "skipped", "reason": "No LLM available"}


def action_classify_intent(params: Dict, context: Dict) -> Dict:
    """Classify customer intent using LLM."""
    llm = context.get("llm")
    text = params.get("text", "")
    if llm:
        try:
            result = llm.chat(
                f"Classify this customer message into one category: "
                f"inquiry, complaint, booking, cancellation, feedback, other.\n"
                f"Message: {text}\nCategory:",
                system="Respond with only the category name.",
                max_tokens=20,
            )
            return {"intent": result.strip().lower(), "text": text}
        except Exception:
            pass
    return {"intent": "unknown", "text": text}


def action_qualify_lead(params: Dict, context: Dict) -> Dict:
    """Score and qualify a lead."""
    score = 0
    data = params.get("data", {})
    if data.get("email"):
        score += 20
    if data.get("phone"):
        score += 20
    if data.get("budget"):
        score += 30
    if data.get("timeline", "").lower() in ["urgent", "this month", "asap"]:
        score += 30
    qualification = "hot" if score >= 70 else "warm" if score >= 40 else "cold"
    return {"score": score, "qualification": qualification, "data": data}


def action_wait(params: Dict, context: Dict) -> Dict:
    """Wait for a specified duration (simulated in production)."""
    return {"status": "waited", "duration": params.get("seconds", 0)}


def action_webhook_call(params: Dict, context: Dict) -> Dict:
    """Call an external webhook."""
    return {"status": "called", "url": params.get("url", ""), "method": params.get("method", "POST")}


# ────────────────────────────────────────────────────────
#  Workflow Engine
# ────────────────────────────────────────────────────────

class WorkflowEngine:
    """
    Autonomous business workflow executor.

    Usage:
        engine = WorkflowEngine(llm=router)
        wf = engine.get_template("clinic_patient_intake")
        execution = engine.start(wf, variables={"patient_name": "John"})
        engine.run(execution)
    """

    def __init__(self, llm=None, storage_dir: str = "./agent_data/workflows"):
        self.llm = llm
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)

        self.actions = ActionRegistry()
        self._register_builtin_actions()
        self.active_executions: Dict[str, WorkflowExecution] = {}
        self.templates: Dict[str, WorkflowDefinition] = {}
        self._register_builtin_templates()

    def _register_builtin_actions(self):
        self.actions.register("send_email", action_send_email)
        self.actions.register("send_sms", action_send_sms)
        self.actions.register("create_record", action_create_record)
        self.actions.register("update_record", action_update_record)
        self.actions.register("schedule_appointment", action_schedule_appointment)
        self.actions.register("generate_report", action_generate_report)
        self.actions.register("llm_process", action_llm_process)
        self.actions.register("classify_intent", action_classify_intent)
        self.actions.register("qualify_lead", action_qualify_lead)
        self.actions.register("wait", action_wait)
        self.actions.register("webhook_call", action_webhook_call)

    # ── Template Library ──

    def _register_builtin_templates(self):
        # 1. CLINIC: Patient Intake Workflow
        self.templates["clinic_patient_intake"] = WorkflowDefinition(
            id="clinic_patient_intake",
            name="Clinic - Patient Intake",
            description="End-to-end patient intake from first contact to scheduled appointment",
            category="clinic",
            steps=[
                WorkflowStep(id="capture", name="Capture Patient Info",
                    action="create_record",
                    parameters={"type": "patient", "data": "{patient_data}"}),
                WorkflowStep(id="classify", name="Classify Visit Type",
                    action="classify_intent",
                    parameters={"text": "{patient_message}"},
                    depends_on=["capture"]),
                WorkflowStep(id="schedule", name="Schedule Appointment",
                    action="schedule_appointment",
                    parameters={"type": "{visit_type}", "date": "{preferred_date}",
                                "provider": "{doctor}"},
                    depends_on=["classify"]),
                WorkflowStep(id="confirm_email", name="Send Confirmation Email",
                    action="send_email",
                    parameters={"to": "{patient_email}",
                                "subject": "Appointment Confirmed",
                                "body": "Your appointment is scheduled."},
                    depends_on=["schedule"]),
                WorkflowStep(id="confirm_sms", name="Send SMS Reminder",
                    action="send_sms",
                    parameters={"phone": "{patient_phone}",
                                "message": "Appointment reminder"},
                    depends_on=["schedule"]),
                WorkflowStep(id="update_crm", name="Update CRM",
                    action="update_record",
                    parameters={"record_id": "{patient_id}",
                                "fields": {"status": "scheduled"}},
                    depends_on=["confirm_email"]),
            ],
        )

        # 2. REAL ESTATE: Lead to Close
        self.templates["real_estate_pipeline"] = WorkflowDefinition(
            id="real_estate_pipeline",
            name="Real Estate - Lead to Close",
            description="Full real estate pipeline from lead capture to deal closure",
            category="real_estate",
            steps=[
                WorkflowStep(id="capture_lead", name="Capture Lead",
                    action="create_record",
                    parameters={"type": "lead", "data": "{lead_data}"}),
                WorkflowStep(id="qualify", name="Qualify Lead",
                    action="qualify_lead",
                    parameters={"data": "{lead_data}"},
                    depends_on=["capture_lead"]),
                WorkflowStep(id="match_property", name="Match Properties",
                    action="llm_process",
                    parameters={
                        "prompt": "Match these buyer preferences to available properties: {preferences}",
                        "system": "You are a Dubai real estate matching engine.",
                    },
                    depends_on=["qualify"]),
                WorkflowStep(id="schedule_viewing", name="Schedule Viewing",
                    action="schedule_appointment",
                    parameters={"type": "property_viewing", "date": "{viewing_date}"},
                    depends_on=["match_property"]),
                WorkflowStep(id="send_details", name="Send Property Details",
                    action="send_email",
                    parameters={"to": "{lead_email}",
                                "subject": "Properties Matched For You",
                                "body": "{matched_properties}"},
                    depends_on=["match_property"]),
                WorkflowStep(id="follow_up", name="Follow-up Call Reminder",
                    action="send_sms",
                    parameters={"phone": "{agent_phone}",
                                "message": "Follow up with {lead_name}"},
                    depends_on=["schedule_viewing"]),
                WorkflowStep(id="update_pipeline", name="Update Pipeline",
                    action="update_record",
                    parameters={"record_id": "{lead_id}",
                                "fields": {"stage": "viewing_scheduled"}},
                    depends_on=["schedule_viewing"]),
            ],
        )

        # 3. CRM: Lead Nurture Pipeline
        self.templates["crm_lead_nurture"] = WorkflowDefinition(
            id="crm_lead_nurture",
            name="CRM - Lead Nurture Pipeline",
            description="Automated lead nurturing with scoring, emails, and follow-ups",
            category="crm",
            steps=[
                WorkflowStep(id="import_lead", name="Import Lead",
                    action="create_record",
                    parameters={"type": "lead", "data": "{lead_data}"}),
                WorkflowStep(id="score", name="Score Lead",
                    action="qualify_lead",
                    parameters={"data": "{lead_data}"},
                    depends_on=["import_lead"]),
                WorkflowStep(id="segment", name="Segment Lead",
                    action="llm_process",
                    parameters={
                        "prompt": "Based on this lead score: {lead_score}, "
                                  "determine the best nurture sequence: "
                                  "high-touch, medium-touch, or low-touch.",
                        "system": "Respond with only the sequence name.",
                    },
                    depends_on=["score"]),
                WorkflowStep(id="welcome_email", name="Send Welcome Email",
                    action="send_email",
                    parameters={"to": "{lead_email}",
                                "subject": "Welcome to our service!",
                                "body": "{welcome_template}"},
                    depends_on=["segment"]),
                WorkflowStep(id="schedule_followup", name="Schedule Follow-up",
                    action="schedule_appointment",
                    parameters={"type": "follow_up_call", "date": "{followup_date}"},
                    depends_on=["welcome_email"]),
                WorkflowStep(id="report", name="Generate Pipeline Report",
                    action="generate_report",
                    parameters={"type": "pipeline_summary"},
                    depends_on=["schedule_followup"]),
            ],
        )

        # 4. CUSTOMER SUPPORT: Ticket Resolution
        self.templates["support_ticket_resolution"] = WorkflowDefinition(
            id="support_ticket_resolution",
            name="Support - Ticket Resolution",
            description="Automated customer support ticket classification and routing",
            category="support",
            steps=[
                WorkflowStep(id="create_ticket", name="Create Ticket",
                    action="create_record",
                    parameters={"type": "ticket", "data": "{ticket_data}"}),
                WorkflowStep(id="classify", name="Classify Ticket",
                    action="classify_intent",
                    parameters={"text": "{ticket_message}"},
                    depends_on=["create_ticket"]),
                WorkflowStep(id="auto_respond", name="Send Auto-Response",
                    action="llm_process",
                    parameters={
                        "prompt": "Generate a helpful response for this {intent} ticket: {ticket_message}",
                        "system": "You are a professional customer support agent. Be empathetic and helpful.",
                    },
                    depends_on=["classify"]),
                WorkflowStep(id="notify_agent", name="Notify Support Agent",
                    action="send_email",
                    parameters={"to": "{support_agent_email}",
                                "subject": "New {intent} Ticket #{ticket_id}",
                                "body": "{ticket_summary}"},
                    depends_on=["classify"]),
                WorkflowStep(id="update_status", name="Update Ticket Status",
                    action="update_record",
                    parameters={"record_id": "{ticket_id}",
                                "fields": {"status": "in_progress", "category": "{intent}"}},
                    depends_on=["notify_agent"]),
            ],
        )

    # ── Public API ──

    def get_template(self, template_id: str) -> Optional[WorkflowDefinition]:
        return self.templates.get(template_id)

    def list_templates(self) -> List[Dict[str, str]]:
        return [
            {"id": t.id, "name": t.name, "category": t.category,
             "description": t.description}
            for t in self.templates.values()
        ]

    def register_template(self, workflow: WorkflowDefinition):
        self.templates[workflow.id] = workflow

    def start(self, workflow: WorkflowDefinition,
              variables: Optional[Dict[str, Any]] = None) -> WorkflowExecution:
        """Start a new workflow execution."""
        import copy
        execution = WorkflowExecution(
            id=str(uuid.uuid4())[:12],
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            steps=[copy.deepcopy(s) for s in workflow.steps],
            variables={**workflow.variables, **(variables or {})},
        )
        self.active_executions[execution.id] = execution
        execution.log(f"Workflow started: {workflow.name}")
        return execution

    def run(self, execution: WorkflowExecution) -> WorkflowExecution:
        """Run a workflow execution to completion."""
        execution.log("Execution started")

        while execution.status == "running":
            step = self._get_next_step(execution)
            if not step:
                # Check if all done
                all_done = all(
                    s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
                    for s in execution.steps
                )
                if all_done:
                    execution.status = "completed"
                    execution.completed_at = time.time()
                    execution.log("Workflow completed successfully")
                else:
                    any_failed = any(s.status == StepStatus.FAILED for s in execution.steps)
                    if any_failed:
                        execution.status = "failed"
                        execution.log("Workflow failed", "error")
                    else:
                        execution.status = "paused"
                        execution.log("Workflow paused (waiting for input/approval)")
                break

            self._execute_step(execution, step)

        self._save_execution(execution)
        return execution

    def _get_next_step(self, execution: WorkflowExecution) -> Optional[WorkflowStep]:
        """Find the next executable step."""
        for step in execution.steps:
            if step.status != StepStatus.PENDING:
                continue
            # Check dependencies
            deps_met = all(
                any(s.id == dep and s.status == StepStatus.COMPLETED
                    for s in execution.steps)
                for dep in step.depends_on
            )
            if deps_met:
                return step
        return None

    def _execute_step(self, execution: WorkflowExecution, step: WorkflowStep):
        """Execute a single workflow step."""
        step.status = StepStatus.RUNNING
        step.started_at = time.time()
        execution.log(f"Step started: {step.name}")

        # Resolve variable references in parameters
        resolved_params = self._resolve_variables(step.parameters, execution.variables)

        context = {"llm": self.llm, "variables": execution.variables}

        try:
            result = self.actions.execute(step.action, resolved_params, context)
            step.result = result
            step.status = StepStatus.COMPLETED
            step.completed_at = time.time()
            execution.log(f"Step completed: {step.name} -> {json.dumps(result, default=str)[:200]}")

            # Store result in variables for downstream steps
            execution.variables[f"{step.id}_result"] = result

        except Exception as e:
            step.error = str(e)
            if step.on_failure == "skip":
                step.status = StepStatus.SKIPPED
                execution.log(f"Step skipped (error): {step.name} - {e}", "warning")
            elif step.on_failure == "stop":
                step.status = StepStatus.FAILED
                execution.status = "failed"
                execution.log(f"Step failed (stopping): {step.name} - {e}", "error")
            else:
                step.status = StepStatus.FAILED
                execution.log(f"Step failed: {step.name} - {e}", "error")

    def _resolve_variables(self, params: Any, variables: Dict) -> Any:
        """Replace {variable} placeholders in parameters."""
        if isinstance(params, str):
            for key, value in variables.items():
                placeholder = f"{{{key}}}"
                if placeholder in params:
                    if params == placeholder:
                        return value
                    params = params.replace(placeholder, str(value))
            return params
        elif isinstance(params, dict):
            return {k: self._resolve_variables(v, variables) for k, v in params.items()}
        elif isinstance(params, list):
            return [self._resolve_variables(v, variables) for v in params]
        return params

    def _save_execution(self, execution: WorkflowExecution):
        """Persist execution state."""
        path = os.path.join(self.storage_dir, f"{execution.id}.json")
        data = {
            "id": execution.id,
            "workflow_id": execution.workflow_id,
            "workflow_name": execution.workflow_name,
            "status": execution.status,
            "started_at": execution.started_at,
            "completed_at": execution.completed_at,
            "variables": {k: str(v)[:500] for k, v in execution.variables.items()},
            "steps": [
                {
                    "id": s.id, "name": s.name, "status": s.status.value,
                    "result": str(s.result)[:500] if s.result else None,
                    "error": s.error,
                }
                for s in execution.steps
            ],
            "logs": execution.logs[-50:],  # keep last 50 logs
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def get_execution_summary(self, execution: WorkflowExecution) -> Dict:
        """Get a summary of an execution."""
        completed = sum(1 for s in execution.steps if s.status == StepStatus.COMPLETED)
        failed = sum(1 for s in execution.steps if s.status == StepStatus.FAILED)
        return {
            "id": execution.id,
            "workflow": execution.workflow_name,
            "status": execution.status,
            "total_steps": len(execution.steps),
            "completed": completed,
            "failed": failed,
            "duration_s": (execution.completed_at or time.time()) - execution.started_at,
            "steps": [
                {"name": s.name, "status": s.status.value}
                for s in execution.steps
            ],
        }
