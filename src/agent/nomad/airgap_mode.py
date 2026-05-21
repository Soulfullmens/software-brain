"""
airgap_mode.py — Zero Internet Execution Enforcer

Ties into NemoClaw to enforce a strict offline survival mode. 
When activated, it actively blocks telemetry, internet-dependent tools, 
and DNS resolution, forcing the agent to rely 100% on local offline resources
managed by the NomadOrchestrator.
"""
import socket
import logging
from typing import List, Callable, Any
import functools

class AirgapEnforcer:
    """Enforces strict offline-only execution for the agent."""
    def __init__(self):
        self.logger = logging.getLogger("AirgapEnforcer")
        self.is_active = False
        self._original_socket = socket.socket

    def enable(self):
        """Activate Airgap Mode. Blocks all external network requests."""
        if self.is_active:
            return
        
        self.is_active = True
        
        # Monkey-patch getaddrinfo to block all external DNS resolution
        self._original_getaddrinfo = socket.getaddrinfo
        
        def offline_getaddrinfo(host, port, *args, **kwargs):
            if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
                return self._original_getaddrinfo(host, port, *args, **kwargs)
            raise ConnectionError(f"[AIRGAP ENFORCER] Blocked external connection to {host}. Agent is in strict offline mode.")
            
        socket.getaddrinfo = offline_getaddrinfo
        self.logger.warning("AIRGAP MODE ENABLED. All external network traffic is blocked. Welcome to the bunker.")

    def disable(self):
        """Deactivate Airgap Mode. Restores internet capability."""
        if not self.is_active:
            return
        self.is_active = False
        if hasattr(self, '_original_getaddrinfo'):
            socket.getaddrinfo = self._original_getaddrinfo
        self.logger.info("Airgap Mode disabled. External traffic permitted.")

    def filter_tools(self, available_tools: List[Any], internet_required_names: List[str]) -> List[Any]:
        """Strips out tools that strictly require the internet if Airgap Mode is active."""
        if not self.is_active:
            return available_tools
            
        filtered = []
        for t in available_tools:
            if hasattr(t, "name") and t.name in internet_required_names:
                self.logger.info(f"Airgap Enforcer removed tool: {t.name}")
            else:
                filtered.append(t)
                
        return filtered

def require_internet(func: Callable):
    """Decorator to instantly fail a tool if the agent is offline."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # We check by trying to resolve an external DNS very quickly
        try:
            socket.gethostbyname("1.1.1.1")
        except Exception:
            raise RuntimeError("This tool requires internet access, but the agent is in Airgap/Offline mode.")
        return func(*args, **kwargs)
    return wrapper
