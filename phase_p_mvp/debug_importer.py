import sys
from pathlib import Path
print(f"Start from {Path.cwd()}")
p = str(Path(__file__).parent)
print(f"Inserting path: {p}")
sys.path.insert(0, p)

print(f"Sys path: {sys.path}")

try:
    print("Attempting to import controller.controller...")
    from controller.controller import controller
    print("Controller imported successfully")
except Exception:
    import traceback
    traceback.print_exc()
