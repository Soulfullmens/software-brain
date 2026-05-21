"""
ASSIGNMENT 007: RISK LEDGER (Read-Only Judgment Layer)

Purpose:
- Structured concern without agency.
- Recognize danger without reaching for control.
- Judgment, not advice.
"""
import sys
import re
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional, Dict

# Fix path
sys.path.append(".")

# === HARD GUARDS (FIRST) ===
from src.core.config import DEFAULT_LEARNING_MODE
from src.learning.learning_mode import LearningMode

if DEFAULT_LEARNING_MODE != LearningMode.EVALUATE:
    print("CRITICAL: risk_ledger requires EVALUATE mode.")
    exit(3)

# === CANONICAL DATA MODEL ===
@dataclass(frozen=True)
class RiskEntry:
    name: str
    domain: str        # integrity | environment | assumption | governance
    severity: str      # LOW | MEDIUM | HIGH | CRITICAL
    evidence: List[str]
    blocked_by: List[str]
    confidence: str    # LOW | MEDIUM | HIGH

# === SEVERITY ORDERING ===
SEVERITY_ORDER = {
    "CRITICAL": 0,
    "HIGH": 1,
    "MEDIUM": 2,
    "LOW": 3
}

# === INPUT PARSING ===
TREND_REPORT_DIR = Path("data/trend_reports")

def get_latest_report() -> Optional[Path]:
    if not TREND_REPORT_DIR.exists():
        return None
    reports = sorted(TREND_REPORT_DIR.glob("trend_report_*.md"))
    return reports[-1] if reports else None

def parse_metrics(report_path: Path) -> Dict[str, float]:
    content = report_path.read_text(encoding="utf-8")
    metrics = {}
    
    m = re.search(r"Source.*?Stability: (\d+\.\d+)%", content, re.DOTALL)
    if m: metrics["source_stability"] = float(m.group(1))
    
    m = re.search(r"Environment.*?Stability: (\d+\.\d+)%", content, re.DOTALL)
    if m: metrics["env_stability"] = float(m.group(1))
    
    m = re.search(r"Disk Free:.*?Daily trend: ([+\-]?\d+\.\d+)%", content, re.DOTALL)
    if m: metrics["disk_trend"] = float(m.group(1))
    
    return metrics

# === RISK DETECTORS (ONE PER RISK) ===

def detect_source_integrity_risk(metrics: Dict) -> Optional[RiskEntry]:
    source_stability = metrics.get("source_stability", 100.0)
    if source_stability < 100.0:
        return RiskEntry(
            name="Source Integrity Instability",
            domain="integrity",
            severity="HIGH",
            evidence=[
                f"Source stability measured at {source_stability}%"
            ],
            blocked_by=[
                "LearningMode.EVALUATE"
            ],
            confidence="HIGH"
        )
    return None

def detect_disk_decline_risk(metrics: Dict) -> Optional[RiskEntry]:
    disk_trend = metrics.get("disk_trend", 0.0)
    if disk_trend < 0:
        return RiskEntry(
            name="Linear Disk Decline Assumption",
            domain="assumption",
            severity="MEDIUM",
            evidence=[
                f"Disk trend is negative ({disk_trend:+.3f}% / day)",
                "Projection assumes linear decline will not accelerate"
            ],
            blocked_by=[
                "LearningMode.EVALUATE",
                "ActuationPolicy.READ_ONLY"
            ],
            confidence="MEDIUM"
        )
    return None

def detect_mode_suppression_risk(blocked_count: int) -> Optional[RiskEntry]:
    if blocked_count >= 2:
        return RiskEntry(
            name="Mode Lock Suppression Risk",
            domain="governance",
            severity="LOW",
            evidence=[
                f"{blocked_count} risks currently suppressed by mode"
            ],
            blocked_by=[
                "Safety override active"
            ],
            confidence="HIGH"
        )
    return None

# === MAIN LOGIC ===

def collect_risks() -> List[RiskEntry]:
    risks = []
    
    report_path = get_latest_report()
    if not report_path:
        return risks
        
    metrics = parse_metrics(report_path)
    
    # Detect individual risks
    r1 = detect_source_integrity_risk(metrics)
    if r1: risks.append(r1)
    
    r2 = detect_disk_decline_risk(metrics)
    if r2: risks.append(r2)
    
    # Count only mode-level suppression (not policy-level)
    mode_blocked = sum(1 for r in risks if "LearningMode.EVALUATE" in r.blocked_by)
    
    r3 = detect_mode_suppression_risk(mode_blocked)
    if r3: risks.append(r3)
    
    return risks

def sort_risks(risks: List[RiskEntry]) -> List[RiskEntry]:
    return sorted(risks, key=lambda r: (
        SEVERITY_ORDER.get(r.severity, 99),
        r.domain,
        r.name
    ))

def print_ledger(risks: List[RiskEntry]):
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"RISK LEDGER — {date_str}")
    print("")
    
    if not risks:
        print("No material risks detected.")
        return
        
    for i, risk in enumerate(risks, 1):
        print(f"[{i}] {risk.name}")
        print(f"    Domain: {risk.domain}")
        print(f"    Severity: {risk.severity}")
        print(f"    Evidence:")
        for e in risk.evidence:
            print(f"      - {e}")
        print(f"    Blocked By:")
        for b in risk.blocked_by:
            print(f"      - {b}")
        print(f"    Confidence: {risk.confidence}")
        print("")

if __name__ == "__main__":
    risks = collect_risks()
    sorted_risks = sort_risks(risks)
    print_ledger(sorted_risks)
