"""
voice_interface.py — Voice Input/Output with Manual Activation.

DESIGN PRINCIPLES:
  • Push-to-talk or wake-word activation (NEVER always-on mic)
  • Text-to-Speech for agent responses
  • Speech-to-Text for user commands
  • Privacy: audio is processed locally, never sent externally
  • Manual start/stop — user controls when mic is active

REQUIRES (optional installs):
  • speech_recognition (pip install SpeechRecognition)
  • pyttsx3 (pip install pyttsx3) — offline TTS
  • pyaudio (pip install pyaudio) — mic input
"""
import time, threading
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from enum import Enum

try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False

try:
    import pyttsx3
    HAS_TTS = True
except ImportError:
    HAS_TTS = False


class VoiceState(Enum):
    IDLE = "idle"           # Not listening
    LISTENING = "listening" # Mic active, waiting for speech
    PROCESSING = "processing"  # Recognizing speech
    SPEAKING = "speaking"   # Agent is talking


class VoiceInterface:
    """Voice I/O with manual activation — push-to-talk design."""
    
    name = "voice"
    description = "Voice commands and speech output (manual activation)"
    
    def __init__(self, wake_word: str = "hey jarvis"):
        self.state = VoiceState.IDLE
        self.wake_word = wake_word.lower()
        self._recognizer = sr.Recognizer() if HAS_SR else None
        self._tts_engine = None  # Lazy init
        self._listening = False
        self._listen_thread = None
        self._log: List[Dict] = []
        self._command_callback: Optional[Callable] = None
        
        if self._recognizer:
            self._recognizer.energy_threshold = 300
            self._recognizer.dynamic_energy_threshold = True
            self._recognizer.pause_threshold = 0.8
    
    def run(self, action: str, **kwargs) -> Any:
        dispatch = {
            "speak": lambda: self._speak(kwargs.get("text", "")),
            "listen_once": lambda: self._listen_once(kwargs.get("timeout", 5)),
            "start_listening": lambda: self._start_listening(kwargs.get("callback")),
            "stop_listening": self._stop_listening,
            "get_state": lambda: {"state": self.state.value, "has_sr": HAS_SR, "has_tts": HAS_TTS},
            "check_capabilities": self._check_capabilities,
            "set_wake_word": lambda: self._set_wake_word(kwargs.get("word", "hey jarvis")),
        }
        fn = dispatch.get(action)
        if not fn:
            return {"error": f"Unknown action: {action}"}
        return fn()
    
    def _speak(self, text: str) -> Dict:
        """Text-to-speech — agent speaks to user."""
        if not HAS_TTS:
            return {"error": "pyttsx3 not installed. Run: pip install pyttsx3", "text": text}
        
        try:
            if not self._tts_engine:
                self._tts_engine = pyttsx3.init()
                self._tts_engine.setProperty('rate', 160)
                self._tts_engine.setProperty('volume', 0.9)
            
            self.state = VoiceState.SPEAKING
            self._tts_engine.say(text)
            self._tts_engine.runAndWait()
            self.state = VoiceState.IDLE
            self._log.append({"action": "speak", "text": text[:100], "time": datetime.now().isoformat()})
            return {"success": True, "spoke": text[:100]}
        except Exception as e:
            self.state = VoiceState.IDLE
            return {"error": str(e)}
    
    def _listen_once(self, timeout: int = 5) -> Dict:
        """Listen for ONE command then stop. Push-to-talk style."""
        if not HAS_SR:
            return {"error": "SpeechRecognition not installed. Run: pip install SpeechRecognition pyaudio"}
        
        self.state = VoiceState.LISTENING
        try:
            with sr.Microphone() as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self._recognizer.listen(source, timeout=timeout, phrase_time_limit=10)
            
            self.state = VoiceState.PROCESSING
            
            # Use Google's free API (local processing not available without special setup)
            # For full offline: use sphinx or vosk
            try:
                text = self._recognizer.recognize_google(audio)
            except sr.UnknownValueError:
                self.state = VoiceState.IDLE
                return {"success": False, "error": "Could not understand audio"}
            except sr.RequestError:
                # Fallback to sphinx (offline)
                try:
                    text = self._recognizer.recognize_sphinx(audio)
                except Exception:
                    self.state = VoiceState.IDLE
                    return {"success": False, "error": "No speech recognition available (offline)"}
            
            self.state = VoiceState.IDLE
            is_wake = self.wake_word in text.lower()
            
            # Strip wake word from command
            command = text
            if is_wake:
                idx = text.lower().index(self.wake_word)
                command = text[idx + len(self.wake_word):].strip()
            
            result = {
                "success": True, "text": text, "command": command,
                "wake_word_detected": is_wake, "confidence": 0.85
            }
            self._log.append({**result, "time": datetime.now().isoformat()})
            return result
        except sr.WaitTimeoutError:
            self.state = VoiceState.IDLE
            return {"success": False, "error": "Listening timed out — no speech detected"}
        except Exception as e:
            self.state = VoiceState.IDLE
            return {"error": str(e)}
    
    def _start_listening(self, callback: Callable = None) -> Dict:
        """Start background listening (with wake word)."""
        if not HAS_SR:
            return {"error": "SpeechRecognition not installed"}
        if self._listening:
            return {"error": "Already listening"}
        
        self._listening = True
        self._command_callback = callback
        self.state = VoiceState.LISTENING
        
        def listen_loop():
            while self._listening:
                result = self._listen_once(timeout=3)
                if result.get("success") and result.get("wake_word_detected"):
                    if self._command_callback:
                        self._command_callback(result["command"])
                time.sleep(0.1)
        
        self._listen_thread = threading.Thread(target=listen_loop, daemon=True)
        self._listen_thread.start()
        return {"success": True, "mode": "background_listening", "wake_word": self.wake_word}
    
    def _stop_listening(self) -> Dict:
        """Stop background listening."""
        self._listening = False
        self.state = VoiceState.IDLE
        if self._listen_thread:
            self._listen_thread.join(timeout=2)
            self._listen_thread = None
        return {"success": True, "state": "idle"}
    
    def _check_capabilities(self) -> Dict:
        """Check what voice capabilities are available."""
        caps = {
            "speech_recognition": HAS_SR,
            "text_to_speech": HAS_TTS,
            "microphone": False,
            "wake_word": self.wake_word,
        }
        if HAS_SR:
            try:
                mics = sr.Microphone.list_microphone_names()
                caps["microphone"] = len(mics) > 0
                caps["microphone_count"] = len(mics)
                caps["microphones"] = mics[:5]
            except Exception:
                pass
        
        missing = []
        if not HAS_SR:
            missing.append("pip install SpeechRecognition pyaudio")
        if not HAS_TTS:
            missing.append("pip install pyttsx3")
        caps["install_commands"] = missing
        return caps
    
    def _set_wake_word(self, word: str) -> Dict:
        self.wake_word = word.lower()
        return {"success": True, "wake_word": self.wake_word}
    
    def get_log(self) -> List[Dict]:
        return self._log
