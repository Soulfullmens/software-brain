"""
offline_tools.py — Offline Data Pipelines

Agent wrappers for interacting with Nomad offline microservices.
Provides native LLM tool definitions for CyberChef algorithms and Kiwix API queries.
"""
import base64
import hashlib
import binascii
import urllib.request
import json
from contextlib import suppress

class CyberChefLocal:
    """
    Implements core CyberChef recipes locally in Python 
    so the agent can parse garbled inputs offline.
    """
    
    @staticmethod
    def to_base64(data: str) -> str:
        return base64.b64encode(data.encode()).decode()

    @staticmethod
    def from_base64(data: str) -> str:
        try:
            return base64.b64decode(data).decode()
        except:
            return "[Error] Invalid Base64"

    @staticmethod
    def to_hex(data: str) -> str:
        return binascii.hexlify(data.encode()).decode()

    @staticmethod
    def from_hex(data: str) -> str:
        try:
            return binascii.unhexlify(data.replace(" ", "")).decode()
        except:
            return "[Error] Invalid Hex"

    @staticmethod
    def sha256_hash(data: str) -> str:
        return hashlib.sha256(data.encode()).hexdigest()

    @staticmethod
    def magic_decode(data: str) -> str:
        """Attempts to guess the encoding and decode it (Base64 -> Hex -> URL)."""
        decoded = CyberChefLocal.from_base64(data)
        if not decoded.startswith("[Error]"): return decoded
        
        decoded = CyberChefLocal.from_hex(data)
        if not decoded.startswith("[Error]"): return decoded
        
        import urllib.parse
        try:
            url_decoded = urllib.parse.unquote(data)
            if url_decoded != data: return url_decoded
        except Exception:
            pass
        return "[Error] Format unknown."


class KiwixClient:
    """
    Client to query a local Nomad Kiwix container.
    Assuming Kiwix-serve is running on localhost:8080.
    """
    def __init__(self, port: int = 8080):
        self.base_url = f"http://127.0.0.1:{port}"

    def search_wikipedia(self, query: str, limit: int = 5) -> str:
        """Query the local Wikipedia ZIM via Kiwix OPDS API."""
        try:
            # Querying standard kiwix-serve search endpoint
            # Note: actual endpoint depends on zim name, this is a generic mock fallback
            url = f"{self.base_url}/catalog/search?q={urllib.parse.quote(query)}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as response:
                if response.status == 200:
                    data = response.read().decode('utf-8')
                    return f"Found local results for '{query}'.\nContent excerpt: {data[:500]}..."
                return "No offline results found."
        except Exception as e:
            return f"[Error] Kiwix service not reachable offline: {e}. Is the Nomad container running?"
