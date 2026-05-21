"""
jarvis_cli.py — Command-line entry point for Jarvis V1.

Usage:
  python jarvis_cli.py                    # Interactive REPL
  python jarvis_cli.py --insight          # One-shot insight
  python jarvis_cli.py --authority balanced  # Set authority
  python jarvis_cli.py --voice            # Start with voice
"""
import sys, os, argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from agent.jarvis import JarvisV1
from agent.security.security_kernel import AuthorityLevel


def main():
    parser = argparse.ArgumentParser(
        description="🧠 Jarvis V1 — Situational Intelligence for Computers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python jarvis_cli.py              Start interactive mode
  python jarvis_cli.py --insight    One-shot screen analysis
  python jarvis_cli.py --authority expert  Expert mode (fewer confirmations)
        """
    )
    parser.add_argument("--insight", "-i", action="store_true", 
                       help="One-shot: analyze current screen and exit")
    parser.add_argument("--authority", "-a", default="safe",
                       choices=["locked", "paranoid", "safe", "balanced", "expert"],
                       help="Authority level (default: safe)")
    parser.add_argument("--voice", "-v", action="store_true",
                       help="Enable voice interface")
    parser.add_argument("--hotkey", default="ctrl+shift+j",
                       help="Custom hotkey (default: ctrl+shift+j)")
    
    args = parser.parse_args()
    
    # Map authority string to enum
    authority_map = {
        "locked": AuthorityLevel.LOCKED,
        "paranoid": AuthorityLevel.PARANOID,
        "safe": AuthorityLevel.SAFE,
        "balanced": AuthorityLevel.BALANCED,
        "expert": AuthorityLevel.EXPERT,
    }
    authority = authority_map[args.authority]
    
    # Create Jarvis
    jarvis = JarvisV1(authority=authority)
    jarvis.hotkey = args.hotkey
    
    if args.insight:
        # One-shot mode
        result = jarvis.insight()
        print(result.display())
        return
    
    if args.voice:
        print("  🎤 Voice mode — say 'Hey Jarvis' to trigger insight")
        try:
            from agent.tools.voice_interface import VoiceInterface
            voice = VoiceInterface()
            caps = voice.run("check_capabilities")
            if not caps.get("speech_recognition"):
                print("  ⚠️ SpeechRecognition not installed. Run: pip install SpeechRecognition pyaudio")
                print("  Falling back to keyboard mode.\n")
            else:
                print(f"  ✅ Voice ready. Microphones: {caps.get('microphone_count', 0)}")
        except Exception as e:
            print(f"  ⚠️ Voice init failed: {e}. Using keyboard mode.")
    
    # Interactive REPL
    jarvis.repl()


if __name__ == "__main__":
    main()
