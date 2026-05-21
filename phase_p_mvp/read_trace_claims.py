import json

lines = open(r"c:\Users\abdul rahaman\OneDrive\Ai software\software-brain\phase_p_mvp\data\traces\trace.log").readlines()
count = 0
for line in lines:
    if "WORKER_RESULT" in line:
        data = json.loads(line.strip())
        if data.get("extraction_method") == "llm":
            count += 1
            print("Chunk:", data["chunk_id"])
            raw = data.get("raw_response", "")[:100].replace("\n", " ")
            print("Raw response snippet:", raw)
            print("Claims count:", len(data.get("claims", [])))
            if data.get("claims"):
                print("First claim:", data["claims"][0])
            print("-" * 40)
print("Total LLM processed chunks:", count)
