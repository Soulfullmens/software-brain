from pathlib import Path

path = Path("main_output.txt")
if not path.exists():
    print("main_output.txt not found")
else:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for i, line in enumerate(lines):
        if "chunk_034" in line and "Low claim count" in line:
            print(f"FOUND at line {i}: {line}")
            # Print next 10 lines
            for j in range(1, 15):
                if i+j < len(lines):
                    print(lines[i+j])
            print("-" * 20)
