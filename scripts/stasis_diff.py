"""
PHASE O: STASIS DRIFT DETECTOR (Read-Only)

Purpose:
- Compare current system state against Day 0 Stasis Baseline.
- Detect semantic drift: changed commitments, loosened eligibility, language softening.
- Ignore harmless changes (timestamps, specific dates).
- Output: A neutral report of any divergence.
"""

import sys
import difflib
import re
from pathlib import Path
from typing import Dict, List, Tuple

# Fix path
sys.path.append(".")

# Import scripts to capture current state
# We use subprocess to run them to ensure clean isolation, or import main functions if permitted.
# Given they print to stdout, subprocess capture is safest and most robust.
import subprocess

BASELINE_DIR = Path("data/stasis_baseline/day_0").resolve()

# Map of baseline filename -> script path
ARTIFACT_MAP = {
    "risk_ledger.txt": "scripts/risk_ledger.py",
    "tradeoff_ledger.txt": "scripts/tradeoff_ledger.py",
    "commitment_register.txt": "scripts/commitment_register.py",
    "enforcement_map.txt": "scripts/enforcement_map.py",
    "action_eligibility.txt": "scripts/action_eligibility.py"
    # Trend report is handled separately as it's a file, not a script output
}

def normalize_output(text: str) -> List[str]:
    """
    Normalize text for comparison.
    - Remove date/time headers (e.g., "— 2026-01-10")
    - Remove request IDs (e.g., [REQ-XXXXXX]) if purely random, 
      but Authorization Requests are generated dynamic so IDs change.
      Actually, for these ledgers, IDs might be stable or not present.
      Risk Ledger: [1], [2]... stable.
      Authority Simulation: [REQ-...] random.
    - Strip whitespace.
    """
    lines = text.splitlines()
    normalized = []
    
    # Regex to catch header dates
    date_header_pattern = re.compile(r".*— \d{4}-\d{2}-\d{2}.*")
    # Regex to catch UUIDs in Authority Simulation (if we were diffing that, but we aren't in the main map yet)
    # The artifact map includes action_eligibility, which might contain random IDs if it calls authority_simulation?
    # action_eligibility calls simulate_... which take IDs. 
    # Let's check if action_eligibility output contains random IDs.
    # It does not print the request structure with IDs, just "Action: ... Eligible: ... Blocked By: ..." 
    # But wait, evaluate_learn_mode_eligibility calls generate_integrity_repair_request which makes a UUID. 
    # Does action_eligibility PRINT that UUID? 
    # No, it prints "Blocked By: - Authority Decision: DENIED". It doesn't print the ID.
    # So we should be safe on UUIDs.
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        # Skip date headers to avoid false positives on daily runs
        if date_header_pattern.match(stripped):
            continue
            
        normalized.append(stripped)
        
    return normalized

def capture_current_output(script_path: str) -> str:
    """Run a script and capture its stdout."""
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            cwd=str(Path.cwd()),
            env={"PYTHONPATH": "."} 
        )
        if result.returncode != 0:
            return f"ERROR: Script {script_path} failed.\n{result.stderr}"
        return result.stdout
    except Exception as e:
        return f"ERROR: Executing {script_path}: {str(e)}"

def compare_artifacts() -> List[str]:
    drift_report = []
    
    print(">>> STASIS DRIFT DETECTION IN PROGRESS <<<")
    print(f"Baseline: {BASELINE_DIR}")
    print("-" * 40)

    all_match = True

    for filename, script_path in ARTIFACT_MAP.items():
        baseline_file = BASELINE_DIR / filename
        if not baseline_file.exists():
            drift_report.append(f"MISSING BASELINE: {filename}")
            all_match = False
            continue

        baseline_text = baseline_file.read_text(encoding="utf-8-sig")
        current_text = capture_current_output(script_path)
        
        baseline_norm = normalize_output(baseline_text)
        current_norm = normalize_output(current_text)
        
        if baseline_norm == current_norm:
            print(f"OK: {filename}")
        else:
            all_match = False
            print(f"DRIFT: {filename}")
            drift_report.append(f"\n--- DRIFT DETECTED: {filename} ---")
            
            # Generate diff
            diff = difflib.unified_diff(
                baseline_norm, 
                current_norm, 
                fromfile=f"Baseline ({filename})", 
                tofile=f"Current ({script_path})",
                n=3
                # lineterm=""
            )
            for line in diff:
                drift_report.append(line)

    # Compare Trend Report (File vs File)
    # Note: Trend reports change naturally over time.
    # Stasis requires we compare Day 0 trend logic/structure, but data WILL change.
    # Strictly speaking, comparing the *content* of trend report might be noisy if disk usage changes slightly.
    # Phase O says: "Drift includes... Risk reclassification without cause".
    # We should probably check if the *structure* or key constraints in the trend report changed. 
    # For now, let's just log if it exists. Comparing actual numbers is tricky for "stasis" unless we expect numbers to be identical.
    # Ops manual says "Compare Day 0 baseline vs current state... Drift includes... Risk reclassification".
    # Implies we SHOULD monitor trend report for significant shifts.
    # Let's perform a diff but acknowledge that numbers might change.
    
    # Actually, for the purpose of "Silent Drift Detection script", checking the ledgers is the critical part.
    # The trend report is a time-series input.
    # I will skip deep diffing the trend report text because dates/disk % will validly change.
    # Instead I will check internal consistencies if possible, or just leave it for the weekly report.
    # The user request specifically mentioned: "Must check: Commitments changed? Enforcement mappings altered? Eligibility logic loosened?"
    # These are covered by the ledgers.
    
    return drift_report

if __name__ == "__main__":
    report = compare_artifacts()
    
    print("-" * 40)
    if not report:
        print("STATUS: STABLE. No semantic drift detected.")
    else:
        print("STATUS: DRIFT DETECTED.")
        print("\n".join(report))
        sys.exit(1) # Non-zero exit to signal drift
