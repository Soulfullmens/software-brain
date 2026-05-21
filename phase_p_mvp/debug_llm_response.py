import json

lines = open(r"c:\Users\abdul rahaman\OneDrive\Ai software\software-brain\phase_p_mvp\data\traces\trace.log").readlines()
print("Dumping raw LLM responses:")
for line in lines:
    if "WORKER_RESULT" in line:
        data = json.loads(line.strip())
        if data.get("extraction_method") == "llm":
            print("=" * 40)
            print("Chunk:", data["chunk_id"])
            raw = data.get("raw_response", "")
            print(f"RAW LENGTH: {len(raw)}")
            print(raw[:1000])  # Print first 1000 chars
            print("=" * 40)
            break  # Just look at the first one
