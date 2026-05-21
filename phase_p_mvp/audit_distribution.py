"""
audit_distribution.py

Validation script for Phase Q+1.
Checks if the empirical Mahalanobis distances (d^2) follow the theoretical Chi-Square distribution.
If they do, our Gaussian assumption holds.
If not, we need to calibrate the scoring function.
"""
import json
import math
from pathlib import Path
from structural_profile import MahalanobisProjector

def calculate_chi2_stats(k: int):
    """Theoretical stats for Chi-Square distribution with k degrees of freedom."""
    mean = k
    variance = 2 * k
    std = math.sqrt(variance)
    return mean, variance, std

def ascii_histogram(values, bins=10):
    """Draw a simple ASCII histogram."""
    if not values:
        return ""
    
    min_v, max_v = min(values), max(values)
    bin_width = (max_v - min_v) / bins
    if bin_width == 0:
        return f"All values are {min_v}"
        
    counts = [0] * bins
    for v in values:
        idx = int((v - min_v) / bin_width)
        if idx >= bins: idx = bins - 1
        counts[idx] += 1
        
    lines = []
    max_count = max(counts)
    for i in range(bins):
        range_str = f"{min_v + i*bin_width:>5.1f} - {min_v + (i+1)*bin_width:>5.1f}"
        bar = "#" * int(counts[i] / max_count * 20) if max_count > 0 else ""
        lines.append(f"{range_str} | {bar} ({counts[i]})")
        
    return "\n".join(lines)

def main():
    print("="*60)
    print("  MAHALANOBIS DISTRIBUTION AUDIT")
    print("="*60)
    
    # 1. Load Data
    data_path = Path("calibration_data_high_dim.json")
    if not data_path.exists():
        print("Data file not found.")
        return
    raw = json.loads(data_path.read_text(encoding="utf-8"))
    
    # 2. Load Projector
    projector = MahalanobisProjector(Path("structural_pca_model.json"))
    dof = len(projector.feature_names) # Degrees of Freedom
    
    print(f"  Degrees of Freedom (k): {dof}")
    
    # 3. Compute d^2 for all points
    d2_values = []
    
    for sample in raw["raw_data"]:
        # Projector returns (pc1, pc2, pc3, d2, z)
        # We only need d2 for the raw distribution audit (z depends on calibration which we are computing)
        _, _, _, d2, _ = projector.project(sample["metrics"])
        d2_values.append(d2)
        
    # 4. Compute Standard Statistics (Mean/Std)
    n = len(d2_values)
    emp_mean = sum(d2_values) / n
    emp_var = sum((x - emp_mean)**2 for x in d2_values) / (n - 1)
    emp_std = math.sqrt(emp_var)
    
    theo_mean, theo_var, theo_std = calculate_chi2_stats(dof)
    
    # 5. Compute Robust Statistics (Median/MAD)
    d2_values.sort()
    mid_idx = n // 2
    median = (d2_values[mid_idx] + d2_values[~mid_idx]) / 2
    
    abs_devs = [abs(x - median) for x in d2_values]
    abs_devs.sort()
    mad = (abs_devs[mid_idx] + abs_devs[~mid_idx]) / 2
    
    # 6. Tail Statistics
    p95_idx = int(0.95 * n)
    p95 = d2_values[p95_idx] if p95_idx < n else d2_values[-1]
    crit_95 = 19.675
    
    # 7. Z-Score Comparison for Max Outlier
    max_val = d2_values[-1]
    z_std = (max_val - emp_mean) / emp_std
    z_mad = (max_val - median) / (mad if mad > 0 else 1.0)
    
    # Print Report
    print("\n--- STATISTICS ---")
    print(f"  {'Metric':<15} {'Empirical':<10} {'Theoretical':<20}")
    print(f"  {'-'*50}")
    print(f"  {'Mean':<15} {emp_mean:<10.2f} {theo_mean:<20.2f}")
    print(f"  {'Std Dev':<15} {emp_std:<10.2f} {theo_std:<20.2f}")
    print(f"  {'Median':<15} {median:<10.2f} {'--':<20}")
    print(f"  {'MAD':<15} {mad:<10.2f} {'--':<20}")
    
    print("\n--- OUTLIER SCALING (Max Value) ---")
    print(f"  Value: {max_val:.2f}")
    print(f"  Z_std: {z_std:.2f} (Penalty strength)")
    print(f"  Z_mad: {z_mad:.2f} (Penalty strength)")
    
    print("\n--- HISTOGRAM ---")
    print(ascii_histogram(d2_values))
    
    # Export JSON
    analysis = {
        "n": n,
        "dof": dof,
        "mean": {"empirical": emp_mean, "theoretical": theo_mean},
        "std": {"empirical": emp_std, "theoretical": theo_std},
        "robust": {
            "median": median,
            "mad": mad,
            "z_std_max": z_std,
            "z_mad_max": z_mad
        },
        "p95": {"empirical": p95, "theoretical": crit_95},
        "extremes": {"max": max(d2_values), "min": min(d2_values)},
        "verdict": "PASS" if abs(emp_mean - theo_mean) < 2.0 and abs(emp_std - theo_std) < 2.0 else "FAIL"
    }
    
    Path("audit_result.json").write_text(json.dumps(analysis, indent=2))
    print(json.dumps(analysis, indent=2))



if __name__ == "__main__":
    main()
