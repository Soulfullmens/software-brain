import shutil
from pathlib import Path

root = Path.cwd()
for p in root.rglob("__pycache__"):
    try:
        shutil.rmtree(p)
        print(f"Removed {p}")
    except Exception as e:
        print(f"Failed to remove {p}: {e}")
