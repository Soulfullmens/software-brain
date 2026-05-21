from workers.worker import process_chunk, CHUNK_DIR
import json

chunk_id = "chunk_011"
question = "Under what conditions does the system transition from EVALUATE to FROZEN?"

print(f"Processing {chunk_id} with llama3.2 (3B)...")
result = process_chunk(chunk_id, question)

print(f"Serialized Result: {json.dumps(result)}")
