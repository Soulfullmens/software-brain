import json
from pathlib import Path
import datetime

TRACE_DIR = Path(__file__).parent.parent / "data" / "traces"
TRACE_DIR.mkdir(parents=True, exist_ok=True)

def log(event: dict):
    ts = datetime.datetime.utcnow().isoformat()
    record = {"timestamp": ts, **event}
    path = TRACE_DIR / "trace.log"

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

def new_trace():
    path = TRACE_DIR / "trace.log"
    if path.exists():
        path.unlink()
