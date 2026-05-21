import json

lines = open(r"c:\Users\abdul rahaman\OneDrive\Ai software\software-brain\phase_p_mvp\data\traces\trace.log").readlines()
print("Inspecting LLM Claims:")
count = 0
for line in lines:
    if "WORKER_RESULT" in line:
        data = json.loads(line.strip())
        if data.get("extraction_method") == "llm":
            count += 1
            print("=" * 40)
            print(f"Chunk: {data['chunk_id']}")
            claims = data.get("claims", [])
            print(f"Claims count: {len(claims)}")
            print(f"Raw response repr: {repr(data.get('raw_response', ''))[:500]}")
            print("=" * 40)
print(f"Total chunks with LLM claims: {count}")
