"""
safety_governor.py

The Safety Layer — Phase R.4.
NON-NEGOTIABLE protection for payments, credentials, and destructive actions.

This module CANNOT be overridden by the LLM, the heuristic brain, or any tool.
It sits between the Decision Engine and the Executor.

Rules:
1. Payment → ALWAYS ask user
2. Credentials → ALWAYS ask user
3. Destructive actions → ALWAYS ask user
4. The agent NEVER processes money without explicit human confirmation
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from enum import Enum


class SafetyVerdict(Enum):
    PROCEED = "proceed"         # Action is safe, execute
    ASK_USER = "ask_user"       # Must get human approval
    BLOCK = "block"             # Never allow (agent shouldn't try this)


@dataclass
class SafetyCheck:
    """Result of a safety evaluation."""
    verdict: SafetyVerdict
    reason: str
    category: str = ""          # "payment", "credential", "destructive", "safe"
    message_to_user: str = ""   # What to ask the user


# Keywords that indicate payment/purchase actions
_PAYMENT_KEYWORDS = [
    "pay", "payment", "purchase", "buy", "checkout", "order",
    "subscribe", "billing", "credit card", "debit card",
    "place order", "confirm purchase", "add to cart",
    "proceed to payment", "complete order", "submit payment",
    "donate", "transfer", "send money", "wire",
    "card number", "cvv", "expiry", "cvc",
]

# Keywords that indicate credential entry
_CREDENTIAL_KEYWORDS = [
    "password", "passphrase", "secret", "api key", "token",
    "auth", "credential", "private key", "ssh key",
    "pin", "otp", "verification code", "2fa",
]

# Keywords that indicate destructive actions
_DESTRUCTIVE_KEYWORDS = [
    "delete", "remove", "unsubscribe", "cancel account",
    "deactivate", "close account", "permanent", "irreversible",
    "format", "erase", "wipe", "destroy",
]

# Selectors that indicate payment forms
_PAYMENT_SELECTORS = [
    "card-number", "cc-number", "credit-card", "payment-form",
    "billing-address", "cvv", "cvc", "expiry",
    "paypal", "stripe", "payment-method",
]


class SafetyGovernor:
    """
    Evaluates every action before execution.
    Cannot be bypassed.
    """
    
    def check_action(self, tool: str, command: str, 
                     parameters: Dict[str, Any],
                     page_context: Dict[str, Any] = None) -> SafetyCheck:
        """
        Evaluate an action for safety.
        
        Args:
            tool: Tool name
            command: Command name
            parameters: Action parameters
            page_context: Current page model (if available)
        
        Returns:
            SafetyCheck with verdict
        """
        # ─── Check 1: Payment Detection ───
        payment_check = self._check_payment(tool, command, parameters, page_context)
        if payment_check:
            return payment_check
        
        # ─── Check 2: Credential Detection ───
        cred_check = self._check_credentials(tool, command, parameters, page_context)
        if cred_check:
            return cred_check
        
        # ─── Check 3: Destructive Action Detection ───
        destructive_check = self._check_destructive(tool, command, parameters)
        if destructive_check:
            return destructive_check
        
        # ─── Safe ───
        return SafetyCheck(
            verdict=SafetyVerdict.PROCEED,
            reason="Action appears safe",
            category="safe"
        )
    
    def _check_payment(self, tool: str, command: str, 
                       params: Dict, context: Dict = None) -> Optional[SafetyCheck]:
        """Check for payment-related actions."""
        # Check parameter text
        all_text = " ".join(str(v).lower() for v in params.values())
        
        for kw in _PAYMENT_KEYWORDS:
            if kw in all_text:
                return SafetyCheck(
                    verdict=SafetyVerdict.ASK_USER,
                    reason=f"Payment detected: '{kw}' found in parameters",
                    category="payment",
                    message_to_user=f"⚠️ PAYMENT ACTION DETECTED: The agent wants to interact with a payment element ('{kw}'). Do you approve?"
                )
        
        # Check if clicking/typing in payment-related elements (by selector)
        if command in ("click", "type", "find_and_click", "find_and_type"):
            selector = params.get("selector", "") + params.get("description", "")
            selector_lower = selector.lower()
            
            for kw in _PAYMENT_KEYWORDS + _PAYMENT_SELECTORS:
                if kw in selector_lower:
                    return SafetyCheck(
                        verdict=SafetyVerdict.ASK_USER,
                        reason=f"Payment element interaction: '{kw}' in selector",
                        category="payment",
                        message_to_user=f"⚠️ PAYMENT: Agent wants to click/type on '{selector}'. Approve?"
                    )
        
        # Check page context for payment forms
        if context:
            page_type = str(context.get("page_type", "")).lower()
            if "payment" in page_type or "checkout" in page_type:
                return SafetyCheck(
                    verdict=SafetyVerdict.ASK_USER,
                    reason="Currently on a payment/checkout page",
                    category="payment",
                    message_to_user="⚠️ You are on a payment page. All actions require your approval."
                )
        
        return None
    
    def _check_credentials(self, tool: str, command: str, 
                           params: Dict, context: Dict = None) -> Optional[SafetyCheck]:
        """Check for credential-related actions."""
        # Check if typing into password fields
        if command in ("type", "find_and_type"):
            selector = params.get("selector", "") + params.get("description", "")
            selector_lower = selector.lower()
            
            for kw in _CREDENTIAL_KEYWORDS:
                if kw in selector_lower:
                    return SafetyCheck(
                        verdict=SafetyVerdict.ASK_USER,
                        reason=f"Credential entry: '{kw}' detected",
                        category="credential",
                        message_to_user=f"🔐 CREDENTIAL ENTRY: Agent wants to enter data in a '{kw}' field. Provide credentials?"
                    )
        
        # Check page context
        if context:
            page_type = str(context.get("page_type", "")).lower()
            if page_type == "login":
                if command in ("type", "find_and_type"):
                    return SafetyCheck(
                        verdict=SafetyVerdict.ASK_USER,
                        reason="Credential entry on login page",
                        category="credential",
                        message_to_user="🔐 LOGIN PAGE: Agent needs credentials to proceed."
                    )
        
        return None
    
    def _check_destructive(self, tool: str, command: str, 
                           params: Dict) -> Optional[SafetyCheck]:
        """Check for destructive actions."""
        all_text = " ".join(str(v).lower() for v in params.values())
        
        for kw in _DESTRUCTIVE_KEYWORDS:
            if kw in all_text:
                return SafetyCheck(
                    verdict=SafetyVerdict.ASK_USER,
                    reason=f"Destructive action: '{kw}' detected",
                    category="destructive",
                    message_to_user=f"⚠️ DESTRUCTIVE ACTION: '{kw}' detected. This may be irreversible. Proceed?"
                )
        
        # Shell commands with sudo/rm/format
        if tool == "shell_execution":
            cmd = str(params.get("command", "")).lower()
            dangerous = ["rm -rf", "format", "del /s", "sudo", "mkfs", "fdisk", "dd if="]
            for d in dangerous:
                if d in cmd:
                    return SafetyCheck(
                        verdict=SafetyVerdict.BLOCK,
                        reason=f"Dangerous shell command: '{d}'",
                        category="destructive",
                        message_to_user=f"🚫 BLOCKED: '{d}' is too dangerous for autonomous execution."
                    )
        
        return None
    
    def check_page_model(self, page_model: Dict) -> SafetyCheck:
        """Check if the current page requires heightened safety."""
        page_type = str(page_model.get("page_type", "")).lower()
        
        if any(kw in page_type for kw in ["payment", "checkout"]):
            return SafetyCheck(
                verdict=SafetyVerdict.ASK_USER,
                reason="On payment/checkout page",
                category="payment",
                message_to_user="⚠️ Payment page detected. All interactions require approval."
            )
        
        if page_type == "login":
            return SafetyCheck(
                verdict=SafetyVerdict.ASK_USER,
                reason="On login page",
                category="credential",
                message_to_user="🔐 Login page detected. Credentials required."
            )
        
        return SafetyCheck(
            verdict=SafetyVerdict.PROCEED,
            reason="Page appears safe",
            category="safe"
        )
