"""
sensitivity_analysis.py — Continuous fragility analysis.

REDESIGNED: Sweeps metrics across ranges instead of discrete pokes.
Reports decision boundaries and margin of safety.
Fixes the list(scores.keys())[0] bug: uses max(scores, key=scores.get).
"""
import json
import math
from pathlib import Path
from copy import deepcopy

from auto_hypotheses import auto_generate_hypotheses, STRUCTURAL_ARCHETYPES, score_archetype


def find_winner(scores: dict) -> str:
    """Return the archetype with the highest score. NOT dict-order dependent."""
    return max(scores, key=scores.get)


def sweep_metric(metrics: dict, method_name: str, desc: str,
                 metric_key: str, min_val: float, max_val: float, steps: int = 30):
    """
    Sweep a metric across its full range and record how scores change.
    Returns list of (value, winner, winner_score, all_scores).
    """
    results = []
    for i in range(steps + 1):
        val = min_val + (max_val - min_val) * i / steps
        
        p_metrics = deepcopy(metrics)
        p_metrics[metric_key] = val
        
        _, scores, profile = auto_generate_hypotheses(desc, method_name, p_metrics)
        winner = find_winner(scores)
        
        results.append({
            "value": round(val, 3),
            "winner": winner,
            "winner_score": round(scores[winner], 4),
            "ambiguity": profile.ambiguity,
            "entropy": round(profile.entropy, 4),
            "vector": profile.vector,
            "scores": {k: round(v, 4) for k, v in scores.items()},
        })
    
    return results


def find_decision_boundaries(sweep_results: list) -> list:
    """
    Find exact values where the winning archetype changes.
    These are the system's decision boundaries.
    """
    boundaries = []
    for i in range(1, len(sweep_results)):
        prev = sweep_results[i-1]
        curr = sweep_results[i]
        
        # Check for archetype flip OR ambiguity shift
        flip = prev["winner"] != curr["winner"]
        ambiguity_shift = prev["ambiguity"] != curr["ambiguity"]
        
        if flip or ambiguity_shift:
            boundaries.append({
                "at_value": curr["value"],
                "type": "FLIP" if flip else "SHIFT",
                "from": f"{prev['winner']} ({prev['ambiguity']})",
                "to": f"{curr['winner']} ({curr['ambiguity']})",
                "entropy_delta": round(curr["entropy"] - prev["entropy"], 3),
            })
    return boundaries


def margin_of_safety(current_value: float, boundaries: list) -> float:
    """
    Distance from current metric value to nearest decision boundary.
    Higher = more robust.
    """
    if not boundaries:
        return float('inf')
    
    return min(abs(current_value - b["at_value"]) for b in boundaries)


def run_full_analysis(metrics: dict, method_name: str, desc: str) -> dict:
    """
    Run continuous sensitivity analysis for one method.
    Sweeps each key metric and finds decision boundaries.
    """
    # Get baseline
    _, scores, profile = auto_generate_hypotheses(desc, method_name, metrics)
    baseline_winner = find_winner(scores)
    baseline_score = scores[baseline_winner]
    
    report = {
        "baseline": {
            "winner": baseline_winner,
            "score": round(baseline_score, 4),
            "ambiguity": profile.ambiguity,
            "entropy": round(profile.entropy, 4),
            "all_scores": {k: round(v, 4) for k, v in scores.items()},
        },
        "sweeps": {},
    }
    
    # Define sweep ranges for each metric
    sweep_configs = [
        ("unique_caller_files", 1, 10),
        ("dominant_file_ratio", 0.0, 1.0),
        ("automatic_ratio", 0.0, 1.0),
        ("manual_ratio", 0.0, 1.0),
        ("reason_enum_count", 0, 8),
    ]
    
    for metric_key, min_val, max_val in sweep_configs:
        if metric_key not in metrics:
            continue
        
        sweep = sweep_metric(metrics, method_name, desc, metric_key, min_val, max_val, steps=20)
        boundaries = find_decision_boundaries(sweep)
        current_val = metrics[metric_key]
        margin = margin_of_safety(current_val, boundaries)
        
        report["sweeps"][metric_key] = {
            "current_value": current_val,
            "boundaries": boundaries,
            "margin_of_safety": round(margin, 3) if margin != float('inf') else "INF",
            "num_flips": len(boundaries),
        }
    
    return report


def format_text_report(reports: dict) -> str:
    """Format the analysis as human-readable text."""
    lines = []
    lines.append("=" * 70)
    lines.append("  CONTINUOUS SENSITIVITY ANALYSIS — PROBABILISTIC SCORING")
    lines.append("=" * 70)
    
    for method, report in reports.items():
        lines.append(f"\n{'─' * 60}")
        lines.append(f"  METHOD: {method}")
        lines.append(f"{'─' * 60}")
        
        b = report["baseline"]
        lines.append(f"  Baseline: {b['winner']} (score={b['score']:.4f})")
        lines.append(f"  Ambiguity: {b['ambiguity']} (entropy={b['entropy']})")
        lines.append(f"  All scores: {', '.join(f'{k}={v:.4f}' for k,v in sorted(b['all_scores'].items(), key=lambda x:x[1], reverse=True))}")
        
        for metric, sweep in report["sweeps"].items():
            lines.append(f"\n  Metric: {metric}")
            lines.append(f"    Current: {sweep['current_value']}")
            lines.append(f"    Margin of safety: {sweep['margin_of_safety']}")
            lines.append(f"    Structural changes: {sweep['num_flips']}")
            
            for bd in sweep["boundaries"]:
                lines.append(f"      @ {metric}={bd['at_value']} [{bd['type']}]: {bd['from']} → {bd['to']} (ΔH={bd['entropy_delta']})")
        
        # Overall fragility assessment
        total_flips = sum(s["num_flips"] for s in report["sweeps"].values())
        min_margin = min(
            (s["margin_of_safety"] for s in report["sweeps"].values() if s["margin_of_safety"] != "INF"),
            default="INF"
        )
        
        lines.append(f"\n  VERDICT: {'FRAGILE' if total_flips > 2 else 'MODERATE' if total_flips > 0 else 'ROBUST'}")
        lines.append(f"    Total boundary crossings: {total_flips}")
        lines.append(f"    Minimum margin of safety: {min_margin}")
    
    return "\n".join(lines)


def main():
    res_path = Path("auto_hypothesis_result.json")
    if not res_path.exists():
        print("No results found. Run auto_hypotheses.py first.")
        return
    
    data = json.loads(res_path.read_text(encoding="utf-8"))
    
    all_reports = {}
    for method, info in data.items():
        metrics = info["metrics"]
        report = run_full_analysis(metrics, method, "Transition Analysis")
        all_reports[method] = report
    
    # Write human-readable report
    text_report = format_text_report(all_reports)
    Path("fragility_report.txt").write_text(text_report, encoding="utf-8")
    
    # Write machine-readable report
    Path("fragility_report.json").write_text(
        json.dumps(all_reports, indent=2, default=str), encoding="utf-8"
    )
    
    print(text_report)
    print("\nReports written to fragility_report.txt and fragility_report.json")


if __name__ == "__main__":
    main()
