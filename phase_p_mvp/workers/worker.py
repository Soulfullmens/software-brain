"""
LLM-based Worker - Real intelligence, not pattern matching.

Uses Ollama (local) to extract structured claims from code chunks.
Returns proper epistemic output: claims, uncertainties, confidence, references.
"""

import json
import re
import requests
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Optional

CHUNK_DIR = Path(__file__).parent.parent / "data" / "repo_chunks"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2"  # 3B model - minimum for reliable code reasoning

@dataclass
class Claim:
    statement: str
    evidence: str  # The actual code that supports this
    confidence: float  # 0.0-1.0
    claim_type: str  # "fact", "inference", "uncertainty"

@dataclass
class WorkerResult:
    chunk_id: str
    claims: List[dict]
    uncertainties: List[str]
    references: List[str]  # Files/modules to explore next
    overall_confidence: float
    raw_response: str  # For debugging

def call_ollama(prompt: str) -> Optional[str]:
    """Call Ollama API with timeout."""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": "llama3.2",
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.1,
                    "num_ctx": 2048,
                    "num_predict": 512
                }
            },
            timeout=120  # Increased timeout for slow CPU
        )
        if response.status_code == 200:
            return response.json().get("response", "")
        else: # Keep the original error logging for non-200 status codes
            print(f"Ollama error: {response.status_code}")
            return None
    except requests.exceptions.ConnectionError: # Keep this specific error handling
        print("Ollama not running. Falling back to pattern matching.")
        return None
    except Exception as e:
        print(f"Ollama Error: {e}")
        return None

def build_extraction_prompt(chunk_content: str, question: str) -> str:
    """Build prompt for structured extraction."""
    return f"""Analyze this Python code to answer: {question}

CODE:
```python
{chunk_content[:4000]}
```

Extract claims relevant to the question. Focus on CAUSALITY and CONDITIONS.
- If a function changes system state, explicitly state what changes and under what conditions.
- If a function is called conditionally, describe the condition in plain English.
- If a mode transition occurs, list who triggers it and why.

Respond in JSON:
{{
    "claims": [
        {{"statement": "...", "evidence": "exact code line", "confidence": 0.9, "claim_type": "fact"}}
    ],
    "uncertainties": ["..."],
    "references": ["module_name"],
    "overall_confidence": 0.7
}}

Only include claims ACTUALLY in the code. If nothing relevant, return empty arrays."""

def parse_llm_response(response: str) -> dict:
    """Parse LLM response into structured data."""
    # Try to extract JSON from response
    try:
        # Look for JSON block
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass
    
    # Fallback: empty result
    return {
        "claims": [],
        "uncertainties": [],
        "references": [],
        "overall_confidence": 0.0
    }

def fallback_pattern_extraction(content: str, question: str) -> dict:
    """Fallback to pattern matching if Ollama unavailable."""
    q_lower = question.lower()
    keywords = []
    
    if "learningmode" in q_lower or "learning" in q_lower:
        keywords.extend(["LearningMode", "DEFAULT_LEARNING_MODE", "EVALUATE", "FROZEN", "LEARN"])
    if "evaluate" in q_lower:
        keywords.append("EVALUATE")
    if "frozen" in q_lower:
        keywords.append("FROZEN")
    if "transition" in q_lower:
        keywords.extend(["transition", "->", "change", "switch"])
    
    claims = []
    for line in content.splitlines():
        for kw in keywords:
            if kw in line:
                claims.append({
                    "statement": f"Code contains: {line.strip()[:100]}",
                    "evidence": line.strip()[:200],
                    "confidence": 0.5,
                    "claim_type": "pattern_match"
                })
                break
    
    # Extract references
    references = []
    imports = re.findall(r'from\s+([\w.]+)\s+import', content)
    for imp in imports:
        parts = imp.split('.')
        if len(parts) > 1:
            references.append(parts[-1])
    
    return {
        "claims": claims[:10],
        "uncertainties": ["Pattern matching only - LLM unavailable"],
        "references": list(set(references))[:5],
        "overall_confidence": min(0.3 + len(claims) * 0.05, 0.6)
    }

def process_chunk(chunk_id: str, question: str) -> dict:
    """
    Process a single chunk using LLM extraction.
    Falls back to pattern matching if Ollama unavailable.
    """
    chunk_path = CHUNK_DIR / f"{chunk_id}.txt"

    if not chunk_path.exists():
        raise FileNotFoundError(f"Chunk {chunk_id} not found.")

    content = chunk_path.read_text(encoding="utf-8", errors="ignore")

    # Try LLM extraction with retry for low quality
    # Use smaller context for safety with 3B model
    prompt = build_extraction_prompt(content, question)
    
    for attempt in range(2):
        llm_response = call_ollama(prompt)
        
        # Sanity check for empty response
        if llm_response and llm_response.strip():
            parsed = parse_llm_response(llm_response)
            claims = parsed.get("claims", [])
            
            # If we have decent claims or it's the last attempt, return result
            if len(claims) >= 3 or attempt == 1:
                return {
                    "chunk_id": chunk_id,
                    "claims": claims,
                    "uncertainties": parsed.get("uncertainties", []),
                    "references": parsed.get("references", []),
                    "confidence": parsed.get("overall_confidence", 0.5),
                    "extraction_method": "llm",
                    "raw_response": llm_response[:500]
                }
            else:
                print(f"WARNING: Low claim count ({len(claims)}) for {chunk_id}, retrying...", flush=True)
        else:
            if attempt == 1: # Failed twice
                if llm_response == "":
                    print(f"WARNING: LLM returned empty response for {chunk_id}")
    
    # Fallback to pattern matching if LLM fails after retries
    fallback = fallback_pattern_extraction(content, question)
    return {
        "chunk_id": chunk_id,
        "claims": fallback["claims"],
        "uncertainties": fallback["uncertainties"],
        "references": fallback["references"],
        "confidence": fallback["overall_confidence"],
        "extraction_method": "pattern_fallback",
        "raw_response": ""
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        chunk_id = sys.argv[1]
        question = sys.argv[2]
        result = process_chunk(chunk_id, question)
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python worker.py <chunk_id> <question>")
