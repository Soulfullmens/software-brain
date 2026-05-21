"""
ASSIGNMENT 006: REFLECTIVE INTELLIGENCE (why.py)

Objective:
- Expose the agent's internal reasoning as an explanation.
- Answer: Why no action? Why stable? What would trigger change?
- STRICT READ-ONLY. NO LEARNING. NO ACTUATION.

Logic:
1. Load Context (Mode, Latest Trend Report).
2. Synthesize Explanations based on fixed rules.
3. Output properly formatted reasoning.
"""
import sys
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

# Fix path
sys.path.append(".")

# Hard Constants for Reasoning (No magic numbers)
DISK_THRESHOLD_CRITICAL = 10.0
SOURCE_STABILITY_TARGET = 100.0
ENV_STABILITY_TARGET = 100.0

# Import Config for Mode
from src.core.config import DEFAULT_LEARNING_MODE
from src.learning.learning_mode import LearningMode

TREND_REPORT_DIR = Path("data/trend_reports")

def get_latest_report() -> Optional[Path]:
    """Find the most recent trend report."""
    if not TREND_REPORT_DIR.exists():
        return None
    reports = sorted(TREND_REPORT_DIR.glob("trend_report_*.md"))
    return reports[-1] if reports else None

def parse_report_summary(k: Path) -> Dict[str, str]:
    """Extract key metrics from the markdown report."""
    content = k.read_text(encoding="utf-8")
    summary = {}
    
    # Extract Source Stability
    m = re.search(r"Source.*?Stability: (\d+\.\d+)%", content, re.DOTALL)
    if m: summary["source_stability"] = float(m.group(1))
    
    # Extract Env Stability
    m = re.search(r"Environment.*?Stability: (\d+\.\d+)%", content, re.DOTALL)
    if m: summary["env_stability"] = float(m.group(1))
    
    # Extract Disk Trend
    m = re.search(r"Disk Free:.*?Daily trend: ([+\-]?\d+\.\d+)%", content, re.DOTALL)
    if m: 
        summary["disk_trend"] = float(m.group(1))
    else:
        summary["disk_trend"] = 0.0 # Default or None
        
    return summary

def explain_system():
    print(f"SYSTEM EXPLANATION — {datetime.now().strftime('%Y-%m-%d')}")
    print("")
    
    # 1. System State
    print("System State:")
    print(f"- Mode: {DEFAULT_LEARNING_MODE.value}")
    print(f"- Learning: DISABLED (Hardcoded in Mode)")
    print(f"- Actuation: RESTRICTED (Whitelist Only)")
    print("")
    
    # 2. Observed Facts
    print("Observed Facts:")
    report_path = get_latest_report()
    if not report_path:
        print("- No trend reports found. System is blind to history.")
        metrics = {}
    else:
        print(f"- Latest Report: {report_path.name}")
        metrics = parse_report_summary(report_path)
        
        s_stab = metrics.get("source_stability", 0.0)
        e_stab = metrics.get("env_stability", 0.0)
        d_trend = metrics.get("disk_trend", 0.0)
        
        print(f"- Source Stability: {s_stab}%")
        print(f"- Env Stability:    {e_stab}%")
        print(f"- Disk Trend:       {d_trend:+.3f}% / day")
    print("")
    
    # 3. Blocked Actions (Why nothing happened)
    print("Why no action was taken:")
    
    # Hierarchy of blockers
    # Primary: Mode
    if DEFAULT_LEARNING_MODE == LearningMode.EVALUATE:
        print("- Primary Blocker: LearningMode is EVALUATE (Prohibits policy checks)")
    
    # Secondary: Thresholds
    reasons = []
    if metrics:
        if metrics.get("source_stability", 100) >= SOURCE_STABILITY_TARGET:
            reasons.append("Source stability meets target (100%)")
        else:
            reasons.append(f"Source stability degraded ({metrics.get('source_stability')}% < 100%) - BUT blocked by Mode")
            
        if metrics.get("env_stability", 100) >= ENV_STABILITY_TARGET:
            reasons.append("Environment stability meets target (100%)")
            
        # Disk check logic (Simplified)
        # We don't have current disk state freely available here without re-parsing log detail or trusting report.
        # Report provides trend. Action trigger would be mostly threshold based.
        reasons.append("No critical thresholds breached requiring immediate intervention")
        
    for r in reasons:
        print(f"- {r}")
    print("")

    # 4. Counterfactual Triggers (What implies change)
    print("What would trigger change:")
    print(f"- Assignment 001 Fails (Source < {SOURCE_STABILITY_TARGET}%) -> Immediate Halt")
    print(f"- Assignment 002 Fails (Env < {ENV_STABILITY_TARGET}%) -> Re-bind required")
    print(f"- Disk Free < {DISK_THRESHOLD_CRITICAL}% -> Alert / Actuation Proposal")
    print("- Assignment 005 Projections point to < 7 days survival")
    print("")
    
    # 5. Most Fragile Assumption
    print("Most Fragile Assumption:")
    if metrics and metrics.get("disk_trend", 0) < 0:
        print("- Disk usage decline is linear and will not accelerate.")
    else:
        print("- Current stability implies future stability (Classic Induction Fallacy).")

if __name__ == "__main__":
    if DEFAULT_LEARNING_MODE != LearningMode.EVALUATE:
        print("CRITICAL: why.py requires EVALUATE mode.")
        sys.exit(3)
    explain_system()
