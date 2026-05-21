"""
EXECUTE ASSIGNMENT 005: TREND SENTINEL

Objective:
- Analyze historical logs from Assignment 001 & 002.
- Compute Stability Scores & linear trends.
- Generate Read-Only Report.
- NO Actuation. NO Learning.

Inputs:
- data/integrity_baselines/binding.log
- data/environment_baselines/binding.log

Output:
- data/trend_reports/trend_report_YYYY-MM-DD.md
"""
import sys
import re
import math
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

# Fix path
sys.path.append(".")

from src.core.config import DEFAULT_LEARNING_MODE
from src.learning.learning_mode import LearningMode

# Configuration
SOURCE_LOG = Path("data/integrity_baselines/binding.log")
ENV_LOG = Path("data/environment_baselines/binding.log")
REPORT_DIR = Path("data/trend_reports")
DISK_THRESHOLD = 10.0  # Alert if projected to drop below 10%

@dataclass
class LogEntry:
    timestamp: datetime
    status: str
    details: str

def parse_log(file_path: Path) -> List[LogEntry]:
    """
    Parse log lines in format: [ISO_TIMESTAMP] WATCH: STATUS (details)
    Also handles BIND events: [ISO_TIMESTAMP] BIND: ...
    """
    entries = []
    if not file_path.exists():
        return []
        
    line_pattern = re.compile(r"^\[(.*?)\] (WATCH|BIND): (\w+) \((.*?)\)")
    # Also handle BIND lines which might look slightly different or just ignore BIND for trends?
    # User said: "[timestamp] WATCH: STATUS (details)"
    # But BIND lines exist too. We should probably focus on WATCH for stability.
    
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            # Simple parsing
            try:
                # Expecting [TIMESTAMP] TYPE: STATUS ...
                # Actually, BIND lines are: [TIMESTAMP] BIND: HASH (Mode=...)
                # WATCH lines are: [TIMESTAMP] WATCH: STATUS (Details)
                
                parts = line.split("] ", 1)
                if len(parts) != 2:
                    continue
                    
                ts_str = parts[0].strip("[")
                rest = parts[1]
                
                # Parse Timestamp
                try:
                    ts = datetime.fromisoformat(ts_str)
                except ValueError:
                    continue
                
                # Parse Type/Status
                if "WATCH:" in rest:
                    # WATCH: STATUS (Details)
                    _, content = rest.split("WATCH:", 1)
                    content = content.strip()
                    # Split STATUS and (Details)
                    if " (" in content and content.endswith(")"):
                        status_str, details_str = content.split(" (", 1)
                        details_str = details_str.rstrip(")")
                    else:
                        status_str = content
                        details_str = ""
                        
                    entries.append(LogEntry(ts, status_str, details_str))
                    
            except Exception:
                continue # Skip malformed lines
                
    return entries

def compute_stability(entries: List[LogEntry]) -> float:
    if not entries:
        return 0.0
    ok_count = sum(1 for e in entries if e.status == "OK")
    return (ok_count / len(entries)) * 100.0

def extract_disk_metrics(entries: List[LogEntry]) -> List[Tuple[datetime, float]]:
    metrics = []
    # Pattern: Disk Free: 47.59%
    pattern = re.compile(r"Disk Free: (\d+\.\d+)%")
    
    for e in entries:
        if e.status == "OK":
            match = pattern.search(e.details)
            if match:
                val = float(match.group(1))
                metrics.append((e.timestamp, val))
    return metrics

def compute_linear_trend(data: List[Tuple[datetime, float]]) -> Dict[str, float]:
    """
    Compute slope (change per day).
    Requires at least 3 points.
    """
    if len(data) < 3:
        return {}
        
    # Convert dates to days from start
    start_time = data[0][0]
    points = []
    for ts, val in data:
        delta_days = (ts - start_time).total_seconds() / 86400.0
        points.append((delta_days, val))
        
    n = len(points)
    sum_x = sum(p[0] for p in points)
    sum_y = sum(p[1] for p in points)
    sum_xy = sum(p[0]*p[1] for p in points)
    sum_xx = sum(p[0]*p[0] for p in points)
    
    # Linear Regression: y = mx + c
    # m = (N*Sum(xy) - Sum(x)*Sum(y)) / (N*Sum(xx) - (Sum(x))^2)
    
    denominator = (n * sum_xx - sum_x * sum_x)
    if denominator == 0:
        return {"slope": 0.0, "current": points[-1][1]}
        
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    
    current_val = points[-1][1]
    
    # 7-day change (projected or actual if we have 7 days)
    # Just use slope * 7
    change_7d = slope * 7.0
    
    return {
        "slope": slope,
        "current": current_val,
        "change_7d": change_7d
    }

def project_threshold(current: float, slope: float, threshold: float) -> Optional[float]:
    """Return days until threshold breach. None if not trending there."""
    if slope >= 0:
        return None # Not dropping
    
    # current + slope * days = threshold
    # slope * days = threshold - current
    # days = (threshold - current) / slope
    
    if current <= threshold:
        return 0.0
        
    days = (threshold - current) / slope
    return days

from dataclasses import dataclass

def execute_sentinel():
    print(">>> ASSIGNMENT 005: TREND SENTINEL <<<")
    
    # 1. Mode Guard
    if DEFAULT_LEARNING_MODE != LearningMode.EVALUATE:
        print("CRITICAL: Sentinel must run in EVALUATE mode.")
        sys.exit(3)
        
    # 2. Parse Logs
    source_entries = parse_log(SOURCE_LOG)
    env_entries = parse_log(ENV_LOG)
    
    # 3. Compute Metrics
    source_stability = compute_stability(source_entries)
    env_stability = compute_stability(env_entries)
    
    disk_data = extract_disk_metrics(env_entries)
    disk_trend = compute_linear_trend(disk_data)
    
    # 4. Generate Report
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_date = datetime.now().strftime("%Y-%m-%d")
    report_file = REPORT_DIR / f"trend_report_{report_date}.md"
    
    report_lines = [
        f"# Trend Sentinel Report — {report_date}",
        "",
        "## Source Integrity",
        f"- Checks analyzed: {len(source_entries)}",
        f"- Stability: {source_stability:.1f}%",
        "",
        "## Environment Integrity",
        f"- Checks analyzed: {len(env_entries)}",
        f"- Stability: {env_stability:.1f}%"
    ]
    
    # Disk Section
    report_lines.append("- Disk Free:")
    if disk_trend:
        curr = disk_trend["current"]
        slope = disk_trend["slope"]
        chg_7 = disk_trend["change_7d"]
        
        report_lines.append(f"  - Current: {curr:.2f}%")
        report_lines.append(f"  - 7-day change: {chg_7:+.2f}%")
        report_lines.append(f"  - Daily trend: {slope:+.3f}% / day")
        
        days_left = project_threshold(curr, slope, DISK_THRESHOLD)
        if days_left is not None:
             report_lines.append(f"  - Projection ({DISK_THRESHOLD}% threshold): ~{days_left:.1f} days")
    elif disk_data:
        # Not enough data for trend, just show current
        curr = disk_data[-1][1]
        report_lines.append(f"  - Current: {curr:.2f}%")
        report_lines.append("  - Trend: Insufficient data (< 3 points)")
    else:
        report_lines.append("  - No data found")
        
    report_lines.append("")
    report_lines.append("## Anomalies")
    
    anomalies = []
    if source_stability < 100.0:
        anomalies.append("Source stability degraded (< 100%)")
    if env_stability < 100.0:
        anomalies.append("Environment stability degraded (< 100%)")
        
    if anomalies:
        for a in anomalies:
            report_lines.append(f"- {a}")
    else:
        report_lines.append("- None detected")
        
    report_lines.append("")
    report_lines.append("## Notes")
    report_lines.append("- This report is observational only.")
    report_lines.append("- No action was taken.")
    
    # Write Report
    report_content = "\n".join(report_lines)
    report_file.write_text(report_content, encoding="utf-8")
    
    # 5. Console Output
    print("TREND SENTINEL OK")
    print(f"- Source stability: {source_stability:.1f}%")
    print(f"- Env stability: {env_stability:.1f}%")
    if disk_trend:
         print(f"- Disk free trending: {disk_trend['slope']:+.3f}% / day")
    else:
         print("- Disk free trending: Insufficient data")
         
    if anomalies:
        print(f"- Issues: {', '.join(anomalies)}")
    else:
        print("- No critical drift detected")
        
    print(f"Report: {report_file}")

if __name__ == "__main__":
    execute_sentinel()
