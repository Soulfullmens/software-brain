import requests
import json

url = "http://localhost:11434/api/generate"
payload = {
    "model": "llama3.2",
    "prompt": "Hi",
    "stream": False
}

try:
    print(f"Connecting to {url}...")
    response = requests.post(url, json=payload, timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text[:100]}")
except Exception as e:
    print(f"Error: {e}")
