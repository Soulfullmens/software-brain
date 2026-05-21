"""
remote_control.py
A minimal implementation of the "Claude Remote Control" feature.
Hosts a local web server so you can control your agent from your phone.
"""
import http.server
import socketserver
import urllib.parse
import json
import socket
import os
import sys

# Ensure src is in the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.agent.autonomous_agent import AutonomousAgent

PORT = 8080

def get_local_ip():
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    return local_ip

class RemoteControlHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            # Serve the simple mobile UI
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 20px; background: #0f172a; color: #f8fafc; }
                    .header { display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #334155; padding-bottom: 10px; margin-bottom: 20px; }
                    .chat { height: 60vh; overflow-y: auto; background: #1e293b; border-radius: 8px; padding: 15px; margin-bottom: 15px; border: 1px solid #334155; }
                    .message { padding: 10px; margin-bottom: 10px; border-radius: 5px; }
                    .user { background: #3b82f6; text-align: right; }
                    .agent { background: #334155; text-align: left; }
                    input { width: calc(100% - 80px); padding: 12px; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: white; }
                    button { width: 70px; padding: 12px; background: #10b981; color: white; border: none; border-radius: 6px; cursor: pointer; }
                    .input-row { display: flex; justify-content: space-between; }
                </style>
            </head>
            <body>
                <div class="header">
                    <h2>🧠 Agent Remote Control</h2>
                    <span style="color: #10b981; font-size: 14px;">● Connected</span>
                </div>
                
                <div class="chat" id="chat">
                    <div class="message agent">Agent online. Waiting for commands from your phone...</div>
                </div>
                
                <div class="input-row">
                    <input type="text" id="cmd" placeholder="Type a command (e.g., 'check news')..." onkeypress="if(event.key === 'Enter') sendCmd()">
                    <button onclick="sendCmd()">Send</button>
                </div>

                <script>
                    function sendCmd() {
                        const input = document.getElementById('cmd');
                        const cmd = input.value;
                        if(!cmd) return;
                        
                        addMessage(cmd, 'user');
                        input.value = '';
                        
                        fetch('/execute', {
                            method: 'POST',
                            body: cmd
                        })
                        .then(res => res.text())
                        .then(data => addMessage(data, 'agent'));
                    }
                    
                    function addMessage(text, type) {
                        const chat = document.getElementById('chat');
                        chat.innerHTML += `<div class="message ${type}">${text}</div>`;
                        chat.scrollTop = chat.scrollHeight;
                    }
                </script>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
            
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/execute':
            content_length = int(self.headers['Content-Length'])
            command = self.rfile.read(content_length).decode('utf-8')
            
            # INTELLIGENT ROUTING
            print(f"\n[REMOTE COMMAND RECEIVED]: {command}")
            response = ""
            command_lower = command.lower()
            
            try:
                if "news" in command_lower or "world" in command_lower or "incident" in command_lower:
                    from src.agent.tools.world_monitor import WorldMonitorTool
                    tool = WorldMonitorTool()
                    incidents = tool.run("get_latest_incidents", region="Global", limit=2)
                    response = "🌍 **World Monitor Intel:**\n"
                    for inc in incidents:
                        response += f"- [{inc['severity']}] {inc['headline']}\n"
                        
                elif "country" in command_lower or "status" in command_lower:
                    from src.agent.tools.world_monitor import WorldMonitorTool
                    tool = WorldMonitorTool()
                    # Extract a basic country code if present (hacky for demo, LLM would normally parse)
                    cc = "US"
                    if " in " in command_lower:
                        cc = command_lower.split(" in ")[1][:2].upper()
                    status = tool.run("query_country_status", country_code=cc)
                    response = f"📊 **{status['country_code']} Instability Score:** {status['instability_index']}/10\nThreats: {', '.join(status['active_threats'])}"
                    
                elif "infrastructure" in command_lower or "cables" in command_lower:
                    from src.agent.tools.world_monitor import WorldMonitorTool
                    tool = WorldMonitorTool()
                    infra = tool.run("check_infrastructure", target_type="Undersea Cables")
                    response = f"🔌 **Infrastructure Alert ({infra['infrastructure_type']}):**\nStatus: {infra['overall_health']}\nDetails: {infra['details']}"
                
                else:
                    response = (
                         "🤖 **Agent Core:** I am online but you have not configured "
                         "a live LLM API key yet (OpenAI/Gemini) in your environment variables. "
                         "Until we add a real 'Brain' to parse open-ended text, I can only respond to "
                         "specific skills like 'check world news', 'US country status', or 'infrastructure'."
                    )
            except Exception as e:
                response = f"⚠️ Agent encountered an error executing the tool: {str(e)}"
                
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(response.encode('utf-8'))

def start_server():
    ip = get_local_ip()
    with socketserver.TCPServer(("", PORT), RemoteControlHandler) as httpd:
        print("\n" + "="*50)
        print("📱 CLAUDE-STYLE REMOTE CONTROL INITIALIZED")
        print("="*50)
        print(f"\nYour phone and laptop must be on the same Wi-Fi.")
        print("Open Safari/Chrome on your phone and type this exact URL:")
        print(f"\n      =>  http://{ip}:{PORT}  <=\n")
        print("Leave this terminal open to keep the server running.")
        print("Press Ctrl+C to stop.")
        print("="*50 + "\n")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down remote control server.")

if __name__ == "__main__":
    start_server()
