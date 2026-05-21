import sys
from pathlib import Path
print(f"Start from {Path.cwd()}")
p = str(Path(__file__).parent)
sys.path.insert(0, p)
print(f"Sys path inserted: {p}")

try:
    import controller.planner
    print(f"Planner file: {controller.planner.__file__}")
    print(f"Has CHUNK_METADATA? {'CHUNK_METADATA' in dir(controller.planner)}")
    from controller.planner import CHUNK_METADATA
    print("Import CHUNK_METADATA successful")
except Exception:
    import traceback
    traceback.print_exc()
