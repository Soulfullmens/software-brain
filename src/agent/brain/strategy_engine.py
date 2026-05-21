"""
strategy_engine.py

Intelligent Recovery & Strategy Switching.
Phase R.4: When stuck, don't just fail — try a different approach.

Capabilities:
- Alternative site switching (Google → Bing → DuckDuckGo)
- Selector retries with different descriptions
- Backtracking (go back, try different path)
- Timeout-based retries
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import time


@dataclass
class Strategy:
    """An alternative approach to try."""
    name: str
    tool: str
    command: str
    parameters: Dict[str, Any]
    description: str
    priority: int = 0  # Higher = try first


class StrategyEngine:
    """
    When the agent fails, generate alternative strategies.
    """
    
    # Alternative search engines
    SEARCH_ALTERNATIVES = [
        ("Google", "https://www.google.com/search?q="),
        ("Bing", "https://www.bing.com/search?q="),
        ("DuckDuckGo", "https://duckduckgo.com/?q="),
    ]
    
    # Alternative selectors for common elements
    ELEMENT_ALTERNATIVES = {
        "search": ["search box", "search input", "search field", "search bar", "query input"],
        "login": ["login button", "sign in", "log in", "submit", "sign in button"],
        "submit": ["submit button", "submit", "go", "send", "confirm"],
        "next": ["next", "continue", "proceed", "forward", "next page"],
        "email": ["email input", "email field", "email address", "username", "user ID"],
        "password": ["password input", "password field", "pass", "secret"],
    }
    
    def __init__(self):
        self.tried_strategies: List[str] = []
        self.search_engine_index = 0
    
    def get_alternatives(self, failed_tool: str, failed_command: str, 
                         failed_params: Dict, error: str = "") -> List[Strategy]:
        """
        Generate alternative strategies for a failed action.
        
        Returns a list of strategies to try, ordered by priority.
        """
        alternatives = []
        
        # ─── Search failures → Try different engine ───
        if failed_command == "open_url" and "search" in str(failed_params.get("url", "")).lower():
            alternatives.extend(self._search_alternatives(failed_params))
        
        # ─── Element not found → Try different description ───
        if failed_command in ("find_and_click", "find_and_type", "find_element"):
            alternatives.extend(self._element_alternatives(failed_command, failed_params))
        
        # ─── Click failed → Try JavaScript click ───
        if failed_command == "click":
            selector = failed_params.get("selector", "")
            alternatives.append(Strategy(
                name="js_click",
                tool="browser_control",
                command="click",
                parameters={"selector": selector},  # Will be handled by tool
                description=f"Retry click on {selector} with JS fallback",
                priority=3
            ))
        
        # ─── Page load failure → Refresh and retry ───
        if "timeout" in error.lower() or "navigation" in error.lower():
            alternatives.append(Strategy(
                name="refresh_retry",
                tool="browser_control",
                command="refresh",
                parameters={},
                description="Refresh page and try again",
                priority=5
            ))
        
        # ─── Generic fallback: Go back ───
        alternatives.append(Strategy(
            name="backtrack",
            tool="browser_control",
            command="back",
            parameters={},
            description="Go back and try a different approach",
            priority=1
        ))
        
        # Filter out already-tried strategies
        alternatives = [a for a in alternatives if a.name not in self.tried_strategies]
        
        # Sort by priority (highest first)
        alternatives.sort(key=lambda s: s.priority, reverse=True)
        
        return alternatives
    
    def _search_alternatives(self, failed_params: Dict) -> List[Strategy]:
        """Get alternative search engines."""
        url = failed_params.get("url", "")
        # Extract query
        query = ""
        for prefix in ["?q=", "?query=", "?search_query="]:
            if prefix in url:
                query = url.split(prefix, 1)[1].split("&")[0]
                break
        
        if not query:
            return []
        
        strategies = []
        for i, (name, base_url) in enumerate(self.SEARCH_ALTERNATIVES):
            strategy_name = f"search_{name.lower()}"
            if strategy_name not in self.tried_strategies:
                strategies.append(Strategy(
                    name=strategy_name,
                    tool="browser_control",
                    command="open_url",
                    parameters={"url": f"{base_url}{query}"},
                    description=f"Try {name} instead",
                    priority=5 - i
                ))
        
        return strategies
    
    def _element_alternatives(self, command: str, params: Dict) -> List[Strategy]:
        """Get alternative element descriptions."""
        description = params.get("description", "").lower()
        
        # Find which category matches
        for category, alternatives in self.ELEMENT_ALTERNATIVES.items():
            if category in description or any(alt in description for alt in alternatives):
                strategies = []
                for alt in alternatives:
                    if alt.lower() != description:
                        strategy_name = f"alt_selector_{alt.replace(' ', '_')}"
                        if strategy_name not in self.tried_strategies:
                            new_params = dict(params)
                            new_params["description"] = alt
                            strategies.append(Strategy(
                                name=strategy_name,
                                tool="browser_control",
                                command=command,
                                parameters=new_params,
                                description=f"Try '{alt}' instead of '{description}'",
                                priority=3
                            ))
                return strategies
        
        return []
    
    def record_attempt(self, strategy_name: str):
        """Record that a strategy was attempted."""
        if strategy_name not in self.tried_strategies:
            self.tried_strategies.append(strategy_name)
    
    def reset(self):
        """Reset for a new task."""
        self.tried_strategies.clear()
        self.search_engine_index = 0
