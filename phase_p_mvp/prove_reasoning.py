"""
prove_reasoning.py — Full pipeline: metrics + claims + hypotheses -> disambiguation.

NO hand-crafted EVIDENCE_RULES.
Evidence comes from two sources:
1. Structural metrics (computed from source code)
2. LLM claims (from fast_run_results.json)

Both are evaluated against numeric thresholds.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from controller.belief_state import BeliefState
from controller.hypothesis import (
    Hypothesis,
    generate_hypotheses,
    generate_discriminating_probes,
    evaluate_probes_against_beliefs
)
from structural_metrics import compute_metrics, evaluate_hypothesis_against_metrics


def classify_hypothesis(h: Hypothesis) -> str:
    stmt = h.statement.lower()
    if "centralized" in stmt or "single authority" in stmt or "governor" in stmt:
        return "centralized"
    elif "distributed" in stmt or "multiple independent" in stmt or "local triggers" in stmt:
        return "distributed"
    elif "manual" in stmt or "authorization" in stmt or "higher-level" in stmt:
        return "manual"
    return "unknown"


def main():
    # ==========================================
    # PHASE 1: Compute structural metrics
    # ==========================================
    print("Phase 1: Computing structural metrics from source code...")
    metrics = compute_metrics()
    
    print(f"  _freeze() calls: {metrics['total_freeze_calls']}")
    print(f"  Unique callers: {metrics['unique_caller_files']} files")
    print(f"  Autonomy dominance: {metrics['autonomy_dominance_ratio']*100:.0f}%")
    print(f"  Auto/Manual/Error: {metrics['automatic_count']}/{metrics['manual_count']}/{metrics['error_count']}")
    print(f"  FreezeReasons: {metrics['freeze_reasons_count']}")
    print()
    
    # ==========================================
    # PHASE 2: Load LLM semantic claims
    # ==========================================
    print("Phase 2: Loading LLM claims from fast_run...")
    results = json.loads((Path(__file__).parent / "fast_run_results.json").read_text())
    all_claims = results["claims"]
    
    # Build belief state from LLM claims only
    belief_state = BeliefState()
    for claim in all_claims:
        belief_state.add_evidence(claim.get("source", "unknown"), claim)
    
    print(f"  Claims loaded: {len(all_claims)}")
    print(f"  Beliefs formed: {len(belief_state.beliefs)}")
    print()
    
    # ==========================================
    # PHASE 3: Generate adversarial hypotheses
    # ==========================================
    print("Phase 3: Generating adversarial hypotheses...")
    question = "Under what conditions does the system transition from EVALUATE to FROZEN?"
    hypotheses = generate_hypotheses(question)
    
    for i, h in enumerate(hypotheses):
        print(f"  H{i+1} [{classify_hypothesis(h)}]: {h.statement}")
    print()
    
    # ==========================================
    # PHASE 4: Evaluate hypotheses QUANTITATIVELY
    # ==========================================
    print("Phase 4: Evaluating against structural metrics (no string patterns)...")
    
    for h in hypotheses:
        h_type = classify_hypothesis(h)
        result = evaluate_hypothesis_against_metrics(h_type, metrics)
        
        # Apply quantitative evidence
        for evidence_str in result["evidence"]:
            if result["supported"]:
                h.add_support(
                    evidence_str,
                    relevance=f"Structural metric ({h_type})",
                    strength=result["support_score"] / max(1, len(result["evidence"]))
                )
            elif result["contradicted"]:
                h.add_contradiction(
                    evidence_str,
                    relevance=f"Structural metric contradicts ({h_type})",
                    strength=result["contradict_score"] / max(1, len(result["evidence"]))
                )
        
        # Resolve gaps based on metric evidence
        if h_type == "distributed" and metrics["unique_caller_files"] >= 3:
            h.resolve_gap("Multiple independent modules that each call _freeze() for different reasons")
            h.resolve_gap("At least 3 distinct modules with independent freeze logic")
        if h_type == "distributed" and not metrics["has_central_router"]:
            h.resolve_gap("No single authority module that all freeze paths route through")
        
        if h_type == "centralized" and not metrics["has_central_router"]:
            h.penalize_absence("No central router found in codebase")
        if h_type == "centralized" and metrics["unique_caller_files"] >= 3:
            h.penalize_absence("Multiple independent callers found — contradicts centralization")
        
        if h_type == "manual" and metrics["manual_ratio"] < 0.5:
            h.penalize_absence("Manual calls are minority")
        
        print(f"  H_{h_type}: support={result['support_score']:.3f} contradict={result['contradict_score']:.3f} net={result['net_score']:.3f}")
        for e in result["evidence"]:
            print(f"    -> {e}")
    
    print()
    
    # ==========================================
    # PHASE 5: Generate and evaluate probes
    # ==========================================
    print("Phase 5: Discriminating probes...")
    probes = generate_discriminating_probes(hypotheses)
    print(f"  Generated: {len(probes)} probes")
    
    if probes:
        evaluate_probes_against_beliefs(probes, belief_state.beliefs, hypotheses)
        for p in probes:
            status = "RESOLVED" if p.found else "UNRESOLVED"
            print(f"  [{status}] {p.description[:70]}")
        print()
    
    # ==========================================
    # FINAL: Disambiguation result
    # ==========================================
    print("=" * 60)
    print("  FINAL DISAMBIGUATION (QUANTITATIVE)")
    print("=" * 60)
    
    ranked = sorted(hypotheses, key=lambda h: h.confidence, reverse=True)
    for i, h in enumerate(ranked):
        h_type = classify_hypothesis(h)
        icon = {"confirmed": "V", "supported": "~", "rejected": "X",
                "investigating": "?", "pending": "o"}.get(h.status.value, "?")
        penalty = f" [-{h.expected_but_missing} absence]" if h.expected_but_missing else ""
        print(f"  [{icon}] ({h.confidence:.3f}) [{h_type}] {h.statement}{penalty}")
        for e in (h.supporting[:2] if h.supporting else []):
            print(f"      + {e.belief_statement[:80]}")
        for c in (h.contradicting[:2] if h.contradicting else []):
            print(f"      - {c.belief_statement[:80]}")
        print()
    
    confidences = [h.confidence for h in hypotheses]
    spread = max(confidences) - min(confidences)
    top = ranked[0]
    runner = ranked[1] if len(ranked) > 1 else None
    loser = ranked[-1] if len(ranked) > 1 else None
    
    print(f"  Spread: {spread:.3f}")
    print(f"  Disambiguated: {spread >= 0.3}")
    print(f"  Winner: [{classify_hypothesis(top)}] {top.confidence:.3f}")
    if runner:
        print(f"  Runner-up: [{classify_hypothesis(runner)}] {runner.confidence:.3f}")
        print(f"  Margin: {top.confidence - runner.confidence:.3f}")
    if loser and loser != runner:
        print(f"  Loser: [{classify_hypothesis(loser)}] {loser.confidence:.3f} ({loser.status.value})")
    
    # Save
    output = {
        "method": "quantitative_structural_metrics",
        "metrics_summary": {
            "total_freeze_calls": metrics["total_freeze_calls"],
            "unique_caller_files": metrics["unique_caller_files"],
            "caller_modules": sorted(metrics["unique_caller_modules"]),
            "autonomy_dominance": metrics["autonomy_dominance_ratio"],
            "automatic_ratio": metrics["automatic_ratio"],
            "manual_ratio": metrics["manual_ratio"],
            "freeze_reasons": sorted(metrics["freeze_reasons"]),
            "has_central_router": metrics["has_central_router"],
        },
        "hypotheses": [
            {
                "type": classify_hypothesis(h),
                "statement": h.statement,
                "status": h.status.value,
                "confidence": round(h.confidence, 4),
                "supporting": len(h.supporting),
                "contradicting": len(h.contradicting),
                "remaining_gaps": h.missing_evidence,
                "absence_penalties": h.expected_but_missing,
            } for h in ranked
        ],
        "probes_total": len(probes),
        "probes_resolved": sum(1 for p in probes if p.found),
        "confidence_spread": round(spread, 4),
        "disambiguated": spread >= 0.3,
        "winner": classify_hypothesis(top),
        "winner_confidence": round(top.confidence, 4),
        "margin": round(top.confidence - runner.confidence, 4) if runner else 0,
    }
    Path(__file__).parent.joinpath("reasoning_result.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8"
    )
    print(f"\n  Saved to reasoning_result.json")


if __name__ == "__main__":
    main()
