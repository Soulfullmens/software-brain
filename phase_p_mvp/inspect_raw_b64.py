import json
import base64

path = r"c:\Users\abdul rahaman\OneDrive\Ai software\software-brain\phase_p_mvp\data\traces\trace.log"
lines = open(path).readlines()

found = False
for line in reversed(lines):
    if "WORKER_RESULT" in line and "llm" in line:
        data = json.loads(line)
        raw = data.get("raw_response", "")
        enc = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
        print(f"Chunk: {data['chunk_id']}")
        print(f"Raw Base64: {enc}")
        print(f"Raw len: {len(raw)}")
        print(f"Claims: {len(data.get('claims', []))}")
        found = True
        break

if not found:
    print("No LLM chunks found.")
