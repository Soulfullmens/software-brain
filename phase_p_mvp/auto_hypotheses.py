"""
auto_hypotheses.py — Probabilistic hypothesis generation from computed metrics.

REDESIGNED: Sigmoid-based continuous likelihood scoring.
No more boolean thresholds. No more cliffs.

Each archetype defines likelihood parameters per metric.
Overall score = weighted geometric mean of individual likelihoods.
"""
import math
from typing import Dict, List, Tuple
from structural_metrics import compute_metrics
from structural_profile import compute_profile, format_profile, StructuralProfile
from controller.hypothesis import Hypothesis, HypothesisStatus


# ============================================================
# MATHEMATICAL FOUNDATION
# ============================================================

def sigmoid(x: float, center: float, steepness: float) -> float:
    """
    Compute sigmoid likelihood for a single metric.
    
    Args:
        x: observed metric value
        center: transition point (where likelihood = 0.5)
        steepness: positive = high values favored, negative = low values favored
                   magnitude controls sharpness (higher = sharper)
    
    Returns:
        likelihood in (0, 1)
    """
    z = steepness * (x - center)
    # Clamp to prevent overflow
    z = max(-20.0, min(20.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def weighted_geometric_mean(likelihoods: List[float], weights: List[float]) -> float:
    """
    Compute weighted geometric mean of likelihoods.
    
    Formula: exp( (1/W) * sum(w_i * log(L_i)) )
    
    If any likelihood is near zero, the whole score drops hard.
    This is intentional — one catastrophically bad metric signal
    should tank the entire archetype, not get averaged away.
    """
    if not likelihoods:
        return 0.0
    
    W = sum(weights)
    if W == 0:
        return 0.0
    
    log_sum = 0.0
    for L, w in zip(likelihoods, weights):
        # Floor at 0.001 to prevent log(0)
        L = max(0.001, L)
        log_sum += w * math.log(L)
    
    return math.exp(log_sum / W)


# ============================================================
# STRUCTURAL ARCHETYPES — PROBABILISTIC EDITION
# ============================================================
#
# Each archetype defines:
#   - template: human-readable description
#   - likelihood_params: list of {metric, center, steepness, weight}
#     * metric: key in the metrics dict
#     * center: where sigmoid crosses 0.5
#     * steepness: positive = "high values support this archetype"
#                  negative = "low values support this archetype"
#     * weight: how much this metric matters (higher = more important)
#   - missing_evidence_templates: what would confirm this
#   - falsifier_templates: what would kill this
#
# CALIBRATION NOTES (2026-02-12):
#   Parameters calibrated from cross-repo experiment:
#   8 repos (httpx, rich, textual, fastapi, paramiko, celery, scrapy, click)
#   46 data points, 10 state-transition methods.
#
#   Empirical distributions:
#     unique_caller_files: median=5.5, P25=1, P75=13, IQR=12 (WIDE spread)
#     dominant_file_ratio: median=0.447, P25=0.254, P75=1.0, IQR=0.746
#     automatic_ratio:     median=0.488, P25=0.258, P75=0.649, IQR=0.391
#     manual_ratio:        median=0.0 (near-zero everywhere — classifier is domain-specific)
#     reason_enum_count:   median=0.0 (most repos don't use XReason enums)
#
#   KNOWN LIMITATION: manual_ratio and reason_enum_count are unreliable
#   cross-repo. Their weights are reduced accordingly.

STRUCTURAL_ARCHETYPES = {
    "centralized": {
        "template": "{transition} is controlled by a centralized authority — a single module mediates all transitions",
        "likelihood_params": [
            # Few callers favors centralized. Empirical median=5.5, so center=5.5
            # Steepness=-0.33 (empirical IQR=12, very wide spread)
            {"metric": "unique_caller_files", "center": 5.5, "steepness": -0.33, "weight": 3.0},
            # High dominance favors centralized. Empirical median=0.447
            {"metric": "dominant_file_ratio", "center": 0.447, "steepness": 5.36, "weight": 2.5},
            # automatic_ratio: empirical median=0.488
            {"metric": "automatic_ratio", "center": 0.488, "steepness": 3.0, "weight": 1.0},
        ],
        "missing_evidence_templates": [
            "A single module that mediates ALL {method_name} transitions",
            "Other modules delegate to this authority rather than transitioning directly",
            "A centralized {method_name}() method that all paths converge to",
        ],
        "falsifier_templates": [
            "Multiple modules call {method_name}() independently (>2 unique callers)",
            "No single module accounts for >50% of {method_name} calls",
        ],
    },
    "distributed": {
        "template": "{transition} is driven by distributed local triggers — multiple independent modules initiate transitions for different reasons",
        "likelihood_params": [
            # Many callers favors distributed. Empirical median=5.5, IQR=12
            {"metric": "unique_caller_files", "center": 5.5, "steepness": 0.33, "weight": 3.0},
            # Low dominance favors distributed. Empirical median=0.447
            {"metric": "dominant_file_ratio", "center": 0.447, "steepness": -5.36, "weight": 2.5},
            # reason_enum_count: unreliable cross-repo (median=0). Weight reduced.
            {"metric": "reason_enum_count", "center": 1.0, "steepness": 1.0, "weight": 0.5},
            # High automation favors distributed. Empirical median=0.488
            {"metric": "automatic_ratio", "center": 0.488, "steepness": 3.0, "weight": 1.5},
        ],
        "missing_evidence_templates": [
            "Multiple independent modules that each call {method_name}() for different reasons",
            "No single authority that all {method_name} paths route through",
            "At least 3 distinct modules with independent {method_name} logic",
            "Majority of calls are automated triggers",
        ],
        "falsifier_templates": [
            "All {method_name}() calls routed through a single authority layer",
            "Only 1-2 files ever call {method_name}() directly",
            "Majority of calls are manual overrides",
        ],
    },
    "manual_first": {
        "template": "{transition} is primarily initiated by manual or external authorization — automated triggers are secondary",
        "likelihood_params": [
            # CAUTION: manual_ratio is near-zero in most repos (empirical median=0.0)
            # This archetype is domain-specific, not general. Weight reduced.
            {"metric": "manual_ratio", "center": 0.1, "steepness": 4.0, "weight": 2.0},
            # Low automation favors manual_first. Empirical median=0.488
            {"metric": "automatic_ratio", "center": 0.488, "steepness": -3.0, "weight": 2.5},
            # Few callers. Empirical median=5.5
            {"metric": "unique_caller_files", "center": 5.5, "steepness": -0.33, "weight": 1.5},
        ],
        "missing_evidence_templates": [
            "Explicit permission or authority check before {method_name}() calls",
            "Human-initiated {method_name} mechanism (operator override)",
            "Majority of {method_name} paths require external authorization",
        ],
        "falsifier_templates": [
            "Majority of {method_name}() calls are fully automatic",
            "No manual {method_name} mechanism exists",
            "High number of dispersed manual call sites (>3)",
        ],
    },
    "conditional_threshold": {
        "template": "{transition} is triggered by numeric threshold conditions (coherence, budget, severity) evaluated in a single decision function",
        "likelihood_params": [
            # High automation favors threshold-based. Empirical median=0.488
            {"metric": "automatic_ratio", "center": 0.488, "steepness": 4.0, "weight": 3.0},
            # Few callers favors threshold. Empirical median=5.5
            {"metric": "unique_caller_files", "center": 5.5, "steepness": -0.33, "weight": 2.0},
            # High dominance favors threshold. Empirical median=0.447
            {"metric": "dominant_file_ratio", "center": 0.447, "steepness": 5.36, "weight": 1.5},
        ],
        "missing_evidence_templates": [
            "A decision function that evaluates numeric thresholds before {method_name}()",
            "Threshold variables (coherence, budget, severity) checked before transition",
            "A single evaluation point that determines whether to {method_name}",
        ],
        "falsifier_templates": [
            "No threshold-based conditions exist before {method_name}()",
            "{method_name}() is called without any numeric condition checks",
        ],
    },
}


def score_archetype(archetype: dict, metrics: Dict) -> Tuple[float, List[dict]]:
    """
    Score how well an archetype fits the observed metrics.
    
    Returns:
        (score, details) where:
        - score: weighted geometric mean of sigmoid likelihoods [0, 1]
        - details: list of {metric, value, likelihood, weight} for transparency
    """
    params = archetype.get("likelihood_params", [])
    if not params:
        return 0.5, []
    
    likelihoods = []
    weights = []
    details = []
    
    for p in params:
        metric_name = p["metric"]
        center = p["center"]
        steepness = p["steepness"]
        weight = p["weight"]
        
        value = metrics.get(metric_name, 0)
        if isinstance(value, bool):
            value = 1.0 if value else 0.0
        
        L = sigmoid(float(value), center, steepness)
        
        likelihoods.append(L)
        weights.append(weight)
        details.append({
            "metric": metric_name,
            "value": value,
            "center": center,
            "steepness": steepness,
            "likelihood": round(L, 4),
            "weight": weight,
        })
    
    score = weighted_geometric_mean(likelihoods, weights)
    return round(score, 4), details


def suggest_missing_metrics(scores: Dict[str, float], metrics: Dict) -> List[str]:
    """
    When the system is uncertain, identify what ADDITIONAL metric
    would most reduce ambiguity between competing archetypes.
    
    This is not poetry — it compares the top two archetypes
    and finds which dimensions they disagree on most.
    """
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    if len(ranked) < 2:
        return []
    
    top_name, top_score = ranked[0]
    runner_name, runner_score = ranked[1]
    
    gap = top_score - runner_score
    if gap > 0.3:
        return []  # Clear winner, no ambiguity
    
    suggestions = []
    
    # Compare what metrics the two archetypes care about differently
    top_metrics = {p["metric"] for p in STRUCTURAL_ARCHETYPES[top_name]["likelihood_params"]}
    runner_metrics = {p["metric"] for p in STRUCTURAL_ARCHETYPES[runner_name]["likelihood_params"]}
    
    # Metrics that only one cares about = potential discriminators
    unique_to_top = top_metrics - runner_metrics
    unique_to_runner = runner_metrics - top_metrics
    
    if unique_to_top:
        suggestions.append(f"Metric '{list(unique_to_top)[0]}' distinguishes {top_name} from {runner_name} — strengthen measurement here")
    if unique_to_runner:
        suggestions.append(f"Metric '{list(unique_to_runner)[0]}' distinguishes {runner_name} from {top_name} — strengthen measurement here")
    
    # Suggest metrics NOT currently measured
    unmeasured = []
    if "call_graph_depth" not in metrics:
        unmeasured.append("call_graph_depth (how deep are transition chains?)")
    if "loop_context_ratio" not in metrics:
        unmeasured.append("loop_context_ratio (are calls inside loops?)")
    if "exception_context_ratio" not in metrics:
        unmeasured.append("exception_context_ratio (are calls inside exception handlers?)")
    if "reversibility" not in metrics:
        unmeasured.append("reversibility (does the transition have an inverse?)")
    
    if unmeasured and gap < 0.15:
        suggestions.append(f"Ambiguity is high (gap={gap:.3f}). Consider measuring: {unmeasured[0]}")
    
    return suggestions


def synthesize_archetype(metrics: Dict, transition_desc: str, method_name: str,
                         scores: Dict[str, float]) -> Hypothesis:
    """
    Fallback: Synthesize a structural description when no archetype fits.
    
    Now also reports what metrics would help resolve ambiguity.
    Uses proper HypothesisStatus (not a raw string).
    """
    traits = []
    
    # Analyze dispersion (continuous, not binned)
    files = metrics.get('unique_caller_files', 0)
    if files <= 1:
        traits.append("monolithic single-source origin")
    elif files <= 3:
        traits.append(f"tightly coupled few-source origin ({files} callers)")
    else:
        traits.append(f"highly dispersed origin ({files} callers)")
        
    # Analyze topology
    dom_ratio = metrics.get('dominant_file_ratio', 0)
    dom_file = metrics.get('dominant_file', 'unknown')
    if dom_ratio > 0.7:
        traits.append(f"strongly mediated by {dom_file} ({dom_ratio*100:.0f}% dominance)")
    elif dom_ratio > 0.4:
        traits.append(f"partially concentrated in {dom_file} ({dom_ratio*100:.0f}% dominance)")
    else:
        traits.append("lacking any central coordination point")
        
    # Analyze control mode (continuous)
    auto = metrics.get('automatic_ratio', 0)
    manual = metrics.get('manual_ratio', 0)
    error = metrics.get('error_count', 0)
    
    if auto > 0.7:
        traits.append("driven by fully automated logic")
    elif manual > 0.5:
        traits.append(f"driven primarily by manual intervention ({manual*100:.0f}%)")
    elif auto > 0.2 and manual > 0.2:
        traits.append(f"driven by hybrid triggers (auto={auto*100:.0f}%, manual={manual*100:.0f}%)")
    elif error > 0:
        traits.append("driven by error/safety recovery logic")
    else:
        traits.append("driven by uncategorized trigger logic")

    # Get metric suggestions
    suggestions = suggest_missing_metrics(scores, metrics)
    
    description = f"{transition_desc} exhibits a novel structural pattern: {' / '.join(traits)}."
    
    missing = ["Validation of this unique structural pattern"]
    if suggestions:
        missing.extend(suggestions)
    
    h = Hypothesis(
        statement=description,
        status=HypothesisStatus.PENDING,  # FIXED: was status="synthetic" (invalid)
        confidence=0.1,
        missing_evidence=missing,
        falsifiers=["Standard architectural patterns apply instead"],
        search_hints=[method_name, "structural anomaly"]
    )
    # Tag for identification (not overriding the enum status)
    h._is_synthetic = True
    return h


def auto_generate_hypotheses(
    transition_description: str,
    method_name: str,
    metrics: Dict,
    top_n: int = 3
) -> Tuple[List[Hypothesis], Dict[str, float], StructuralProfile]:
    """
    Automatically generate hypotheses from computed metrics.
    
    Returns:
        (hypotheses, scores, profile)
    """
    # Score all archetypes
    scores = {}
    all_details = {}
    for name, archetype in STRUCTURAL_ARCHETYPES.items():
        score, details = score_archetype(archetype, metrics)
        scores[name] = score
        all_details[name] = details
    
    # Compute structural profile (embedding + ambiguity + neighbors)
    profile = compute_profile(metrics, scores)
    
    # Sort by score — best fit first
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_name, best_score = ranked[0] if ranked else ("none", 0.0)
    
    model_hypotheses = []
    
    # If ambiguity is HIGH, synthesize a structural novelty hypothesis
    if profile.ambiguity in ("ambiguous", "structurally_novel"):
        synthetic_h = synthesize_archetype(metrics, transition_description, method_name, scores)
        model_hypotheses.append(synthetic_h)
        # Still include best misfit for comparison
        selected = [ranked[0]]
    else:
        # Standard selection: best, runner-up, worst (for adversarial contrast)
        if len(ranked) >= top_n:
            selected = [ranked[0], ranked[1], ranked[-1]]
        else:
            selected = ranked[:top_n]
    
    # Phase Q+1: Confidence Integration (Structural Prior)
    # Logic: Structural Anomaly (z_mad) acts as a Bayesian prior on likelihood.
    # Formula: Multiplier = exp(-0.5 * z_eff)
    # where z_eff = 3.0 * (1.0 - exp(-max(0, z) / 3.0))  (Soft Saturation)
    # - Typicality (z <= 0) -> z_eff=0 -> Multiplier=1.0 (Neutral)
    # - Anomaly (z > 0) -> Smoothly penalizes up to max penalty (z->inf => z_eff->3.0 => 0.22x)
    # - Preserves order: z=10 is strictly worse than z=3, unlike hard clamp.
    
    z_raw = getattr(profile, "structural_anomaly_z", 0.0)
    z_clipped = max(0.0, z_raw)
    # Soft saturation curve: asymptote at 3.0, linear near 0
    z_eff = 3.0 * (1.0 - math.exp(-z_clipped / 3.0))
    
    struct_log_prior = -0.5 * z_eff
    struct_multiplier = math.exp(struct_log_prior)
    
    for name, score in selected:
        archetype = STRUCTURAL_ARCHETYPES[name]
        statement = archetype["template"].format(
            transition=transition_description,
            method_name=method_name
        )
        missing = [t.format(method_name=method_name) for t in archetype["missing_evidence_templates"]]
        falsifiers = [t.format(method_name=method_name) for t in archetype["falsifier_templates"]]
        
        # Explain the confidence adjustment if significant
        if abs(struct_multiplier - 1.0) > 0.1:
            direction = "penalized" if struct_multiplier < 1.0 else "boosted"
            falsifiers.append(f"Confidence {direction} by structural prior (z={z_raw:.2f}, x{struct_multiplier:.2f})")
        
        h = Hypothesis(
            statement=statement,
            missing_evidence=missing,
            falsifiers=falsifiers,
            search_hints=[method_name, "transition"]
        )
        
        # Apply Structural Multiplier
        final_conf = float(score) * struct_multiplier
        h.confidence = max(0.01, min(0.99, final_conf)) # Clamp to (0,1)
        
        h._is_synthetic = False
        model_hypotheses.append(h)
    
    return model_hypotheses, scores, profile


# ============================================================
# MAIN — TEST SUITE
# ============================================================

if __name__ == "__main__":
    import json
    from pathlib import Path
    
    tests = [
        ("TEST 1: _freeze (EVALUATE->FROZEN)", "EVALUATE to FROZEN", "_freeze", None),
        ("TEST 2: _unfreeze (FROZEN->CAUTIOUS)", "FROZEN to CAUTIOUS", "_unfreeze", None),
    ]
    
    # Synthetic Ambiguity Test — conflicting metrics
    synthetic_metrics = {
        "total_calls": 100,
        "unique_caller_files": 10,
        "has_central_router": True,
        "dominant_file": "messy_manager.py",
        "dominant_file_ratio": 0.8,
        "manual_ratio": 0.9,
        "automatic_ratio": 0.1,
        "reason_enum_count": 1,
    }
    tests.append(
        ("TEST 3: SYNTHETIC AMBIGUITY", "CONFUSING_TRANSITION", "messy_method", synthetic_metrics)
    )
    
    results_dump = {}

    for title, desc, method, injected_metrics in tests:
        print("=" * 60)
        print(f"  {title}")
        print("=" * 60)
        
        if injected_metrics:
            metrics = injected_metrics
            print("  [Injecting synthetic metrics]")
        else:
            metrics = compute_metrics(method)
        
        print(f"  Metrics: {metrics.get('total_calls', 0)} calls, {metrics.get('unique_caller_files', 0)} files")
        print(f"           DomRatio={metrics.get('dominant_file_ratio', 0):.2f}, Auto={metrics.get('automatic_ratio', 0):.2f}, Man={metrics.get('manual_ratio', 0):.2f}")
        
        hyps, scores, profile = auto_generate_hypotheses(desc, method, metrics)
        
        print(f"\n{format_profile(profile, method)}")
        
        # Winner is max(scores), NOT list(scores.keys())[0]
        winner = max(scores, key=scores.get)
        
        print(f"\n  Archetype scores (probabilistic):")
        for name, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            marker = " <-- WINNER" if name == winner else ""
            print(f"    {name:25s} {score:.4f}{marker}")
        
        # Show per-metric details for winner
        # _, details = score_archetype(STRUCTURAL_ARCHETYPES[winner], metrics)
        # print(f"\n  Winner '{winner}' breakdown:")
        # for d in details:
        #     print(f"    {d['metric']:25s} val={d['value']:<8} L={d['likelihood']:.4f}  (center={d['center']}, k={d['steepness']}, w={d['weight']})")
        
        # Metric suggestions
        suggestions = suggest_missing_metrics(scores, metrics)
        if suggestions:
            print(f"\n  Metric suggestions:")
            for s in suggestions:
                print(f"    -> {s}")
        
        print(f"\n  Generated Hypotheses:")
        for i, h in enumerate(hyps):
            tag = "[SYNTHETIC]" if getattr(h, "_is_synthetic", False) else "[ARCHETYPE]"
            print(f"    {i+1}. {tag} (conf={h.confidence:.4f}) {h.statement[:100]}...")
        print()
        
        results_dump[method] = {
            "metrics": {k:v for k,v in metrics.items() if k not in ['callsites', 'file_distribution', 'unique_caller_modules', 'reasons']},
            "scores": scores,
            "winner": winner,
            "hypotheses": [{"statement": h.statement, "confidence": h.confidence, "synthetic": getattr(h, "_is_synthetic", False)} for h in hyps]
        }
        
    Path(__file__).parent.joinpath("auto_hypothesis_result.json").write_text(
        json.dumps(results_dump, indent=2, default=str), encoding="utf-8"
    )
    print("Results saved to auto_hypothesis_result.json")
