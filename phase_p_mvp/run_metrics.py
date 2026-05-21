"""Run structural metrics, save output as JSON."""
import json
from structural_metrics import compute_metrics, evaluate_hypothesis_against_metrics

metrics = compute_metrics()

# Serialize
out = {k: v for k, v in metrics.items() if k != "callsites"}
out["unique_caller_modules"] = sorted(out["unique_caller_modules"])
out["freeze_reasons"] = sorted(out.get("freeze_reasons", set()))

# Callsite summary
out["callsites"] = [
    f"[{cs['context_type']}] {cs['file']}:{cs['line_number']} -> {cs['line_text'][:80]}"
    for cs in metrics["callsites"]
]

# Evaluate each hypothesis
for h_type in ["centralized", "distributed", "manual"]:
    out[f"eval_{h_type}"] = evaluate_hypothesis_against_metrics(h_type, metrics)

with open("metrics_output.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

print("Saved to metrics_output.json")
