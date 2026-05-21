
import json
import statistics
from pathlib import Path

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

if __name__ == "__main__":
    data = json.loads(Path("calibration_data_high_dim.json").read_text(encoding="utf-8"))
    print_variance_report(data["distributions"])
