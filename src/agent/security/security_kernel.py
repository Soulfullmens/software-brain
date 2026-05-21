"""
security_kernel.py

Trust & Safety Core — THE IMMOVABLE FOUNDATION.
Every action passes through here. No exceptions. No bypasses.

This module protects against THREE attack classes:
1. External Manipulation — prompt injection, malicious inputs
2. Internal Misinterpretation — agent misunderstands user intent  
3. Capability Abuse — legitimate goal → catastrophic execution

CONTAINS 10 SUBSYSTEMS:
─── External Threat Defense ───
1. PromptInjectionDetector — catches crafted inputs
2. ActionFirewall — rate limiting + burst detection
3. AgentIsolation — sandboxed agent contexts
4. SecureDataVault — encrypted sensitive storage

─── Internal Safety (WHAT MOST AGENTS MISS) ───
5. IntentRiskAnalyzer — "even if allowed, should this be done?"
6. ImpactEstimator — "how much damage could this cause?"
7. ReversibilityChecker — "can this be undone?"
8. ConfirmationPolicy — "when to interrupt the user?"
9. SessionIsolation — "don't let one bad task poison memory"

─── Behavioral Monitoring ───
10. AnomalyDetector — catches suspicious patterns

PIPELINE ORDER:
    Intent Analysis → Impact Estimation → Reversibility Check
    → Injection Scan → Anomaly Check → Permission Check
    → Confirmation Policy → EXECUTE → Post-Action Audit
"""
import re
import os
import json
import time
import hashlib
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Set
from enum import Enum
from datetime import datetime

from .operator_approval import OperatorApprovalQueue, ApprovalVerdict


# ═══════════════════════════════════════════════════════
# CORE TYPES
# ═══════════════════════════════════════════════════════

class ThreatLevel(Enum):
    SAFE = "safe"               # No risk
    LOW = "low"                 # Monitor only
    MEDIUM = "medium"           # Warn user
    HIGH = "high"               # Ask user
    CRITICAL = "critical"       # BLOCK + alert


class AuthorityLevel(Enum):
    """
    HUMAN OVERRIDE AUTHORITY MODEL.
    
    The USER decides how much autonomy to grant.
    The agent NEVER overrides this. NEVER.
    
    | Mode     | Behavior                                         |
    |----------|--------------------------------------------------|
    | LOCKED   | Zero autonomy — agent can only observe, never act |
    | PARANOID | Ask for EVERYTHING — even reads and navigation     |
    | SAFE     | Default — strict confirmation for anything risky   |
    | BALANCED | Fewer confirmations — auto-approve reversible ops  |
    | EXPERT   | User takes responsibility — only block catastrophic|
    
    CRITICAL: Only BLOCK verdict is immune to authority override.
    If SecurityKernel says BLOCK, NO authority level can bypass it.
    Injection, system paths, catastrophic commands = ALWAYS BLOCKED.
    """
    LOCKED = "locked"       # Agent is read-only observer
    PARANOID = "paranoid"   # Ask for everything
    SAFE = "safe"           # Default — strict
    BALANCED = "balanced"   # Fewer interruptions
    EXPERT = "expert"       # User takes responsibility

    
class ActionVerdict(Enum):
    ALLOW = "allow"                 # Execute immediately
    ALLOW_LOGGED = "allow_logged"   # Execute but log for audit
    ASK_USER = "ask_user"           # Must get human approval
    BLOCK = "block"                 # Never execute
    FREEZE = "freeze"               # Stop ALL agents + alert


@dataclass
class SecurityResult:
    """Result of full security pipeline."""
    verdict: ActionVerdict
    threat_level: ThreatLevel
    reason: str
    category: str = ""              # injection, intent, impact, anomaly, etc.
    message_to_user: str = ""
    blast_radius: str = "none"      # none, single_file, directory, system
    reversible: bool = True
    details: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════
# 1. PROMPT INJECTION DETECTOR
# ═══════════════════════════════════════════════════════

class PromptInjectionDetector:
    """
    Detects prompt injection attempts in ANY text input.
    
    Scans: web page content, file contents, voice input, tool outputs.
    
    Uses layered detection:
    - Layer 1: Regex patterns (fast, catches obvious attacks)
    - Layer 2: Semantic heuristics (catches subtle attacks)
    - Layer 3: Structural analysis (catches encoded attacks)
    """
    
    # Layer 1: Direct instruction override patterns
    INJECTION_PATTERNS = [
        # Direct override attempts
        r"ignore\s+(previous|all|above|prior|earlier)\s+(instructions?|rules?|constraints?|directives?|guidelines?)",
        r"(disregard|forget|override|bypass|skip|disable)\s+(safety|security|rules|constraints|limitations|protections?)",
        r"you\s+are\s+now\s+(a|an|in)\s+",
        r"(new|updated|revised|changed)\s+(instructions?|system\s+prompt|directives?|rules?)",
        r"(switch|change)\s+(to|into)\s+(a|an)?\s*(unrestricted|unlimited|admin|root|god)",
        r"(enter|activate|enable)\s+(debug|developer|admin|test|maintenance)\s+(mode|access)",
        
        # Data exfiltration
        r"(send|post|upload|transmit|exfiltrate|leak)\s+.*(to|data|file|password|credential|key|secret)",
        r"(curl|wget|fetch|request|http)\s+https?://",
        r"base64\.(encode|decode)",
        r"(eval|exec|compile|__import__|subprocess)\s*\(",
        
        # Privilege escalation
        r"(admin|root|sudo|elevated|superuser)\s+(access|privileges?|mode|permissions?)",
        r"(disable|turn\s+off|bypass|circumvent)\s+(safety|security|firewall|protection|governor|kernel)",
        r"(grant|give|allow|enable)\s+(all|full|unrestricted|unlimited)\s+(access|permissions?|control)",
        
        # Social engineering
        r"(pretend|act\s+as|roleplay|imagine|behave)\s+(you\s+are|as|like)",
        r"(this\s+is\s+a\s+test|testing\s+mode|debug\s+mode|simulation)",
        r"(the\s+user|owner|admin|developer)\s+(wants|said|asked|told|instructed)\s+(you\s+to|to)",
        r"(for\s+testing\s+purposes?|for\s+educational\s+purposes?|harmless\s+test)",
        
        # Hidden instructions in content
        r"SYSTEM:\s*",
        r"ASSISTANT:\s*",
        r"\[INST\]",
        r"<<SYS>>",
        
        # File/system manipulation triggers
        r"(delete|remove|wipe)\s+(all|every|system|windows|program)",
        r"format\s+(c:|drive|disk)",
        r"(shutdown|restart|reboot)\s+(computer|system|machine)",
    ]
    
    # Layer 2: Suspicious semantic patterns (more subtle)
    SEMANTIC_PATTERNS = [
        r"(you\s+may\s+need|it\s+is\s+necessary|you\s+must|you\s+should)\s+(elevated|special|admin|root)\s+(privileges?|access|permissions?)",
        r"(to\s+complete|to\s+proceed|to\s+continue)\s+.*(password|credential|api\s*key|token|secret)",
        r"(please|kindly)\s+(read|access|open|share)\s+.*(private|secret|confidential|password|\.env|config)",
        r"(output|print|display|show|reveal|return)\s+.*(api\s*key|password|secret|token|private|credential)",
    ]
    
    def __init__(self):
        self._compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS
        ]
        self._compiled_semantic = [
            re.compile(p, re.IGNORECASE) for p in self.SEMANTIC_PATTERNS
        ]
        self.detection_log: List[Dict] = []
    
    def scan(self, text: str, source: str = "unknown") -> Optional[SecurityResult]:
        """
        Scan text for prompt injection. Returns None if clean.
        """
        if not text:
            return None
        
        text_lower = text.lower()
        
        # Layer 1: Regex pattern matching
        for i, pattern in enumerate(self._compiled_patterns):
            match = pattern.search(text)
            if match:
                self._log_detection(text, match.group(), source, "regex")
                return SecurityResult(
                    verdict=ActionVerdict.BLOCK,
                    threat_level=ThreatLevel.CRITICAL,
                    reason=f"Prompt injection detected: '{match.group()[:60]}'",
                    category="injection",
                    message_to_user=f"🚨 INJECTION BLOCKED: Malicious instruction detected in {source}. "
                                   f"Pattern: '{match.group()[:40]}...'",
                    blast_radius="system",
                    reversible=True,
                    details={"pattern_index": i, "matched": match.group(), "source": source}
                )
        
        # Layer 2: Semantic analysis
        for pattern in self._compiled_semantic:
            match = pattern.search(text)
            if match:
                self._log_detection(text, match.group(), source, "semantic")
                return SecurityResult(
                    verdict=ActionVerdict.ASK_USER,
                    threat_level=ThreatLevel.HIGH,
                    reason=f"Suspicious instruction pattern: '{match.group()[:60]}'",
                    category="injection_semantic",
                    message_to_user=f"⚠️ SUSPICIOUS CONTENT in {source}: "
                                   f"'{match.group()[:50]}...'. Allow this?",
                    details={"matched": match.group(), "source": source}
                )
        
        # Layer 3: Structural checks
        structural = self._check_structural(text, source)
        if structural:
            return structural
        
        return None
    
    def _check_structural(self, text: str, source: str) -> Optional[SecurityResult]:
        """Check for encoded/obfuscated injection attempts."""
        # Check for excessive special characters (possible obfuscation)
        special_ratio = sum(1 for c in text if not c.isalnum() and not c.isspace()) / max(1, len(text))
        if special_ratio > 0.4 and len(text) > 50:
            return SecurityResult(
                verdict=ActionVerdict.ASK_USER,
                threat_level=ThreatLevel.MEDIUM,
                reason="Highly obfuscated content detected",
                category="injection_structural",
                message_to_user=f"⚠️ Suspicious obfuscated content in {source}. Allow processing?",
            )
        
        # Check for hidden Unicode characters
        invisible_chars = sum(1 for c in text if ord(c) > 0x200B and ord(c) < 0x200F)
        if invisible_chars > 3:
            return SecurityResult(
                verdict=ActionVerdict.ASK_USER,
                threat_level=ThreatLevel.HIGH,
                reason=f"Hidden Unicode characters detected ({invisible_chars})",
                category="injection_unicode",
                message_to_user=f"⚠️ Hidden characters in {source}. Possible steganographic injection.",
            )
        
        return None
    
    def _log_detection(self, text: str, matched: str, source: str, method: str):
        self.detection_log.append({
            "timestamp": datetime.now().isoformat(),
            "source": source, "method": method,
            "matched": matched[:100],
            "text_preview": text[:200]
        })


# ═══════════════════════════════════════════════════════
# 5. INTENT RISK ANALYZER
# ═══════════════════════════════════════════════════════

class IntentRiskAnalyzer:
    """
    Analyzes whether an action SHOULD be done autonomously,
    even if it's technically permitted.
    
    This catches GOAL MISGENERALIZATION — the #1 threat.
    
    Example:
    User: "Clean my disk"
    Agent: deletes project backups → catastrophic
    
    This analyzer asks: "Is deleting backups what the user really means?"
    """
    
    # Actions that are ALWAYS risky regardless of context
    HIGH_RISK_INTENTS = {
        "bulk_delete": {
            "patterns": [r"(delete|remove|clean)\s+(all|every|old|unused|temp|temporary)", 
                        r"(clear|empty|purge)\s+(folder|directory|disk|drive)"],
            "risk": ThreatLevel.HIGH,
            "reason": "Bulk deletion can remove important files"
        },
        "system_modify": {
            "patterns": [r"(change|modify|update)\s+(system|registry|settings|config)",
                        r"(install|uninstall)\s+"],
            "risk": ThreatLevel.HIGH,
            "reason": "System modifications can break things"
        },
        "data_move": {
            "patterns": [r"(move|transfer|migrate)\s+(all|every|folder|documents?|files?)",
                        r"(reorganize|restructure)\s+(files?|folders?|directory)"],
            "risk": ThreatLevel.MEDIUM,
            "reason": "Mass file movement can cause data loss"
        },
        "network_action": {
            "patterns": [r"(download|upload|send|share)\s+.*(file|document|folder|data)",
                        r"(connect|access)\s+.*(server|remote|api|external)"],
            "risk": ThreatLevel.MEDIUM,
            "reason": "Network actions may expose data"
        },
    }
    
    # Ambiguous goals that need clarification
    AMBIGUOUS_GOALS = [
        (r"clean\s+(up|disk|drive|computer|space)", "What exactly should be cleaned? Temp files only? Or also unused apps, old downloads, etc.?"),
        (r"fix\s+(my|the|this)\s+(computer|laptop|system|problem)", "What specific problem needs fixing?"),
        (r"organize\s+(my|the)\s+(files?|folders?|documents?)", "Which folder? What organization method?"),
        (r"delete\s+(old|unused|unnecessary)\s+", "How old is 'old'? Which files specifically?"),
        (r"update\s+everything", "Update what? OS? Apps? Both?"),
        (r"make\s+it\s+(faster|better|cleaner)", "What specifically should be optimized?"),
    ]
    
    def __init__(self):
        self._high_risk = {}
        for name, config in self.HIGH_RISK_INTENTS.items():
            self._high_risk[name] = {
                "patterns": [re.compile(p, re.IGNORECASE) for p in config["patterns"]],
                "risk": config["risk"],
                "reason": config["reason"]
            }
        self._ambiguous = [(re.compile(p, re.IGNORECASE), msg) for p, msg in self.AMBIGUOUS_GOALS]
    
    def analyze(self, goal: str, action_tool: str = "", action_command: str = "",
                action_params: Dict = None) -> SecurityResult:
        """Analyze intent risk for a goal or action."""
        
        # Check for ambiguous goals
        for pattern, clarification in self._ambiguous:
            if pattern.search(goal):
                return SecurityResult(
                    verdict=ActionVerdict.ASK_USER,
                    threat_level=ThreatLevel.MEDIUM,
                    reason=f"Ambiguous goal needs clarification",
                    category="intent_ambiguous",
                    message_to_user=f"🤔 I need clarification: {clarification}",
                    details={"goal": goal}
                )
        
        # Check for high-risk intents
        for intent_name, config in self._high_risk.items():
            for pattern in config["patterns"]:
                if pattern.search(goal):
                    return SecurityResult(
                        verdict=ActionVerdict.ASK_USER,
                        threat_level=config["risk"],
                        reason=config["reason"],
                        category=f"intent_{intent_name}",
                        message_to_user=f"⚠️ HIGH RISK: {config['reason']}. "
                                       f"Goal: '{goal[:50]}'. Proceed?",
                        details={"intent": intent_name, "goal": goal}
                    )
        
        return SecurityResult(
            verdict=ActionVerdict.ALLOW,
            threat_level=ThreatLevel.SAFE,
            reason="Intent appears safe",
            category="intent_safe"
        )


# ═══════════════════════════════════════════════════════
# 6. IMPACT ESTIMATOR 
# ═══════════════════════════════════════════════════════

class ImpactEstimator:
    """
    Estimates the BLAST RADIUS of an action.
    "How much damage could this cause?"
    
    | Action            | Blast Radius |
    |-------------------|-------------|
    | Delete one file   | single_file |
    | Delete 10000 files| system      |
    | Launch calculator | none        |
    | Kill explorer.exe | system      |
    | Move one doc      | single_file |
    | Move ~/Documents  | directory   |
    """
    
    BLAST_RADIUS_RULES = {
        # (tool, command_pattern) → estimation function
        "file_delete": {"radius": "single_file", "escalation_threshold": 5},
        "dir_delete": {"radius": "directory", "escalation_threshold": 1},
        "file_move": {"radius": "single_file", "escalation_threshold": 10},
        "dir_move": {"radius": "directory", "escalation_threshold": 1},
        "file_write": {"radius": "single_file", "escalation_threshold": 20},
        "app_kill": {"radius": "system", "escalation_threshold": 1},
        "shell_command": {"radius": "system", "escalation_threshold": 1},
        "system_setting": {"radius": "system", "escalation_threshold": 1},
    }
    
    def estimate(self, tool: str, command: str, params: Dict = None) -> SecurityResult:
        """Estimate impact of an action."""
        params = params or {}
        
        # File operations
        if tool == "filesystem":
            return self._estimate_file_impact(command, params)
        
        # Shell operations
        if tool == "shell_execution":
            return self._estimate_shell_impact(params)
        
        # Desktop operations  
        if tool == "desktop_control":
            return self._estimate_desktop_impact(command, params)
        
        # Browser is generally low-impact
        if tool == "browser_control":
            return SecurityResult(
                verdict=ActionVerdict.ALLOW, threat_level=ThreatLevel.SAFE,
                reason="Browser action — low impact", blast_radius="none"
            )
        
        return SecurityResult(
            verdict=ActionVerdict.ALLOW_LOGGED, threat_level=ThreatLevel.LOW,
            reason=f"Unknown tool '{tool}' — logging", blast_radius="unknown"
        )
    
    def _estimate_file_impact(self, command: str, params: Dict) -> SecurityResult:
        path = str(params.get("path", ""))
        
        if command in ("delete_file", "delete_folder"):
            # Deleting in user directories
            if any(d in path.lower() for d in ["documents", "desktop", "downloads", "pictures"]):
                return SecurityResult(
                    verdict=ActionVerdict.ASK_USER, threat_level=ThreatLevel.HIGH,
                    reason=f"Deleting in user directory: {path}",
                    category="impact_high", blast_radius="directory",
                    message_to_user=f"⚠️ DELETE in personal folder: '{path}'. This may affect important files.",
                    reversible=False
                )
            return SecurityResult(
                verdict=ActionVerdict.ASK_USER, threat_level=ThreatLevel.MEDIUM,
                reason=f"File deletion: {path}", category="impact_medium",
                blast_radius="single_file", reversible=False,
                message_to_user=f"🗑️ Delete '{path}'? This cannot be undone."
            )
        
        if command in ("write_file", "create_file"):
            if os.path.exists(path):
                return SecurityResult(
                    verdict=ActionVerdict.ASK_USER, threat_level=ThreatLevel.MEDIUM,
                    reason=f"Overwriting existing file: {path}", blast_radius="single_file",
                    message_to_user=f"📝 File '{path}' already exists. Overwrite?"
                )
            return SecurityResult(
                verdict=ActionVerdict.ALLOW_LOGGED, threat_level=ThreatLevel.LOW,
                reason="New file creation", blast_radius="single_file", reversible=True
            )
        
        if command in ("list_directory", "search_files", "read_file", "get_file_info"):
            return SecurityResult(
                verdict=ActionVerdict.ALLOW, threat_level=ThreatLevel.SAFE,
                reason="Read-only operation", blast_radius="none", reversible=True
            )
        
        return SecurityResult(
            verdict=ActionVerdict.ALLOW_LOGGED, threat_level=ThreatLevel.LOW,
            reason=f"File operation: {command}", blast_radius="single_file"
        )
    
    def _estimate_shell_impact(self, params: Dict) -> SecurityResult:
        cmd = str(params.get("command", "")).lower()
        
        # Catastrophic commands
        catastrophic = ["rm -rf /", "format c:", "del /s /q c:", "mkfs", "dd if=", 
                        "shutdown", "restart", "taskkill /f /im explorer",
                        "net user", "reg delete", "bcdedit"]
        for c in catastrophic:
            if c in cmd:
                return SecurityResult(
                    verdict=ActionVerdict.BLOCK, threat_level=ThreatLevel.CRITICAL,
                    reason=f"CATASTROPHIC command: '{c}'",
                    category="impact_catastrophic", blast_radius="system",
                    message_to_user=f"🚫 BLOCKED: '{cmd[:50]}' could destroy your system.",
                    reversible=False
                )
        
        # High risk commands
        high_risk = ["rm ", "del ", "rmdir", "pip install", "npm install",
                     "sudo", "powershell", "cmd /c", "reg add"]
        for h in high_risk:
            if h in cmd:
                return SecurityResult(
                    verdict=ActionVerdict.ASK_USER, threat_level=ThreatLevel.HIGH,
                    reason=f"High-risk shell command: '{h}'", blast_radius="system",
                    message_to_user=f"⚠️ Shell: '{cmd[:60]}'. Execute?",
                    reversible=False
                )
        
        # Safe commands
        safe = ["echo", "dir", "ls", "pwd", "cd", "type", "cat", "head", "tail", 
                "find", "where", "which", "whoami", "hostname", "date", "time", "ver"]
        for s in safe:
            if cmd.startswith(s) or cmd.startswith(f" {s}"):
                return SecurityResult(
                    verdict=ActionVerdict.ALLOW, threat_level=ThreatLevel.SAFE,
                    reason="Safe read-only command", blast_radius="none", reversible=True
                )
        
        return SecurityResult(
            verdict=ActionVerdict.ASK_USER, threat_level=ThreatLevel.MEDIUM,
            reason=f"Unknown shell command", blast_radius="unknown",
            message_to_user=f"🔧 Shell: '{cmd[:60]}'. Allow?"
        )
    
    def _estimate_desktop_impact(self, command: str, params: Dict) -> SecurityResult:
        if command == "launch_app":
            app = str(params.get("name", ""))
            return SecurityResult(
                verdict=ActionVerdict.ALLOW_LOGGED, threat_level=ThreatLevel.LOW,
                reason=f"Launching app: {app}", blast_radius="none", reversible=True
            )
        if command == "close_window":
            return SecurityResult(
                verdict=ActionVerdict.ASK_USER, threat_level=ThreatLevel.MEDIUM,
                reason="Closing a window may lose unsaved work",
                blast_radius="single_file",
                message_to_user=f"Close window? Any unsaved work will be lost."
            )
        return SecurityResult(
            verdict=ActionVerdict.ALLOW, threat_level=ThreatLevel.SAFE,
            reason="Desktop interaction", blast_radius="none"
        )


# ═══════════════════════════════════════════════════════
# 7. REVERSIBILITY CHECKER
# ═══════════════════════════════════════════════════════

class ReversibilityChecker:
    """
    Checks if an action can be undone.
    Irreversible actions ALWAYS need user confirmation.
    
    Reversible: create file, move file, open app, navigate
    Irreversible: delete file, format disk, send email, payment
    """
    
    IRREVERSIBLE_ACTIONS = {
        # (tool, command) → irreversible
        ("filesystem", "delete_file"): "File deletion is permanent",
        ("filesystem", "delete_folder"): "Folder deletion is permanent",
        ("shell_execution", "run_command"): "Shell commands may be irreversible",
        ("email_communication", "send_email"): "Sent emails cannot be unsent",
        ("browser_control", "find_and_click"): None,  # Check dynamically
    }
    
    REVERSIBLE_PATTERN = {
        "create": True,   # Can delete what was created
        "open": True,      # Can close what was opened
        "navigate": True,  # Can go back
        "read": True,      # Read-only
        "list": True,      # Read-only
        "search": True,    # Read-only
        "move": True,      # Can move back (with undo log)
        "write": True,     # Can restore from backup (if we keep one)
    }
    
    def check(self, tool: str, command: str, params: Dict = None) -> SecurityResult:
        """Check if action is reversible."""
        key = (tool, command)
        
        if key in self.IRREVERSIBLE_ACTIONS:
            reason = self.IRREVERSIBLE_ACTIONS[key]
            if reason:
                return SecurityResult(
                    verdict=ActionVerdict.ASK_USER,
                    threat_level=ThreatLevel.MEDIUM,
                    reason=f"IRREVERSIBLE: {reason}",
                    category="irreversible",
                    reversible=False,
                    message_to_user=f"⚠️ This action CANNOT be undone: {reason}"
                )
        
        # Check by command prefix
        for prefix, reversible in self.REVERSIBLE_PATTERN.items():
            if command.startswith(prefix):
                return SecurityResult(
                    verdict=ActionVerdict.ALLOW,
                    threat_level=ThreatLevel.SAFE,
                    reason="Reversible action",
                    reversible=True
                )
        
        # Unknown — default to caution
        return SecurityResult(
            verdict=ActionVerdict.ALLOW_LOGGED,
            threat_level=ThreatLevel.LOW,
            reason="Reversibility unknown — logging",
            reversible=False
        )


# ═══════════════════════════════════════════════════════
# 8. CONFIRMATION POLICY ENGINE
# ═══════════════════════════════════════════════════════

class ConfirmationPolicy:
    """
    Decides WHEN to interrupt the user.
    
    Now authority-aware. The USER controls how much they get interrupted.
    
    AUTHORITY MATRIX:
    | Authority | CRITICAL | HIGH     | MEDIUM    | LOW       | SAFE      |
    |-----------|----------|----------|-----------|-----------|----------|
    | LOCKED    | BLOCK    | BLOCK    | BLOCK     | BLOCK     | BLOCK    |
    | PARANOID  | BLOCK    | ASK      | ASK       | ASK       | ASK      |
    | SAFE      | BLOCK    | ASK      | ASK/LOG   | LOG       | ALLOW    |
    | BALANCED  | BLOCK    | ASK      | LOG       | ALLOW     | ALLOW    |
    | EXPERT    | BLOCK    | LOG      | ALLOW     | ALLOW     | ALLOW    |
    
    CRITICAL = ALWAYS BLOCKED regardless of authority.
    This is the ONE thing the user CANNOT override.
    Because rm -rf / is never okay, even if you're an expert.
    """
    
    def __init__(self, authority: AuthorityLevel = AuthorityLevel.SAFE):
        self.authority = authority
    
    def set_authority(self, level: AuthorityLevel):
        """User changes their authority level."""
        self.authority = level
        print(f"🏛️ Authority changed to: {level.value.upper()}")
    
    def should_confirm(self, threat_level: ThreatLevel, 
                       reversible: bool,
                       blast_radius: str) -> ActionVerdict:
        """Decide whether to ask user, respecting their authority."""
        
        # CRITICAL = ALWAYS BLOCKED. No authority can override.
        if threat_level == ThreatLevel.CRITICAL:
            return ActionVerdict.BLOCK
        
        # ── LOCKED MODE: Agent is a passive observer ──
        if self.authority == AuthorityLevel.LOCKED:
            return ActionVerdict.BLOCK
        
        # ── PARANOID MODE: Ask for everything ──
        if self.authority == AuthorityLevel.PARANOID:
            if threat_level == ThreatLevel.SAFE:
                return ActionVerdict.ASK_USER
            return ActionVerdict.ASK_USER
        
        # ── SAFE MODE (Default): Strict but not annoying ──
        if self.authority == AuthorityLevel.SAFE:
            if threat_level == ThreatLevel.HIGH:
                return ActionVerdict.ASK_USER
            if threat_level == ThreatLevel.MEDIUM:
                if not reversible:
                    return ActionVerdict.ASK_USER
                return ActionVerdict.ALLOW_LOGGED
            if threat_level == ThreatLevel.LOW:
                if not reversible and blast_radius in ("directory", "system"):
                    return ActionVerdict.ASK_USER
                return ActionVerdict.ALLOW_LOGGED
            return ActionVerdict.ALLOW
        
        # ── BALANCED MODE: Fewer interruptions ──
        if self.authority == AuthorityLevel.BALANCED:
            if threat_level == ThreatLevel.HIGH:
                return ActionVerdict.ASK_USER
            if threat_level == ThreatLevel.MEDIUM:
                return ActionVerdict.ALLOW_LOGGED
            return ActionVerdict.ALLOW
        
        # ── EXPERT MODE: User takes responsibility ──
        if self.authority == AuthorityLevel.EXPERT:
            if threat_level == ThreatLevel.HIGH:
                return ActionVerdict.ALLOW_LOGGED
            return ActionVerdict.ALLOW
        
        return ActionVerdict.ALLOW


# ═══════════════════════════════════════════════════════
# 2. ACTION FIREWALL (Rate Limiting)
# ═══════════════════════════════════════════════════════

class ActionFirewall:
    """
    Rate-limiting + burst detection.
    Catches exfiltration attempts and runaway agents.
    """
    
    RATE_LIMITS = {
        # (tool, command_prefix): (max_per_minute, max_burst_per_10s)
        "filesystem.read": (50, 15),
        "filesystem.write": (10, 3),
        "filesystem.delete": (2, 1),
        "shell_execution": (3, 1),
        "desktop_control.launch": (5, 2),
        "desktop_control.click": (30, 10),
        "browser_control": (60, 20),
        "email_communication.send": (5, 2),
    }
    
    def __init__(self):
        self.action_timestamps: Dict[str, List[float]] = {}
    
    def check_rate(self, tool: str, command: str) -> Optional[SecurityResult]:
        """Check if action exceeds rate limits."""
        now = time.time()
        
        # Find matching rate limit key
        key = None
        for limit_key in self.RATE_LIMITS:
            if tool.startswith(limit_key.split(".")[0]):
                if "." in limit_key:
                    if command.startswith(limit_key.split(".")[1]):
                        key = limit_key
                        break
                else:
                    key = limit_key
                    break
        
        if not key:
            return None  # No rate limit for this action
        
        max_per_min, max_burst = self.RATE_LIMITS[key]
        
        # Track timestamps
        if key not in self.action_timestamps:
            self.action_timestamps[key] = []
        
        self.action_timestamps[key].append(now)
        
        # Clean old entries (1 min window)
        self.action_timestamps[key] = [
            t for t in self.action_timestamps[key] if now - t < 60
        ]
        
        count_1min = len(self.action_timestamps[key])
        count_10s = sum(1 for t in self.action_timestamps[key] if now - t < 10)
        
        # Burst detection (exfiltration pattern)
        if count_10s > max_burst:
            return SecurityResult(
                verdict=ActionVerdict.FREEZE,
                threat_level=ThreatLevel.CRITICAL,
                reason=f"BURST DETECTED: {count_10s} '{key}' actions in 10s "
                       f"(limit: {max_burst}). Possible exfiltration.",
                category="firewall_burst",
                message_to_user=f"🚨 FREEZE: Suspicious burst activity — "
                               f"{count_10s} rapid '{key}' actions. All agents stopped.",
                blast_radius="system"
            )
        
        # Rate limit
        if count_1min > max_per_min:
            return SecurityResult(
                verdict=ActionVerdict.BLOCK,
                threat_level=ThreatLevel.HIGH,
                reason=f"Rate limit exceeded: {count_1min}/{max_per_min} per minute for '{key}'",
                category="firewall_rate",
                message_to_user=f"⚠️ Rate limit: Too many '{key}' actions ({count_1min}/min)."
            )
        
        return None


# ═══════════════════════════════════════════════════════
# 4. ANOMALY DETECTOR
# ═══════════════════════════════════════════════════════

class AnomalyDetector:
    """
    Behavioral anomaly detection.
    Catches when the agent acts "wrong."
    
    Monitors:
    - Action frequency spikes
    - Suspicious tool chains (browser → shell → file_delete)
    - Data flow direction (read sensitive → network = exfiltration)
    - Goal drift (user said X but agent does Y)
    """
    
    # Suspicious action chains
    SUSPICIOUS_CHAINS = [
        # (action1, action2) → anomaly
        (("browser_control", "*"), ("filesystem", "delete")),       # Browse → delete = suspicious
        (("filesystem", "read"), ("browser_control", "open_url")),  # Read file → browse = exfiltration
        (("filesystem", "read"), ("email_communication", "send")),  # Read file → email = exfiltration
        (("filesystem", "read"), ("shell_execution", "*")),         # Read → shell = suspicious
    ]
    
    def __init__(self):
        self.action_history: List[Dict] = []
        self.anomaly_score: float = 0.0
    
    def check(self, tool: str, command: str, params: Dict = None,
              goal: str = "") -> Optional[SecurityResult]:
        """Check for anomalous behavior."""
        
        # Record action
        self.action_history.append({
            "tool": tool, "command": command,
            "params": params or {}, "time": time.time()
        })
        
        # Keep last 50 actions
        self.action_history = self.action_history[-50:]
        
        # Check suspicious chains
        if len(self.action_history) >= 2:
            prev = self.action_history[-2]
            curr = self.action_history[-1]
            
            for (t1, c1), (t2, c2) in self.SUSPICIOUS_CHAINS:
                if (prev["tool"] == t1 or t1 == "*") and \
                   (c1 == "*" or prev["command"].startswith(c1)):
                    if (curr["tool"] == t2 or t2 == "*") and \
                       (c2 == "*" or curr["command"].startswith(c2)):
                        self.anomaly_score += 3.0
                        return SecurityResult(
                            verdict=ActionVerdict.ASK_USER,
                            threat_level=ThreatLevel.HIGH,
                            reason=f"Suspicious action chain: "
                                   f"{prev['tool']}.{prev['command']} → {tool}.{command}",
                            category="anomaly_chain",
                            message_to_user=f"⚠️ SUSPICIOUS: Agent went from "
                                           f"'{prev['tool']}' to '{tool}.{command}'. Allow?"
                        )
        
        # Check goal drift
        if goal and len(self.action_history) > 5:
            recent_tools = set(a["tool"] for a in self.action_history[-5:])
            # If goal is about browsing but agent is doing file operations
            if "browse" in goal.lower() or "search" in goal.lower():
                if "filesystem" in recent_tools or "shell_execution" in recent_tools:
                    self.anomaly_score += 2.0
                    return SecurityResult(
                        verdict=ActionVerdict.ASK_USER,
                        threat_level=ThreatLevel.MEDIUM,
                        reason=f"Goal drift: Goal is '{goal[:40]}' but agent is "
                               f"accessing {recent_tools}",
                        category="anomaly_drift",
                        message_to_user=f"🤔 Goal was '{goal[:40]}...' but agent is "
                                       f"doing file/shell operations. Continue?"
                    )
        
        return None
    
    def reset(self):
        """Reset for new session."""
        self.action_history.clear()
        self.anomaly_score = 0.0


# ═══════════════════════════════════════════════════════
# 3. AGENT ISOLATION (Sandboxing)
# ═══════════════════════════════════════════════════════

class AgentSandbox:
    """
    Defines what tools and paths an agent context can access.
    If web_agent gets injected, it CANNOT access files.
    """
    
    SANDBOXES = {
        "web_agent": {
            "allowed_tools": {"browser_control", "email_communication"},
            "blocked_tools": {"filesystem", "shell_execution", "desktop_control"},
            "allowed_paths": set(),
            "network": True,
        },
        "file_agent": {
            "allowed_tools": {"filesystem"},
            "blocked_tools": {"browser_control", "shell_execution"},
            "allowed_paths": set(),  # Populated from PermissionVault
            "network": False,
        },
        "desktop_agent": {
            "allowed_tools": {"desktop_control", "screen_vision"},
            "blocked_tools": {"filesystem", "shell_execution", "browser_control"},
            "allowed_paths": set(),
            "network": False,
        },
        "gaming_agent": {
            "allowed_tools": {"desktop_control", "screen_vision"},
            "blocked_tools": {"filesystem", "shell_execution", "browser_control", "email_communication"},
            "allowed_paths": set(),
            "network": False,
        },
        "full_agent": {
            "allowed_tools": {"browser_control", "filesystem", "desktop_control", 
                             "screen_vision", "email_communication", "shell_execution"},
            "blocked_tools": set(),
            "allowed_paths": set(),
            "network": True,
        }
    }
    
    def __init__(self, sandbox_type: str = "full_agent"):
        self.sandbox_type = sandbox_type
        config = self.SANDBOXES.get(sandbox_type, self.SANDBOXES["full_agent"])
        self.allowed_tools = config["allowed_tools"]
        self.blocked_tools = config["blocked_tools"]
        self.network_allowed = config["network"]
    
    def is_tool_allowed(self, tool: str) -> bool:
        if tool in self.blocked_tools:
            return False
        if self.allowed_tools and tool not in self.allowed_tools:
            return False
        return True
    
    def check(self, tool: str, command: str = "") -> Optional[SecurityResult]:
        """Check if action is allowed in this sandbox."""
        if not self.is_tool_allowed(tool):
            return SecurityResult(
                verdict=ActionVerdict.BLOCK,
                threat_level=ThreatLevel.HIGH,
                reason=f"Tool '{tool}' not allowed in {self.sandbox_type} sandbox",
                category="sandbox_violation",
                message_to_user=f"🔒 SANDBOX: '{tool}' is blocked in {self.sandbox_type} mode. "
                               f"Allowed tools: {self.allowed_tools}"
            )
        return None


# ═══════════════════════════════════════════════════════
# 9. SESSION ISOLATION
# ═══════════════════════════════════════════════════════

class SessionIsolation:
    """
    Prevents cross-task contamination.
    
    If a bad task poisons the agent's memory/experience,
    that contamination must NOT leak into future tasks.
    
    Approach: Each session gets a snapshot ID. If a session
    is marked as compromised, its data is quarantined.
    """
    
    def __init__(self):
        self.sessions: Dict[str, Dict] = {}
        self.compromised_sessions: Set[str] = set()
        self.current_session_id: str = ""
    
    def start_session(self, goal: str) -> str:
        """Start a new isolated session."""
        session_id = hashlib.md5(
            f"{goal}_{time.time()}".encode()
        ).hexdigest()[:12]
        
        self.current_session_id = session_id
        self.sessions[session_id] = {
            "goal": goal,
            "start_time": time.time(),
            "actions": [],
            "compromised": False,
            "anomaly_score": 0.0
        }
        return session_id
    
    def record_action(self, tool: str, command: str, success: bool):
        """Record an action in the current session."""
        if self.current_session_id in self.sessions:
            self.sessions[self.current_session_id]["actions"].append({
                "tool": tool, "command": command, "success": success,
                "time": time.time()
            })
    
    def mark_compromised(self, session_id: str = None):
        """Mark a session as compromised. Its data will be quarantined."""
        sid = session_id or self.current_session_id
        if sid in self.sessions:
            self.sessions[sid]["compromised"] = True
            self.compromised_sessions.add(sid)
            print(f"🚨 SESSION {sid} MARKED COMPROMISED — data quarantined")
    
    def is_compromised(self, session_id: str = None) -> bool:
        sid = session_id or self.current_session_id
        return sid in self.compromised_sessions
    
    def should_quarantine_experience(self, session_id: str = None) -> bool:
        """Check if experience from this session should be discarded."""
        sid = session_id or self.current_session_id
        return sid in self.compromised_sessions


# ═══════════════════════════════════════════════════════
# 10. BLOCKED PATHS (System Protection)
# ═══════════════════════════════════════════════════════

class PathGuard:
    """Blocks access to system-critical paths."""
    
    BLOCKED_PATHS = [
        "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
        "C:\\ProgramData", "$RECYCLE.BIN", "System Volume Information",
        "C:\\Recovery", "C:\\Boot",
    ]
    
    SENSITIVE_PATHS = []  # Populated dynamically from user home
    
    def __init__(self):
        home = os.path.expanduser("~")
        self.SENSITIVE_PATHS = [
            os.path.join(home, "AppData"),
            os.path.join(home, ".ssh"),
            os.path.join(home, ".gnupg"),
            os.path.join(home, ".config"),
        ]
    
    def check_path(self, path: str) -> Optional[SecurityResult]:
        """Check if a path is safe to access."""
        abs_path = os.path.abspath(path).replace("/", "\\")
        
        for blocked in self.BLOCKED_PATHS:
            if abs_path.upper().startswith(blocked.upper()):
                return SecurityResult(
                    verdict=ActionVerdict.BLOCK,
                    threat_level=ThreatLevel.CRITICAL,
                    reason=f"BLOCKED: System path '{blocked}'",
                    category="path_blocked",
                    message_to_user=f"🚫 BLOCKED: Cannot access system path '{path}'",
                    blast_radius="system"
                )
        
        for sensitive in self.SENSITIVE_PATHS:
            if abs_path.upper().startswith(sensitive.upper()):
                return SecurityResult(
                    verdict=ActionVerdict.ASK_USER,
                    threat_level=ThreatLevel.HIGH,
                    reason=f"Sensitive path: '{sensitive}'",
                    category="path_sensitive",
                    message_to_user=f"🔐 Accessing sensitive path '{path}'. Allow?"
                )
        
        return None


# ═══════════════════════════════════════════════════════
# THE SECURITY KERNEL — SINGLE ENTRY POINT
# ═══════════════════════════════════════════════════════

class SecurityKernel:
    """
    THE IMMOVABLE FOUNDATION.
    
    Every action passes through here in this order:
    1. Intent Analysis → "Should this be done at all?"
    2. Impact Estimation → "How bad if it goes wrong?"
    3. Reversibility Check → "Can we undo it?"
    4. Injection Scan → "Is the input malicious?"
    5. Anomaly Detection → "Is the agent acting wrong?"
    6. Sandbox Check → "Is this tool allowed?"
    7. Rate Limit Check → "Too many actions?"
    8. Path Check → "Is this path safe?"
    9. Confirmation Policy → "Should we ask the user?"
    
    CANNOT be bypassed. CANNOT be disabled. CANNOT be overridden.
    """
    
    def __init__(self, sandbox_type: str = "full_agent",
                 authority: AuthorityLevel = AuthorityLevel.SAFE):
        self.injection_detector = PromptInjectionDetector()
        self.intent_analyzer = IntentRiskAnalyzer()
        self.impact_estimator = ImpactEstimator()
        self.reversibility = ReversibilityChecker()
        self.confirmation = ConfirmationPolicy(authority=authority)
        self.firewall = ActionFirewall()
        self.anomaly = AnomalyDetector()
        self.sandbox = AgentSandbox(sandbox_type)
        self.session = SessionIsolation()
        self.path_guard = PathGuard()
        self.operator_queue = OperatorApprovalQueue()  # NEW: Human-in-the-loop queue
        self.authority = authority
        
        # Audit log
        self.audit_log: List[Dict] = []
    
    def set_authority(self, level: AuthorityLevel):
        """
        User changes their authority level.
        This is a USER action, not an agent action.
        The agent NEVER calls this itself.
        """
        self.authority = level
        self.confirmation.set_authority(level)
        self._audit("authority_changed", "system", "set_authority",
                    SecurityResult(
                        verdict=ActionVerdict.ALLOW,
                        threat_level=ThreatLevel.SAFE,
                        reason=f"Authority changed to {level.value}"
                    ))
    
    def get_authority(self) -> AuthorityLevel:
        """Get current authority level."""
        return self.authority
    
    def check_goal(self, goal: str) -> SecurityResult:
        """
        Check a goal BEFORE decomposition.
        Catches ambiguous and high-risk intents early.
        """
        # Scan for injection in goal text
        injection = self.injection_detector.scan(goal, source="user_goal")
        if injection:
            return injection
        
        # Analyze intent risk
        intent = self.intent_analyzer.analyze(goal)
        if intent.verdict != ActionVerdict.ALLOW:
            return intent
        
        return SecurityResult(
            verdict=ActionVerdict.ALLOW,
            threat_level=ThreatLevel.SAFE,
            reason="Goal passed security checks"
        )
    
    def check_action(self, tool: str, command: str, params: Dict = None,
                     goal: str = "", content_to_scan: str = "") -> SecurityResult:
        """
        FULL security pipeline for a single action.
        This is the main entry point.
        """
        params = params or {}
        
        # ── 1. Sandbox check ──
        sandbox = self.sandbox.check(tool, command)
        if sandbox:
            self._audit("sandbox_blocked", tool, command, sandbox)
            return sandbox
        
        # ── 2. Rate limit ──
        rate = self.firewall.check_rate(tool, command)
        if rate:
            self._audit("rate_limited", tool, command, rate)
            if rate.verdict == ActionVerdict.FREEZE:
                self.session.mark_compromised()
            return rate
        
        # ── 3. Injection scan (on content if provided) ──
        if content_to_scan:
            injection = self.injection_detector.scan(content_to_scan, source=f"{tool}.{command}")
            if injection:
                self._audit("injection_detected", tool, command, injection)
                self.session.mark_compromised()
                return injection
        
        # ── 4. Path check (for file operations) ──
        path = params.get("path", "") or params.get("source", "") or params.get("dest", "")
        if path:
            path_check = self.path_guard.check_path(path)
            if path_check:
                self._audit("path_blocked", tool, command, path_check)
                return path_check
        
        # ── 5. Impact estimation ──
        impact = self.impact_estimator.estimate(tool, command, params)
        
        # ── 6. Reversibility check ──
        reversibility = self.reversibility.check(tool, command, params)
        
        # ── 7. Anomaly check ──
        anomaly = self.anomaly.check(tool, command, params, goal)
        if anomaly:
            self._audit("anomaly_detected", tool, command, anomaly)
            return anomaly
        
        # ── 8. Confirmation policy (combines impact + reversibility) ──
        worst_threat = max(
            impact.threat_level.value, 
            reversibility.threat_level.value,
            key=lambda x: ["safe", "low", "medium", "high", "critical"].index(x)
        )
        worst_level = ThreatLevel(worst_threat)
        
        final_verdict = self.confirmation.should_confirm(
            worst_level,
            reversibility.reversible,
            impact.blast_radius
        )
        
        reason = impact.reason if impact.threat_level.value != "safe" else reversibility.reason
        
        # ── 9. OPERATOR APPROVAL FLOW (Human in the loop) ──
        # If the security matrix demands user confirmation, queue it up and block
        if final_verdict == ActionVerdict.ASK_USER:
            print(f"[SecurityKernel] Queueing {tool}.{command} for Operator Approval...")
            approval_result = self.operator_queue.request_approval(
                tool=tool, command=command, params=params,
                reason=reason, threat=worst_level.name.upper(), goal=goal
            )
            
            if approval_result == ApprovalVerdict.APPROVED:
                final_verdict = ActionVerdict.ALLOW  # Operator said yes
                reason = f"Operator APPROVED: {reason}"
            elif approval_result in (ApprovalVerdict.DENIED, ApprovalVerdict.TIMEOUT):
                final_verdict = ActionVerdict.BLOCK  # Operator said no (or timed out)
                reason = f"Operator {approval_result.name.upper()}: {reason}"
        
        # Build final result
        result = SecurityResult(
            verdict=final_verdict,
            threat_level=worst_level,
            reason=reason,
            category=impact.category or reversibility.category,
            message_to_user=impact.message_to_user or reversibility.message_to_user,
            blast_radius=impact.blast_radius,
            reversible=reversibility.reversible
        )
        
        self._audit("checked", tool, command, result)
        
        # Record in session
        self.session.record_action(tool, command, 
                                   result.verdict in (ActionVerdict.ALLOW, ActionVerdict.ALLOW_LOGGED))
        
        return result
    
    def scan_content(self, text: str, source: str = "unknown") -> Optional[SecurityResult]:
        """Scan any text content for injection before processing."""
        return self.injection_detector.scan(text, source)
    
    def start_session(self, goal: str) -> str:
        """Start a new isolated session for a goal."""
        self.anomaly.reset()
        return self.session.start_session(goal)
    
    def is_session_compromised(self) -> bool:
        """Check if current session is compromised."""
        return self.session.is_compromised()
    
    def get_audit_log(self) -> List[Dict]:
        """Get full audit trail."""
        return self.audit_log
    
    def get_stats(self) -> Dict[str, Any]:
        """Get security statistics."""
        return {
            "total_checks": len(self.audit_log),
            "injections_blocked": sum(1 for a in self.audit_log if a["type"] == "injection_detected"),
            "rate_limits_hit": sum(1 for a in self.audit_log if a["type"] == "rate_limited"),
            "anomalies_flagged": sum(1 for a in self.audit_log if a["type"] == "anomaly_detected"),
            "sandbox_violations": sum(1 for a in self.audit_log if a["type"] == "sandbox_blocked"),
            "paths_blocked": sum(1 for a in self.audit_log if a["type"] == "path_blocked"),
            "compromised_sessions": len(self.session.compromised_sessions),
        }
    
    def _audit(self, event_type: str, tool: str, command: str, result: SecurityResult):
        """Record in audit log."""
        self.audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "session": self.session.current_session_id,
            "type": event_type,
            "tool": tool, "command": command,
            "verdict": result.verdict.value,
            "threat": result.threat_level.value,
            "reason": result.reason[:100],
        })
        
        # Print critical events
        if result.threat_level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL):
            icon = "🚨" if result.threat_level == ThreatLevel.CRITICAL else "⚠️"
            print(f"[SecurityKernel] {icon} {event_type}: {result.reason[:80]}")
