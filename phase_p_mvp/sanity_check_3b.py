from workers.worker import call_ollama, MODEL
import json

print(f"Testing model: {MODEL}")
response = call_ollama("Say 'hello' and nothing else.")
print(f"Response: {repr(response)}")

if response:
    print(f"Length: {len(response)}")
    print(f"Strip check: {bool(response.strip())}")
else:
    print("Response is None or empty string")
