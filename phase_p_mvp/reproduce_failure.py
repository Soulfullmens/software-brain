from pathlib import Path
from workers.worker import call_ollama, build_extraction_prompt, parse_llm_response

chunk_path = Path(r"c:\Users\abdul rahaman\OneDrive\Ai software\software-brain\phase_p_mvp\data\repo_chunks\chunk_011.txt")
if not chunk_path.exists():
    print(f"Chunk 011 not found at {chunk_path}")
    exit(1)

content = chunk_path.read_text(encoding="utf-8", errors="ignore")
question = "Under what conditions does the system transition from EVALUATE to FROZEN?"

prompt = build_extraction_prompt(content, question)
print(f"Prompt length: {len(prompt)}")

print("Sending to Ollama...")
response = call_ollama(prompt)
print(f"Response length: {len(response) if response else 0}")
print(f"Response content: {repr(response)}")

if response:
    parsed = parse_llm_response(response)
    print("Parsed claims:", len(parsed.get("claims", [])))
