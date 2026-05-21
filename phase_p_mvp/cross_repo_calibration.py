"""
cross_repo_calibration.py — Empirical calibration from real-world repos.

HIGH-DIMENSIONAL STRUCTURAL DISCOVERY EDITION (Phase Q)

Clones diverse Python repos, extracts 14+ structural metrics,
and saves the raw high-dimensional vectors for PCA analysis.
"""
import json
import os
import subprocess
import statistics
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
from copy import deepcopy

# Import the metrics engine (now with configurable source_root)
from structural_metrics import compute_metrics


# ============================================================
# CONFIGURATION
# ============================================================

REPOS_DIR = Path(__file__).parent / "calibration_repos"

# Diverse Python repos — small enough to clone fast, well-structured
REPOS = [
    {"name": "httpx", "url": "https://github.com/encode/httpx.git", "src_subdir": "httpx"},
    {"name": "rich", "url": "https://github.com/Textualize/rich.git", "src_subdir": "rich"},
    {"name": "textual", "url": "https://github.com/Textualize/textual.git", "src_subdir": "src/textual"},
    {"name": "fastapi", "url": "https://github.com/tiangolo/fastapi.git", "src_subdir": "fastapi"},
    {"name": "paramiko", "url": "https://github.com/paramiko/paramiko.git", "src_subdir": "paramiko"},
    {"name": "celery", "url": "https://github.com/celery/celery.git", "src_subdir": "celery"},
    {"name": "scrapy", "url": "https://github.com/scrapy/scrapy.git", "src_subdir": "scrapy"},
    {"name": "click", "url": "https://github.com/pallets/click.git", "src_subdir": "src/click"},
]

# Universal state-transition methods to search for
TARGET_METHODS = [
    "close",
    "shutdown",
    "stop",
    "reset",
    "disconnect",
    "lock",
    "unlock",
    "start",
    "open",
    "connect",
]

# NO RESTRICTED KEY_METRICS LIST
# We collect ALL metrics returned by compute_metrics()


# ============================================================
# REPO MANAGEMENT
# ============================================================

def clone_repo(repo: dict) -> Path:
    """Clone a repo (shallow, fast). Returns path to source directory."""
    repo_dir = REPOS_DIR / repo["name"]
    
    if repo_dir.exists():
        print(f"  [SKIP] {repo['name']} already cloned")
    else:
        print(f"  [CLONE] {repo['name']}...")
        subprocess.run(
            ["git", "clone", "--depth", "1", "--single-branch", repo["url"], str(repo_dir)],
            capture_output=True, text=True, timeout=120
        )
    
    src_path = repo_dir / repo["src_subdir"]
    if not src_path.exists():
        # Fallback: use repo_dir itself
        src_path = repo_dir
    
    return src_path


# ============================================================
# DATA COLLECTION
# ============================================================

def collect_metrics(src_path: Path, methods: List[str]) -> List[dict]:
    """
    Run metrics extraction for each method on a single repo.
    Returns list of {method, metrics} dicts (only where calls > 0).
    """
    results = []
    
    for method in methods:
        try:
            metrics = compute_metrics(method, source_root=src_path)
        except Exception as e:
            print(f"    [ERROR] {method}: {e}")
            continue
        
        if metrics["total_calls"] > 0:
            # KEEP EVERYTHING — High-Dimensional Capture
            clean = metrics.copy()
            
            # Ensure metadata is clean
            clean["dominant_file"] = metrics.get("dominant_file", "unknown")
            
            results.append({"method": method, "metrics": clean})
    
    return results


# ============================================================
# STATISTICAL ANALYSIS
# ============================================================

def compute_distributions(all_data: List[dict]) -> dict:
    """
    Compute distributions for ALL numeric metrics found in the data.
    """
    if not all_data:
        return {}
        
    # Ignore non-numeric metadata
    ignore = {"repo", "method", "dominant_file", "context", "total_calls"}
    
    # Collect all possible keys
    all_keys = set()
    for entry in all_data:
        for k, v in entry["metrics"].items():
            if k not in ignore and isinstance(v, (int, float)):
                all_keys.add(k)
    
    distributions = {}
    
    for key in all_keys:
        values = []
        for entry in all_data:
            val = entry["metrics"].get(key, 0)
            if isinstance(val, bool):
                val = 1.0 if val else 0.0
            values.append(float(val))
        
        if not values:
            continue
        
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        
        mean_val = statistics.mean(values)
        
        distributions[key] = {
            "count": n,
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "mean": round(mean_val, 4),
            "median": round(statistics.median(values), 4),
            "stdev": round(statistics.stdev(values), 4) if n > 1 else 0.0,
            "variance": round(statistics.variance(values), 6) if n > 1 else 0.0,
            "p25": round(sorted_vals[n // 4], 4) if n >= 4 else round(sorted_vals[0], 4),
            "p75": round(sorted_vals[3 * n // 4], 4) if n >= 4 else round(sorted_vals[-1], 4),
        }
    
    return distributions


def print_variance_report(distributions: dict):
    """Print variance report to help identify dead metrics."""
    print(f"\n{'='*75}")
    print(f"  VARIANCE REPORT (High-Dimensional Audit)")
    print(f"{'='*75}")
    print(f"  {'METRIC':30s} {'MIN':<8} {'MAX':<8} {'MEAN':<8} {'VAR':<10} {'STATUS'}")
    print(f"  {'-'*30} {'-'*8} {'-'*8} {'-'*8} {'-'*10} {'-'*10}")
    
    sorted_keys = sorted(distributions.keys())
    for k in sorted_keys:
        d = distributions[k]
        var = d.get("variance", 0)
        # Threshold: if variance is extremely low, it's effectively a constant
        status = "DEAD" if var < 0.000001 else "ALIVE"
        
        # Highlight DEAD metrics
        if status == "DEAD":
             status_str = f"!! {status} !!"
        else:
             status_str = status
             
        print(f"  {k:30s} {d['min']:<8.2f} {d['max']:<8.2f} {d['mean']:<8.2f} {var:<10.4f} {status_str}")
    print(f"{'='*75}\n")


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 70)
    print("  HIGH-DIMENSIONAL STRUCTURAL DISCOVERY (Metric Explosion)")
    print("=" * 70)
    
    # Step 1: Clone repos
    print("\n--- STEP 1: CLONING REPOS ---")
    REPOS_DIR.mkdir(exist_ok=True)
    
    repo_paths = {}
    for repo in REPOS:
        try:
            src_path = clone_repo(repo)
            repo_paths[repo["name"]] = src_path
            # print(f"  {repo['name']}: {src_path}")
        except Exception as e:
            print(f"  [FAILED] {repo['name']}: {e}")
    
    if not repo_paths:
        print("No repos cloned.")
        return
    
    # Step 2: Collect metrics
    print("\n--- STEP 2: EXTRACTING 14-DIM VECTORS ---")
    
    all_data = []
    
    for repo_name, src_path in repo_paths.items():
        print(f"  Processing {repo_name}...")
        results = collect_metrics(src_path, TARGET_METHODS)
        
        print(f"    Found {len(results)} valid transitions")
        
        for r in results:
            r["repo"] = repo_name
            all_data.append(r)
    
    print(f"\n  Total data points: {len(all_data)}")
    
    if len(all_data) < 5:
        print("Not enough data points.")
        return
    
    # Step 3: Compute distributions (and Variance Audit)
    print("\n--- STEP 3: VARIANCE AUDIT ---")
    distributions = compute_distributions(all_data)
    print_variance_report(distributions)
    
    # Step 4: Save Raw High-Dim Data
    output_file = Path("calibration_data_high_dim.json")
    results = {
        "timestamp": str(datetime.now()),
        "repo_count": len(REPOS),
        "data_points": len(all_data),
        "distributions": distributions,
        "raw_data": all_data
    }
    
    output_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nHigh-dimensional data saved to {output_file.absolute()}")
    print("Ready for PCA.")


if __name__ == "__main__":
    main()
