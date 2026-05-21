"""
llm_bridge.py — Ollama Integration for Error Explanation Only.

CRITICAL RULE: LLM never decides to interrupt.
Only deterministic logic (interrupt_policy) controls when Jarvis speaks.
LLM only EXPLAINS — it never DECIDES.

Uses Ollama with small models (Phi-3.5, Llama 3.2, Mistral).
Falls back gracefully if Ollama isn't installed.
"""
import json
from typing import Dict, Optional


class LLMBridge:
    """
    Connects to Ollama for error explanation.
    
    The LLM receives STRUCTURED input only:
      - Error class
      - Traceback
      - Code snippet
      - Session context
    
    It NEVER receives raw OCR or decides to interrupt.
    """
    
    DEFAULT_MODEL = "phi3.5"
    FALLBACK_MODELS = ["phi3", "llama3.2", "mistral"]
    
    SYSTEM_PROMPT = """You are Jarvis, a developer's error explanation assistant.
You explain Python errors clearly in 2-3 sentences.

RULES:
1. Be specific to THIS error, not generic advice.
2. Reference the actual traceback and code shown.
3. If unsure, say "I'm not sure" — NEVER hallucinate.
4. Suggest ONE concrete fix.
5. Max 3 sentences total.
"""
    
    def __init__(self, model: str = None):
        self._model = model or self.DEFAULT_MODEL
        self._available = None  # Lazy check
    
    def is_available(self) -> bool:
        """Check if Ollama is running and model is available."""
        if self._available is not None:
            return self._available
        
        try:
            import urllib.request
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read())
                models = [m["name"].split(":")[0] for m in data.get("models", [])]
                
                # Check for our model or fallbacks
                for m in [self._model] + self.FALLBACK_MODELS:
                    if m in models:
                        self._model = m
                        self._available = True
                        return True
                
                self._available = False
                return False
        except Exception:
            self._available = False
            return False
    
    def explain_error(self, error_class: str, traceback: str,
                      code_snippet: str = "", context: str = "") -> Dict:
        """
        Ask LLM to explain an error. Structured input only.
        
        Returns: {explanation, fix, model, success}
        """
        if not self.is_available():
            return {
                "explanation": "",
                "fix": "",
                "model": None,
                "success": False,
                "fallback_reason": "Ollama not available"
            }
        
        # Build structured prompt
        prompt = f"""Error class: {error_class}

Traceback:
{traceback[:1500]}

"""
        if code_snippet:
            prompt += f"""Relevant code:
{code_snippet[:800]}

"""
        if context:
            prompt += f"""Context: {context}

"""
        prompt += "Explain this error and suggest a fix:"
        
        try:
            import urllib.request
            body = json.dumps({
                "model": self._model,
                "system": self.SYSTEM_PROMPT,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,  # Low temp = focused answers
                    "num_predict": 200,  # Short responses only
                }
            }).encode()
            
            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=body,
                headers={"Content-Type": "application/json"}
            )
            
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                response_text = result.get("response", "")
                
                return {
                    "explanation": response_text.strip(),
                    "fix": "",  # Could parse "Fix:" from response
                    "model": self._model,
                    "success": True,
                }
        except Exception as e:
            return {
                "explanation": "",
                "fix": "",
                "model": self._model,
                "success": False,
                "fallback_reason": str(e)
            }
    
    def get_status(self) -> Dict:
        """Check LLM availability and model info."""
        available = self.is_available()
        return {
            "available": available,
            "model": self._model if available else None,
            "endpoint": "http://localhost:11434",
        }
