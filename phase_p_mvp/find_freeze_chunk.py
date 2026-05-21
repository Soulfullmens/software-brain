from pathlib import Path
import os

CHUNK_DIR = Path(r"c:\Users\abdul rahaman\OneDrive\Ai software\software-brain\phase_p_mvp\data\repo_chunks")

found = []
for f in CHUNK_DIR.glob("*.txt"):
    content = f.read_text(encoding="utf-8", errors="ignore")
    if "_freeze" in content or "FROZEN" in content:
        # Extract filename from content
        filename = "???"
        for line in content.splitlines():
            if "# FILE:" in line:
                filename = line.split("FILE:")[-1].strip()
                break
        found.append((f.stem, filename))

print(f"Chunks with '_freeze' or 'FROZEN':")
for chunk_id, fname in found:
    print(f"{chunk_id} | {fname.split(os.sep)[-1]}")
