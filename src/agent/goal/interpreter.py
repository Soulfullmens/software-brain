"""
interpreter.py

The 'Broca's Area' of the Agent.
Converts Natural Language Goals -> Structured GoalPlans.
Implements the 3-Tier Strategy:
1. Deterministic Patterns (Fast, Reliable)
2. Local LLM (Flexible) [Mocked for MVP]
3. Clarification Loop (Safety) [Via Missing Info]
"""
import re
from typing import Dict, Any, Optional
from .schema import GoalPlan

class GoalInterpreter:
    def interpret(self, text: str) -> GoalPlan:
        """
        Main entry point.
        text: "Open the sales report and email it to bob"
        returns: GoalPlan(...)
        """
        # 1. Tier 1: Pattern Engine
        plan = self._pattern_engine(text)
        if plan.confidence > 0.8:
            return plan
            
        # 2. Tier 2: Local LLM Fallback (Mocked for MVP)
        # In Phase R.3, this calls Ollama/Llama 3.2
        plan = self._llm_fallback(text)
        
        return plan

    def _pattern_engine(self, text: str) -> GoalPlan:
        text_lower = text.lower()
        
        # Intent: OPEN_FILE
        if "open" in text_lower:
            # Extract filename (simple heuristic: word segments with extension, no spaces for MVP safety)
            # Regex: Word boundary, alphanumeric/dashes/underscores, dot, 3-4 letter extension
            match = re.search(r'\b[\w\-_]+\.[a-z]{3,4}\b', text, re.IGNORECASE)
            filename = match.group(0).strip() if match else None
            
            return GoalPlan(
                intent="OPEN_FILE",
                entities={"filename": filename},
                actions=["minimize_windows", "locate_file", "double_click_file"],
                missing_info=["filename"] if not filename else [],
                confidence=0.9 if filename else 0.5,
                requires_approval=False,
                reasoning="Detected 'open' keyword and file extension."
            )

        # Intent: RUN_SHELL
        if "run" in text_lower or "exec" in text_lower:
             # Extract command: Remove leading "run", "exec", "execute"
             # Regex: Start of string, optional whitespace, verb, whitespace, capture group
             match = re.search(r'^\s*(?:run|exec|execute)\s+(.+)$', text, re.IGNORECASE)
             cmd = match.group(1).strip() if match else text
             
             return GoalPlan(
                intent="RUN_SHELL",
                entities={"command": cmd}, 
                actions=["open_terminal", "type_command"],
                confidence=0.9,
                requires_approval=True,
                reasoning="Detected execution keyword."
             )

        # Intent: FETCH_EMAIL
        if "email" in text_lower and ("check" in text_lower or "read" in text_lower or "fetch" in text_lower or "get" in text_lower):
            # Extract subject filter?
            # heuristic: "check email for Sales Report"
            subject_filter = None
            if "for" in text_lower:
                parts = text.split("for")
                if len(parts) > 1:
                    subject_filter = parts[1].strip()
            
            return GoalPlan(
                intent="FETCH_EMAIL",
                entities={"subject_filter": subject_filter} if subject_filter else {},
                actions=["email_communication.read_unread"],
                confidence=0.85,
                requires_approval=False,
                reasoning="Detected email fetch request."
            )

        # Intent: SEND_EMAIL
        if "email" in text_lower and ("send" in text_lower or "mail" in text_lower):
            # Extract recipient? "send email to boss"
            to_addr = "manager@corp.com" # Mock default
            if "to" in text_lower:
                parts = text.split("to")
                if len(parts) > 1:
                    to_addr = parts[1].strip() # Simplistic extraction
            
            return GoalPlan(
                intent="SEND_EMAIL",
                entities={"to": to_addr, "subject": "Automated Report", "body": "Here is the report."},
                actions=["email_communication.send_email"],
                confidence=0.85,
                requires_approval=True,
                reasoning="Detected email send request."
            )

        # Intent: UPDATE_EXCEL
        if "excel" in text_lower or "spreadsheet" in text_lower or "master" in text_lower or "process" in text_lower:
            if "update" in text_lower or "add" in text_lower or "process" in text_lower:
                return GoalPlan(
                    intent="UPDATE_EXCEL",
                    entities={
                        "master_path": "./data/master_sales.xlsx", # Relative for MVP/Test
                        "source_pattern": "sales_data.xlsx" 
                    },
                    actions=["excel_processing.append_to_master"],
                    confidence=0.9,
                    requires_approval=False,
                    reasoning="Detected request to update master excel."
                )

        # Intent: GENERATE_REPORT
        if "report" in text_lower or "summary" in text_lower:
            if "generate" in text_lower or "create" in text_lower or "make" in text_lower:
                return GoalPlan(
                    intent="GENERATE_REPORT",
                    entities={
                        "input_path": "./data/master_sales.xlsx",
                        "output_path": "./reports/daily_summary.txt"
                    },
                    actions=["excel_processing.compute_summary", "excel_processing.generate_report"],
                    confidence=0.9,
                    requires_approval=False,
                    reasoning="Detected request to generate report."
                )
             
        # Intent: SCREENSHOT
        if "screenshot" in text_lower or "capture" in text_lower:
            return GoalPlan(
                intent="SCREENSHOT",
                entities={},
                actions=["screen_vision.capture"],
                confidence=0.95,
                requires_approval=False,
                reasoning="Explicit screenshot request."
            )

        # Intent: BROWSE_WEB
        if any(kw in text_lower for kw in ["browse", "navigate", "go to", "visit", "website", "search google", "open url"]):
            # Extract URL or search query
            url = None
            search_query = None
            # Check for URL pattern
            url_match = re.search(r'(https?://\S+)', text)
            if url_match:
                url = url_match.group(1)
            elif "google" in text_lower:
                # Extract search query: "search google for X"
                if "for" in text_lower:
                    parts = text.split("for", 1)
                    if len(parts) > 1:
                        search_query = parts[1].strip()
            elif "go to" in text_lower:
                parts = text_lower.split("go to", 1)
                if len(parts) > 1:
                    url = parts[1].strip()
                    if not url.startswith("http"):
                        url = "https://" + url
            elif "visit" in text_lower:
                parts = text_lower.split("visit", 1)
                if len(parts) > 1:
                    url = parts[1].strip()
                    if not url.startswith("http"):
                        url = "https://" + url

            return GoalPlan(
                intent="BROWSE_WEB",
                entities={
                    "url": url,
                    "search_query": search_query
                },
                actions=["browser_control.open_url", "browser_control.scan_page"],
                confidence=0.85 if url else 0.7,
                requires_approval=False,
                reasoning="Detected web browsing request."
            )

        return GoalPlan(
            intent="UNKNOWN",
            entities={},
            actions=[],
            confidence=0.0,
            requires_approval=True,
            reasoning="No pattern matched."
        )

    def _llm_fallback(self, text: str) -> GoalPlan:
        """
        Mock LLM parser.
        In production, this sends prompt to local Llama 3.2.
        """
        return GoalPlan(
            intent="UNKNOWN_LLM_FALLBACK",
            entities={"original_text": text},
            actions=[],
            missing_info=["clarification"],
            confidence=0.1,
            requires_approval=True,
            reasoning="LLM not connected yet."
        )
