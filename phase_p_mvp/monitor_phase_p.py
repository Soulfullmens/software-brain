import json
import datetime
from pathlib import Path

TRACE_PATH = Path(r"c:\Users\abdul rahaman\OneDrive\Ai software\software-brain\phase_p_mvp\data\traces\trace.log")

def monitor():
    if not TRACE_PATH.exists():
        print("Trace log not found.")
        return

    print(f"Reading {TRACE_PATH}...")
    try:
        lines = TRACE_PATH.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        print(f"Error reading log: {e}")
        return

    worker_count = 0
    llm_count = 0
    total_claims = 0
    
    print("-" * 80)
    print(f"{'Timestamp':<20} | {'Type':<15} | {'Chunk':<15} | {'Method':<10} | {'Claims'}")
    print("-" * 80)

    for line in lines:
        try:
            data = json.loads(line)
            ts = data.get("timestamp", "").split("T")[-1][:8]
            dtype = data.get("type", "")
            
            if dtype == "WORKER_RESULT":
                worker_count += 1
                method = data.get("extraction_method", "???")
                chunk = data.get("chunk_id", "???")
                
                # Get filename
                filename = "???"
                try:
                    cpath = TRACE_PATH.parent.parent / "repo_chunks" / f"{chunk}.txt"
                    if cpath.exists():
                        header = cpath.read_text(encoding="utf-8").splitlines()[1]
                        if "# FILE:" in header:
                            filename = Path(header.split("FILE:")[-1].strip()).name
                except:
                    pass

                claims = data.get("claims", [])
                claim_count = len(claims)
                total_claims += claim_count
                
                if method == "llm":
                    llm_count += 1
                
                print(f"TS={ts} | ID={chunk} | File={filename} | Method={method} | Claims={claim_count}")
                if claims:
                    print(f"   Sample: {claims[0].get('statement', '')[:80]}")
            elif dtype == "DELEGATE":
                chunk = data.get("chunk_id", "???")
                print(f"{ts:<20} | {dtype:<15} | {chunk:<15} | {'-':<10} | -")
            
        except:
            pass
            
    print("-" * 80)
    print(f"Total Worker Results: {worker_count}")
    print(f"LLM Methods: {llm_count}")
    print(f"Total Claims: {total_claims}")

if __name__ == "__main__":
    monitor()
