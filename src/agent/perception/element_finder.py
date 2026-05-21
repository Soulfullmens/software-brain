"""
element_finder.py

Semantic Element Discovery Engine.
Phase R.2 Step 3: Maps natural language -> UI elements.

The bridge between human intent and machine action.
"Find the login button" -> selector="#login-btn"
"""
from typing import List, Optional, Tuple
from .dom_scanner import PageModel, UIElement


class ElementFinder:
    """
    Finds UI elements by semantic description.
    Uses text matching, attribute matching, and heuristic scoring.
    
    This is NOT an LLM-based finder (that comes in R.3).
    This is a fast, deterministic heuristic finder.
    """
    
    def find(self, description: str, page_model: PageModel) -> Optional[UIElement]:
        """
        Find the best matching element for a natural language description.
        
        Args:
            description: e.g. "login button", "email input", "search box", "submit"
            page_model: Structured page model from DOMScanner
            
        Returns:
            Best matching UIElement, or None
        """
        candidates = self._score_all(description, page_model)
        if not candidates:
            return None
        # Return highest scoring
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]
    
    def find_all(self, description: str, page_model: PageModel, top_k: int = 5) -> List[Tuple[UIElement, float]]:
        """
        Find all matching elements with scores.
        Returns list of (UIElement, score) tuples.
        """
        candidates = self._score_all(description, page_model)
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:top_k]
    
    def _score_all(self, description: str, model: PageModel) -> List[Tuple[UIElement, float]]:
        """Score all elements against the description."""
        desc_lower = description.lower().strip()
        desc_words = set(desc_lower.split())
        
        all_elements = []
        all_elements.extend(model.buttons)
        all_elements.extend(model.links)
        all_elements.extend(model.inputs)
        all_elements.extend(model.dropdowns)
        
        scored = []
        for el in all_elements:
            score = self._score_element(desc_lower, desc_words, el)
            if score > 0:
                scored.append((el, score))
        
        return scored
    
    def _score_element(self, desc_lower: str, desc_words: set, el: UIElement) -> float:
        """
        Score how well an element matches the description.
        Higher = better match.
        
        Scoring factors:
        1. Text match (strongest signal)
        2. Attribute match (name, aria-label, placeholder)
        3. Type match (button, input, link)
        4. Keyword match (individual words)
        """
        score = 0.0
        
        # Build searchable text from element
        el_text = el.text.lower()
        el_name = el.name.lower()
        el_aria = el.aria_label.lower()
        el_placeholder = el.placeholder.lower()
        el_combined = f"{el_text} {el_name} {el_aria} {el_placeholder}".strip()
        
        if not el_combined:
            return 0.0
        
        # 1. Exact text match (strongest)
        if desc_lower == el_text or desc_lower == el_aria:
            score += 10.0
        
        # 2. Description contained in element text
        if desc_lower in el_combined:
            score += 7.0
        
        # 3. Element text contained in description
        if el_text and el_text in desc_lower:
            score += 5.0
        
        # 4. Type matching
        type_keywords = {
            "button": ["button", "btn", "submit", "click"],
            "link": ["link", "navigate", "go to", "open"],
            "text_input": ["input", "field", "text", "enter", "type"],
            "password_input": ["password", "pass"],
            "email_input": ["email", "mail"],
            "dropdown": ["select", "dropdown", "choose", "pick"],
            "checkbox": ["check", "checkbox", "toggle"],
            "textarea": ["textarea", "message", "comment", "description"],
            "file_upload": ["upload", "file", "attach"]
        }
        
        el_type = el.element_type.lower()
        if el_type in type_keywords:
            for kw in type_keywords[el_type]:
                if kw in desc_words:
                    score += 3.0
                    break
        
        # 5. Individual word matching
        el_words = set(el_combined.split())
        overlap = desc_words & el_words
        if overlap:
            score += len(overlap) * 1.5
        
        # 6. Attribute-specific boosts
        if el_name and any(w in el_name for w in desc_words):
            score += 2.0
        if el_aria and any(w in el_aria for w in desc_words):
            score += 2.5  # aria-label is high quality signal
        if el_placeholder and any(w in el_placeholder for w in desc_words):
            score += 2.0
            
        return score
