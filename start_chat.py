"""
start_chat.py — Launch the NOMAD SecureChat Platform
Run: python start_chat.py
Then open: http://localhost:8765 in any browser on the same network.
"""
import os
import sys
import subprocess
import webbrowser
import threading
import time

PORT = 8765

def main():
    print("="*60)
    print(" 🔐 NOMAD SecureChat — Starting Server...    ")
    print("="*60)
    print(f"  URL:         http://localhost:{PORT}")
    print(f"  LAN Access:  http://YOUR_IP:{PORT}  (share this with friends on same WiFi)")
    print(f"  E2E Crypto:  ECDH P-256 + AES-256-GCM")
    print(f"  Offline:     Works with no internet (messages over LAN WiFi)")
    print("="*60)

    # Open browser after 1.5 seconds
    def _open_browser():
        time.sleep(1.5)
        webbrowser.open(f"http://localhost:{PORT}")
    threading.Thread(target=_open_browser, daemon=True).start()

    # Run the server
    server_path = os.path.join(os.path.dirname(__file__), "chat_platform", "server.py")
    env = os.environ.copy()
    env["CHAT_PORT"] = str(PORT)
    try:
        subprocess.run([sys.executable, server_path], env=env)
    except KeyboardInterrupt:
        print("\n🔌 SecureChat server stopped.")

if __name__ == "__main__":
    main()
