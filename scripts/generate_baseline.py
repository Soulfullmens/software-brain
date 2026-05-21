import sys
from pathlib import Path
import subprocess

# Fix path
sys.path.append(".")

OUTPUT_DIR = Path("data/stasis_baseline/day_0")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SCRIPTS = {
    "risk_ledger.txt": "scripts/risk_ledger.py",
    "tradeoff_ledger.txt": "scripts/tradeoff_ledger.py",
    "commitment_register.txt": "scripts/commitment_register.py",
    "enforcement_map.txt": "scripts/enforcement_map.py",
    "action_eligibility.txt": "scripts/action_eligibility.py"
}

def generate():
    for filename, script in SCRIPTS.items():
        print(f"Generating {filename}...")
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True,
            env={"PYTHONPATH": "."}
        )
        if result.returncode != 0:
            print(f"Error running {script}: {result.stderr}")
            continue
            
        content = result.stdout if result.stdout is not None else ""
        out_file = OUTPUT_DIR / filename
        out_file.write_text(content, encoding='utf-8')

if __name__ == "__main__":
    generate()
