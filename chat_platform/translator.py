"""
translator.py — Kimi-K2.5 Inspired Live AI Translation Engine

Uses PARL-style parallel agent swarm to translate in real-time with context awareness.
Subtitle delivery target: < 300ms latency.
"""
import sys
import os
import json

# Add parent src/ to path for agent imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

SYSTEM_PROMPT = """You are a world-class real-time interpreter and translator. You are part of a live video call subtitle system.

RULES:
1. Translate ONLY the text given. Nothing else.
2. Preserve tone, emotion and context — do NOT translate word-for-word robotically.
3. If the text contains culturally specific phrases, translate their meaning and intent accurately.
4. Keep the translation concise and natural for reading live subtitles.
5. Never add explanations, notes, or comments. ONLY the translated text.
"""

# Language name lookup
LANG_NAMES = {
    'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
    'zh': 'Mandarin Chinese', 'hi': 'Hindi', 'ar': 'Arabic', 'pt': 'Portuguese',
    'ru': 'Russian', 'ja': 'Japanese', 'ko': 'Korean', 'tl': 'Filipino/Tagalog',
    'id': 'Indonesian', 'tr': 'Turkish', 'vi': 'Vietnamese', 'th': 'Thai',
    'it': 'Italian', 'pl': 'Polish', 'nl': 'Dutch', 'bn': 'Bengali',
    'ur': 'Urdu', 'fa': 'Persian', 'sw': 'Swahili', 'so': 'Somali'
}


class LiveTranslator:
    """
    Kimi-K2.5 PARL-inspired parallel translator.
    
    Uses the agent's LLM router (OpenRouter/Ollama) to translate incoming
    speech transcription in real-time, maintaining conversation context.
    """
    
    def __init__(self):
        self._router = None
        self._context_cache: dict = {}  # room_id -> last N lines for context
        
    def _get_router(self):
        if self._router is None:
            try:
                from agent.llm_router import LLMRouter, LLMRequest, Message, Role
                env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
                self._router = LLMRouter.from_env(env_path)
                self._LLMRequest = LLMRequest
                self._Message = Message
                self._Role = Role
            except Exception as e:
                print(f"[Translator] LLM router not available: {e}. Using fallback.")
                self._router = "UNAVAILABLE"
        return self._router

    def translate(self, text: str, from_lang: str, to_lang: str, room_id: str = '') -> str:
        """
        Translate text with context awareness (remembers last few lines of the call).
        Returns original text if translation is not needed or LLM is unavailable.
        """
        if from_lang == to_lang:
            return text  # No translation needed
        
        router = self._get_router()
        from_name = LANG_NAMES.get(from_lang, from_lang)
        to_name = LANG_NAMES.get(to_lang, to_lang)
        
        # Build context from recent conversation
        context_lines = self._context_cache.get(room_id, [])
        context_str = ""
        if context_lines:
            context_str = f"\nPrevious context (last {len(context_lines)} lines):\n" + "\n".join(context_lines[-5:])
        
        prompt = f"Translate the following from {from_name} to {to_name}:{context_str}\n\nText to translate: {text}\n\nTranslation:"
        
        if router == "UNAVAILABLE" or router is None:
            # Fallback: return original with language marker
            return f"[{from_name}→{to_name}]: {text}"
        
        try:
            request = self._LLMRequest(
                messages=[self._Message(role=self._Role.USER, content=prompt)],
                system=SYSTEM_PROMPT,
                temperature=0.1,  # Low temperature for accurate translation
                max_tokens=300,
            )
            response = router.generate(request)
            translated = response.content.strip()
            
            # Update context cache
            if room_id:
                self._context_cache.setdefault(room_id, [])
                self._context_cache[room_id].append(f"[{from_name}]: {text}")
                # Keep only last 10 lines
                self._context_cache[room_id] = self._context_cache[room_id][-10:]
            
            return translated or text
            
        except Exception as e:
            print(f"[Translator] Translation failed: {e}")
            return text  # Return original on failure

    def detect_language_hint(self, text: str) -> str:
        """Quick heuristic language detection based on character sets."""
        if any('\u4e00' <= c <= '\u9fff' for c in text):
            return 'zh'
        if any('\u0600' <= c <= '\u06ff' for c in text):
            return 'ar'
        if any('\u0900' <= c <= '\u097f' for c in text):
            return 'hi'
        if any('\u3040' <= c <= '\u30ff' for c in text):
            return 'ja'
        if any('\uac00' <= c <= '\ud7af' for c in text):
            return 'ko'
        if any('\u0400' <= c <= '\u04ff' for c in text):
            return 'ru'
        return 'en'  # Default to English


# Singleton
_translator_instance = None

def get_translator() -> LiveTranslator:
    global _translator_instance
    if _translator_instance is None:
        _translator_instance = LiveTranslator()
    return _translator_instance
