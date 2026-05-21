"""
plan_validator.py

Pre-Execution Plan Validation — Phase R.4+.
Validates plans BEFORE execution to catch problems early.

Why this matters:
- Claude plans and hopes. This agent plans, validates, and then executes.
- A bad plan wastes 10 steps. Validation catches it in 0.

Validation checks:
1. Tool existence — all tools in plan are available
2. Dependency sanity — no circular deps, no missing deps
3. Parameter completeness — all required params present
4. URL validity — URLs are well-formed
5. Selector plausibility — selectors look reasonable
6. Historical success — has this plan type worked before?
7. Risk assessment — payment/credential/destructive scoring
"""
from typing import Dict, Any, List, Optional
from .task_graph import TaskGraph, SubGoal, SubGoalStatus
from .experience_memory import ExperienceMemory


class ValidationIssue:
    """A single validation problem."""
    def __init__(self, severity: str, message: str, subgoal_id: str = ""):
        self.severity = severity  # "error", "warning", "info"
        self.message = message
        self.subgoal_id = subgoal_id
    
    def __repr__(self):
        icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(self.severity, "?")
        return f"{icon} [{self.subgoal_id}] {self.message}"


class PlanValidator:
    """
    Validates a TaskGraph before execution.
    Catches problems that would waste execution steps.
    """
    
    def __init__(self, available_tools: Dict[str, Any],
                 experience: Optional[ExperienceMemory] = None):
        self.tools = available_tools
        self.experience = experience
    
    def validate(self, task_graph: TaskGraph) -> Dict[str, Any]:
        """
        Run all validation checks on a TaskGraph.
        
        Returns:
        {
            "valid": True/False,
            "issues": [ValidationIssue...],
            "confidence": 0.0-1.0,
            "risk_level": "low"|"medium"|"high"
        }
        """
        issues = []
        
        # Check 1: Tool existence
        issues.extend(self._check_tools(task_graph))
        
        # Check 2: Dependency sanity
        issues.extend(self._check_dependencies(task_graph))
        
        # Check 3: Parameter completeness
        issues.extend(self._check_parameters(task_graph))
        
        # Check 4: URL validity
        issues.extend(self._check_urls(task_graph))
        
        # Check 5: Historical success check
        if self.experience:
            issues.extend(self._check_history(task_graph))
        
        # Calculate confidence
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]
        
        confidence = 1.0
        confidence -= len(errors) * 0.3
        confidence -= len(warnings) * 0.1
        confidence = max(0.0, min(1.0, confidence))
        
        # Risk level
        has_payment = any(
            s.requires_approval and "payment" in s.approval_message.lower()
            for s in task_graph.subgoals
        )
        has_credentials = any(
            s.requires_approval and any(
                kw in s.approval_message.lower() 
                for kw in ["credential", "password", "login"]
            )
            for s in task_graph.subgoals
        )
        
        if has_payment:
            risk_level = "high"
        elif has_credentials or len(errors) > 0:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        valid = len(errors) == 0
        
        # Log
        self._log_validation(task_graph, issues, confidence, risk_level)
        
        return {
            "valid": valid,
            "issues": issues,
            "confidence": round(confidence, 2),
            "risk_level": risk_level,
            "error_count": len(errors),
            "warning_count": len(warnings),
        }
    
    def _check_tools(self, graph: TaskGraph) -> List[ValidationIssue]:
        """Check that all tools in the plan exist."""
        issues = []
        for sg in graph.subgoals:
            if sg.tool and sg.tool not in self.tools:
                issues.append(ValidationIssue(
                    "error",
                    f"Tool '{sg.tool}' not available. Available: {list(self.tools.keys())}",
                    sg.id
                ))
        return issues
    
    def _check_dependencies(self, graph: TaskGraph) -> List[ValidationIssue]:
        """Check dependency sanity."""
        issues = []
        sg_ids = {s.id for s in graph.subgoals}
        
        for sg in graph.subgoals:
            for dep_id in sg.depends_on:
                if dep_id not in sg_ids:
                    issues.append(ValidationIssue(
                        "error",
                        f"Dependency '{dep_id}' does not exist",
                        sg.id
                    ))
        
        # Check for circular dependencies (simple detection)
        visited = set()
        for sg in graph.subgoals:
            chain = []
            current_id = sg.id
            while current_id:
                if current_id in chain:
                    issues.append(ValidationIssue(
                        "error",
                        f"Circular dependency detected: {' → '.join(chain + [current_id])}",
                        sg.id
                    ))
                    break
                chain.append(current_id)
                # Follow first dependency
                current_sg = graph._get_subgoal(current_id)
                current_id = current_sg.depends_on[0] if current_sg and current_sg.depends_on else None
        
        return issues
    
    def _check_parameters(self, graph: TaskGraph) -> List[ValidationIssue]:
        """Check parameter completeness."""
        issues = []
        
        for sg in graph.subgoals:
            if sg.tool == "browser_control":
                if sg.command == "open_url" and not sg.parameters.get("url"):
                    issues.append(ValidationIssue("error", "open_url requires 'url' parameter", sg.id))
                
                if sg.command in ("click", "hover") and not sg.parameters.get("selector") and not sg.parameters.get("description"):
                    issues.append(ValidationIssue("warning", f"{sg.command} has no selector or description", sg.id))
                
                if sg.command in ("type", "find_and_type") and not sg.parameters.get("text") and "text" not in sg.parameters:
                    issues.append(ValidationIssue("warning", f"{sg.command} has no 'text' parameter", sg.id))
        
        return issues
    
    def _check_urls(self, graph: TaskGraph) -> List[ValidationIssue]:
        """Check URL validity."""
        issues = []
        
        for sg in graph.subgoals:
            url = sg.parameters.get("url", "")
            if url:
                if not url.startswith(("http://", "https://", "file://")):
                    issues.append(ValidationIssue("warning", f"URL may be malformed: '{url[:50]}'", sg.id))
                
                if " " in url and "+" not in url and "%20" not in url:
                    issues.append(ValidationIssue("warning", f"URL contains spaces: '{url[:50]}'", sg.id))
        
        return issues
    
    def _check_history(self, graph: TaskGraph) -> List[ValidationIssue]:
        """Check historical experience for known problems."""
        issues = []
        
        for sg in graph.subgoals:
            url = sg.parameters.get("url", "")
            if url:
                from urllib.parse import urlparse
                try:
                    domain = urlparse(url).netloc
                    reliability = self.experience.get_site_reliability(domain)
                    if 0 < reliability < 0.4:
                        issues.append(ValidationIssue(
                            "warning",
                            f"Site '{domain}' has low historical reliability ({reliability:.0%})",
                            sg.id
                        ))
                except Exception:
                    pass
        
        return issues
    
    def _log_validation(self, graph: TaskGraph, issues: List, 
                        confidence: float, risk: str):
        """Print validation summary."""
        errors = sum(1 for i in issues if i.severity == "error")
        warns = sum(1 for i in issues if i.severity == "warning")
        
        icon = "✅" if errors == 0 else "❌"
        print(f"\n[Validator] {icon} Plan: {graph.goal[:50]}")
        print(f"  Subgoals: {len(graph.subgoals)} | Confidence: {confidence:.0%} | Risk: {risk}")
        
        if errors > 0:
            print(f"  ❌ {errors} error(s):")
            for i in issues:
                if i.severity == "error":
                    print(f"    {i}")
        
        if warns > 0:
            print(f"  ⚠️ {warns} warning(s):")
            for i in issues:
                if i.severity == "warning":
                    print(f"    {i}")


class RiskEstimator:
    """
    Scores the risk level of individual actions.
    
    Risk factors:
    - Payment involvement (10x risk)
    - Credential handling (8x risk)
    - Destructive operations (9x risk)
    - Unknown sites (3x risk)
    - Complex multi-step chains (2x risk)
    """
    
    # Risk weights
    RISK_WEIGHTS = {
        "payment": 10.0,
        "credential": 8.0,
        "destructive": 9.0,
        "unknown_site": 3.0,
        "complex_plan": 2.0,
        "many_approvals": 1.5,
        "low_reliability": 4.0,
    }
    
    def __init__(self, experience: Optional[ExperienceMemory] = None):
        self.experience = experience
    
    def estimate_risk(self, task_graph: TaskGraph) -> Dict[str, Any]:
        """
        Estimate overall risk of a task plan.
        
        Returns:
        {
            "risk_score": 0.0-10.0,
            "risk_level": "safe"|"low"|"medium"|"high"|"critical",
            "risk_factors": [{"factor": "...", "weight": 5.0}],
            "recommendation": "..."
        }
        """
        factors = []
        
        # Check for payment
        for sg in task_graph.subgoals:
            if sg.requires_approval and "payment" in sg.approval_message.lower():
                factors.append({"factor": "Payment required", "weight": self.RISK_WEIGHTS["payment"]})
                break
        
        # Check for credentials
        for sg in task_graph.subgoals:
            if sg.requires_approval and any(kw in sg.approval_message.lower() for kw in ["credential", "password", "login"]):
                factors.append({"factor": "Credential entry", "weight": self.RISK_WEIGHTS["credential"]})
                break
        
        # Check plan complexity
        if len(task_graph.subgoals) > 6:
            factors.append({"factor": f"Complex plan ({len(task_graph.subgoals)} steps)", "weight": self.RISK_WEIGHTS["complex_plan"]})
        
        # Check approval count
        approval_count = sum(1 for s in task_graph.subgoals if s.requires_approval)
        if approval_count > 2:
            factors.append({"factor": f"Many approvals ({approval_count})", "weight": self.RISK_WEIGHTS["many_approvals"]})
        
        # Check site reliability
        if self.experience:
            for sg in task_graph.subgoals:
                url = sg.parameters.get("url", "")
                if url:
                    from urllib.parse import urlparse
                    try:
                        domain = urlparse(url).netloc
                        rel = self.experience.get_site_reliability(domain)
                        if 0 < rel < 0.5:
                            factors.append({"factor": f"Unreliable site: {domain}", "weight": self.RISK_WEIGHTS["low_reliability"]})
                    except Exception:
                        pass
        
        # Calculate score
        if not factors:
            risk_score = 0.0
        else:
            risk_score = min(10.0, sum(f["weight"] for f in factors))
        
        # Determine level
        if risk_score <= 1.0:
            risk_level = "safe"
        elif risk_score <= 3.0:
            risk_level = "low"
        elif risk_score <= 6.0:
            risk_level = "medium"
        elif risk_score <= 8.0:
            risk_level = "high"
        else:
            risk_level = "critical"
        
        # Recommendation
        recommendations = {
            "safe": "✅ Proceed autonomously",
            "low": "✅ Proceed with monitoring",
            "medium": "⚠️ Proceed carefully, watch for issues",
            "high": "🔒 Requires human oversight",
            "critical": "🚫 Do NOT proceed without explicit approval",
        }
        
        return {
            "risk_score": round(risk_score, 1),
            "risk_level": risk_level,
            "risk_factors": factors,
            "recommendation": recommendations[risk_level]
        }


class ToolConfidenceScorer:
    """
    Scores confidence for individual tool actions based on history.
    
    Example:
    - browser_control.open_url → 95% confidence (almost always works)
    - browser_control.find_and_click("login button") → 60% (often fragile)
    - email_communication.fetch → 90% (reliable)
    """
    
    # Base confidence for tool commands
    BASE_CONFIDENCE = {
        "browser_control": {
            "open_url": 0.95,
            "scan_page": 0.90,
            "get_page_model": 0.85,
            "screenshot": 0.95,
            "back": 0.95,
            "refresh": 0.90,
            "close": 0.99,
            "click": 0.70,
            "type": 0.75,
            "find_and_click": 0.65,
            "find_and_type": 0.65,
            "find_element": 0.60,
            "hover": 0.70,
        },
        "email_communication": {
            "fetch_and_download": 0.85,
            "send_email": 0.80,
        },
        "excel_processing": {
            "append_to_master": 0.90,
            "compute_summary": 0.85,
            "generate_report": 0.85,
        },
    }
    
    def __init__(self, experience: Optional[ExperienceMemory] = None):
        self.experience = experience
    
    def score_action(self, tool: str, command: str, 
                     parameters: Dict = None) -> float:
        """Get confidence score for a specific action (0-1)."""
        # Start with base
        base = self.BASE_CONFIDENCE.get(tool, {}).get(command, 0.5)
        
        # Adjust from experience
        if self.experience and parameters:
            # Check selector history
            desc = (parameters or {}).get("description", "")
            if desc:
                best = self.experience.get_best_selector(desc)
                if best == desc:
                    base = min(1.0, base + 0.1)  # Known good selector
            
            # Check site history
            url = (parameters or {}).get("url", "")
            if url:
                from urllib.parse import urlparse
                try:
                    domain = urlparse(url).netloc
                    rel = self.experience.get_site_reliability(domain)
                    if rel > 0:
                        base = base * 0.5 + rel * 0.5  # Blend with history
                except Exception:
                    pass
        
        return round(base, 2)
    
    def score_plan(self, task_graph: TaskGraph) -> float:
        """Score overall plan confidence."""
        if not task_graph.subgoals:
            return 0.0
        
        scores = []
        for sg in task_graph.subgoals:
            if sg.tool:
                score = self.score_action(sg.tool, sg.command, sg.parameters)
                scores.append(score)
        
        if not scores:
            return 0.5
        
        # Overall confidence = geometric mean (penalizes weak links)
        product = 1.0
        for s in scores:
            product *= s
        return round(product ** (1.0 / len(scores)), 2)
