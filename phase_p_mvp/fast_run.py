"""
fast_run.py — Surgical Phase P Validation
Two-tier: regex for easy files, LLM only for 4 critical causal files.
Target: < 3 minutes total on CPU.
"""
import re
import json
import time
import requests
from pathlib import Path

SRC = Path(__file__).parent.parent / "src"
OLLAMA_URL = "http://localhost:11434/api/generate"

# --- TIER CLASSIFICATION (from static analysis) ---
# These 4 files contain actual _freeze CALLSITES or transition LOGIC.
# Only these get LLM reasoning.
MUST_LLM = {"autonomy.py", "adjustment.py", "recovery.py", "policy_evolution.py"}

# These 4 contain relevant terms but only enums/constants/config.
# Regex extraction is sufficient.
REGEX_ONLY = {"learning_mode.py", "accumulation.py", "config.py", "killproof.py"}

# Everything else: SKIP entirely.

# --- REGEX EXTRACTOR (Tier 1) ---
def extract_regex_claims(filepath: Path) -> list:
    """Fast regex extraction for enum/constant files."""
    text = filepath.read_text(errors="ignore")
    claims = []

    # Extract enum members
    for m in re.finditer(r'^\s+([A-Z][A-Z_]+)\s*=\s*["\']?(\w+)', text, re.MULTILINE):
        claims.append({
            "statement": f"{filepath.stem} defines {m.group(1)} = {m.group(2)}",
            "type": "definition",
            "source": filepath.name,
            "confidence": 0.95
        })

    # Extract class definitions
    for m in re.finditer(r'^class\s+(\w+)', text, re.MULTILINE):
        claims.append({
            "statement": f"{filepath.stem} defines class {m.group(1)}",
            "type": "definition",
            "source": filepath.name,
            "confidence": 0.95
        })

    # Extract freeze/transition references
    for m in re.finditer(r'((?:_freeze|FROZEN|EVALUATE)\w*)', text):
        ctx_start = max(0, m.start() - 80)
        ctx_end = min(len(text), m.end() + 80)
        context = text[ctx_start:ctx_end].strip().replace("\n", " ")
        claims.append({
            "statement": f"Reference to {m.group(1)} in {filepath.name}: ...{context}...",
            "type": "reference",
            "source": filepath.name,
            "confidence": 0.7
        })

    return claims


# --- LLM EXTRACTOR (Tier 2) ---
PROMPT_TEMPLATE = """Analyze this Python code. Extract ONLY claims about:
1. What CONDITIONS cause EVALUATE -> FROZEN transition
2. What CALLS _freeze() and WHY
3. What GUARDS or THRESHOLDS trigger freezing

Return JSON: {{"claims": [{{"statement": "...", "type": "causality|condition|transition", "confidence": 0.0-1.0}}]}}

CODE:
```
%s
```

JSON:"""


def extract_llm_claims(filepath: Path) -> list:
    """LLM extraction for causal reasoning files. Single attempt, strict timeout."""
    text = filepath.read_text(errors="ignore")

    # Truncate to ~1500 chars to keep inference fast
    if len(text) > 1500:
        # Keep the part with _freeze logic
        lines = text.split("\n")
        relevant = []
        for i, line in enumerate(lines):
            if any(t in line for t in ["_freeze", "FROZEN", "EVALUATE", "threshold", "emergency"]):
                start = max(0, i - 5)
                end = min(len(lines), i + 10)
                relevant.extend(lines[start:end])
        text = "\n".join(relevant[:60]) if relevant else text[:1500]

    prompt = PROMPT_TEMPLATE % text

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": "llama3.2",
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1,
                "num_ctx": 2048,
                "num_predict": 256  # Short output = fast inference
            }
        }, timeout=90)

        if resp.status_code == 200:
            raw = resp.json().get("response", "")
            try:
                parsed = json.loads(raw)
                claims = parsed.get("claims", [])
                # Tag source
                for c in claims:
                    c["source"] = filepath.name
                return claims
            except json.JSONDecodeError:
                print(f"  [WARN] Bad JSON from LLM for {filepath.name}")
                return []
        else:
            print(f"  [ERR] Ollama status {resp.status_code} for {filepath.name}")
            return []
    except requests.exceptions.ConnectionError:
        print(f"  [ERR] Ollama not reachable for {filepath.name}")
        return []
    except requests.exceptions.Timeout:
        print(f"  [TIMEOUT] {filepath.name} took >90s, skipping")
        return []
    except Exception as e:
        print(f"  [ERR] {filepath.name}: {e}")
        return []


# --- MAIN ---
def main():
    t0 = time.time()
    all_claims = []
    stats = {"skipped": 0, "regex": 0, "llm": 0, "llm_claims": 0, "regex_claims": 0}

    all_py = sorted(SRC.rglob("*.py"))
    print(f"Total source files: {len(all_py)}")

    # --- TIER 0: SKIP ---
    target_files = {}
    for f in all_py:
        if f.name in MUST_LLM:
            target_files[f.name] = ("llm", f)
        elif f.name in REGEX_ONLY:
            target_files[f.name] = ("regex", f)
        else:
            stats["skipped"] += 1

    print(f"Skipped: {stats['skipped']}")
    print(f"Regex targets: {[n for n, (t, _) in target_files.items() if t == 'regex']}")
    print(f"LLM targets: {[n for n, (t, _) in target_files.items() if t == 'llm']}")
    print()

    # --- TIER 1: REGEX ---
    for name, (tier, path) in target_files.items():
        if tier != "regex":
            continue
        t1 = time.time()
        claims = extract_regex_claims(path)
        dt = time.time() - t1
        stats["regex"] += 1
        stats["regex_claims"] += len(claims)
        all_claims.extend(claims)
        print(f"  [REGEX] {name}: {len(claims)} claims in {dt:.2f}s")

    # --- TIER 2: LLM (sequential, 4 files max) ---
    for name, (tier, path) in target_files.items():
        if tier != "llm":
            continue
        t1 = time.time()
        print(f"  [LLM]  {name}: processing...", end="", flush=True)
        claims = extract_llm_claims(path)
        dt = time.time() - t1

        if not claims:
            # Fallback to regex if LLM fails
            claims = extract_regex_claims(path)
            print(f" FALLBACK -> {len(claims)} regex claims in {dt:.1f}s")
        else:
            print(f" {len(claims)} claims in {dt:.1f}s")

        stats["llm"] += 1
        stats["llm_claims"] += len(claims)
        all_claims.extend(claims)

    # --- RESULTS ---
    total_time = time.time() - t0
    print(f"\n{'='*60}")
    print(f"  FAST RUN COMPLETE")
    print(f"{'='*60}")
    print(f"  Total time: {total_time:.1f}s")
    print(f"  Files skipped: {stats['skipped']}")
    print(f"  Regex files: {stats['regex']} -> {stats['regex_claims']} claims")
    print(f"  LLM files:   {stats['llm']} -> {stats['llm_claims']} claims")
    print(f"  Total claims: {len(all_claims)}")
    print()

    # Print interesting claims
    causal = [c for c in all_claims if c.get("type") in ("causality", "condition", "transition")]
    if causal:
        print(f"  CAUSAL/TRANSITION CLAIMS ({len(causal)}):")
        for c in causal:
            print(f"    [{c.get('confidence', '?')}] {c['statement'][:100]}")
    else:
        print(f"  No causal claims extracted. Showing top claims:")
        for c in all_claims[:10]:
            print(f"    [{c.get('type','?')}] [{c.get('confidence','?')}] {c['statement'][:100]}")

    # Save results
    out = Path(__file__).parent / "fast_run_results.json"
    out.write_text(json.dumps({
        "stats": stats,
        "total_time_seconds": round(total_time, 1),
        "claims": all_claims
    }, indent=2))
    print(f"\n  Results saved to {out.name}")


if __name__ == "__main__":
    main()
