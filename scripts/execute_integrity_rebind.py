"""
ASSIGNMENT 015: AUTHORIZED INTEGRITY REBIND EXECUTOR

Purpose:
- Rebind source integrity baseline ONLY after explicit human authorization.
- Transfer responsibility, not repair code.
- STRICTLY READ-ONLY except integrity baseline files.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass

# Fix path
sys.path.append(".")

# === HARD GUARDS ===
from src.core.config import DEFAULT_LEARNING_MODE
from src.learning.learning_mode import LearningMode
from src.ops.integrity import compute_merkle_root

if DEFAULT_LEARNING_MODE != LearningMode.EVALUATE:
    print("CRITICAL: Integrity rebind requires EVALUATE mode.")
    sys.exit(3)

# === CONSTANTS ===
BASELINE_DIR = Path("data/integrity_baselines").resolve()
LOCK_FILE = BASELINE_DIR / "src.lock"
PREV_LOCK_FILE = BASELINE_DIR / "src.lock.prev"
SRC_DIR = Path("src").resolve()
AUTH_WINDOW_HOURS = 24

# === DATA MODEL ===
@dataclass(frozen=True)
class IntegrityRebindRecord:
    previous_hash: str
    new_hash: str
    file_count: int
    total_bytes: int
    authorized_by: str
    authorization_reason: str
    authorization_timestamp: str
    execution_timestamp: str
    mode: str


def load_authorization(path: Path) -> dict:
    if not path.exists():
        raise RuntimeError("Authorization file not found.")

    data = json.loads(path.read_text(encoding="utf-8"))

    required = {"authorized_by", "authorization_reason", "scope", "issued_at"}
    if not required.issubset(data.keys()):
        raise RuntimeError("Authorization file missing required fields.")

    if data["scope"] != "INTEGRITY_REBIND_ONLY":
        raise RuntimeError("Authorization scope invalid.")

    issued_at = datetime.fromisoformat(data["issued_at"])
    if datetime.now() - issued_at > timedelta(hours=AUTH_WINDOW_HOURS):
        raise RuntimeError("Authorization expired.")

    return data


def snapshot_source():
    file_count = 0
    total_bytes = 0

    for p in SRC_DIR.rglob("*"):
        if p.is_file():
            file_count += 1
            total_bytes += p.stat().st_size

    return file_count, total_bytes


def execute_rebind(auth_path: Path):
    print(">>> AUTHORIZED INTEGRITY REBIND <<<")

    auth = load_authorization(auth_path)

    if not LOCK_FILE.exists():
        raise RuntimeError("Existing baseline missing. Cannot rebind.")

    previous_lock = json.loads(LOCK_FILE.read_text())
    previous_hash = previous_lock["merkle_root"]

    new_hash = compute_merkle_root(SRC_DIR)
    file_count, total_bytes = snapshot_source()

    # Preserve previous baseline
    PREV_LOCK_FILE.write_text(LOCK_FILE.read_text(), encoding="utf-8")

    # Write new baseline
    new_lock = {
        "target": str(SRC_DIR),
        "merkle_root": new_hash,
        "rebuilt_at": datetime.now().isoformat()
    }
    LOCK_FILE.write_text(json.dumps(new_lock, indent=2), encoding="utf-8")

    record = IntegrityRebindRecord(
        previous_hash=previous_hash,
        new_hash=new_hash,
        file_count=file_count,
        total_bytes=total_bytes,
        authorized_by=auth["authorized_by"],
        authorization_reason=auth["authorization_reason"],
        authorization_timestamp=auth["issued_at"],
        execution_timestamp=datetime.now().isoformat(),
        mode=DEFAULT_LEARNING_MODE.value
    )

    # Immutable audit append
    audit_file = BASELINE_DIR / "rebind_audit.log"
    audit_file.open("a", encoding="utf-8").write(json.dumps(record.__dict__) + "\n")

    # Human-facing output
    print("")
    print(f"INTEGRITY REBIND EXECUTED — {record.execution_timestamp}")
    print("")
    print("Previous Baseline:")
    print(f"  - Hash: {record.previous_hash[:12]}...")
    print("New Baseline:")
    print(f"  - Hash: {record.new_hash[:12]}...")
    print("")
    print("Authorization:")
    print(f"  - Provided By: {record.authorized_by}")
    print(f"  - Scope: INTEGRITY_REBIND_ONLY")
    print(f"  - Reason: \"{record.authorization_reason}\"")
    print("")
    print("System State:")
    print(f"  - Mode: {record.mode}")
    print("  - Learning: DISABLED")
    print("  - Actuation: NONE")
    print("")
    print("Statement:")
    print("  Responsibility for current source state has been accepted by the human operator.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/execute_integrity_rebind.py <authorization.json>")
        sys.exit(1)

    execute_rebind(Path(sys.argv[1]))
