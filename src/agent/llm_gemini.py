"""
llm_gemini.py
A direct REST implementation for Google's Gemini API so we don't need external pip libraries.
"""
import json
import urllib.request
import urllib.error

class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        
    def generate(self, user_prompt: str, system_prompt: str = "") -> str:
        """Generate text using Gemini REST API."""
        
        # Build the payload according to Gemini REST specs
        contents = []
        
        if system_prompt:
            # Note: system instruction can be passed in `systemInstruction` field in newer specs, 
            # but appending it to user message is universally safer if API version mismatches.
            contents.append({
                "role": "user",
                "parts": [{"text": "SYSTEM INSTRUCTIONS:\n" + system_prompt + "\n\nUSER PROMPT:\n" + user_prompt}]
            })
        else:
            contents.append({
                "role": "user",
                "parts": [{"text": user_prompt}]
            })
            
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.2, # Keep hallucination low for agents
            }
        }
        
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(self.url, data=data, headers={'Content-Type': 'application/json'})
        
        try:
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                
                # Extract text
                if 'candidates' in result and len(result['candidates']) > 0:
                    parts = result['candidates'][0]['content'].get('parts', [])
                    if parts:
                        return parts[0].get('text', '')
                return ""
        except urllib.error.HTTPError as e:
            error_msg = e.read().decode('utf-8')
            print(f"[Gemini Error]: {error_msg}")
            raise Exception(f"Gemini API Error: {e.code}")
        except Exception as e:
            print(f"[Gemini Error]: {str(e)}")
            raise
