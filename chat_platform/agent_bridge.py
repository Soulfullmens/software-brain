"""
agent_bridge.py — Bridge between NOMAD SecureChat and the ReACT Agent

Connects the chat platform's WebSocket message handler to the real
ReACT reasoning loop. When a user sends a message to the NOMAD Agent
room, this module processes it through the full Think→Act→Observe→Reflect
pipeline with real tools: browser control, screen control, web search, etc.
"""
import asyncio
import sys
import os
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.agent.intelligence.react_loop import ReACTLoop, ToolDefinition


def _build_agent() -> ReACTLoop:
    """Build a fresh ReACT agent with all available tools."""
    
    # LLM Priority: 1. Gemini (cloud) → 2. Ollama (local/offline) → 3. Static fallback
    llm_fn = None
    
    # ── Try 1: Gemini API (cloud — needs GEMINI_API_KEY) ──
    try:
        from src.agent.llm_gemini import GeminiModel
        model = GeminiModel()
        # Quick test to see if it actually works
        test = model.generate("respond with OK")
        if test and len(test) > 0:
            llm_fn = lambda prompt: model.generate(prompt)
            print("[Agent] Using Gemini API (cloud)")
    except Exception:
        pass
    
    # ── Try 2: Ollama (local — FREE, works offline, no API key needed) ──
    if llm_fn is None:
        try:
            import urllib.request
            import json as _json
            
            # Check if Ollama is running
            urllib.request.urlopen('http://localhost:11434/api/tags', timeout=2)
            
            def ollama_generate(prompt: str) -> str:
                """Call Ollama's local API — works 100% offline."""
                # Try these models in order of intelligence
                models_to_try = ['gemma2', 'gemma2:9b', 'llama3.1:8b', 'qwen2.5:14b', 'mistral:7b', 'llama3:8b', 'qwen2.5:7b', 'phi3:mini']
                
                # First, find which model is actually available
                try:
                    tags_resp = urllib.request.urlopen('http://localhost:11434/api/tags', timeout=5)
                    tags_data = _json.loads(tags_resp.read().decode())
                    available = [m['name'].split(':')[0] + ':' + m['name'].split(':')[-1] if ':' in m['name'] else m['name'] for m in tags_data.get('models', [])]
                    # Also try just the base names
                    available_base = [m['name'].split(':')[0] for m in tags_data.get('models', [])]
                except Exception:
                    available = []
                    available_base = []
                
                # Pick the best available model
                model_name = None
                for m in models_to_try:
                    base = m.split(':')[0]
                    if m in available or base in available_base:
                        model_name = m
                        break
                
                if not model_name:
                    # Just use whatever is first available
                    if available:
                        model_name = available[0]
                    else:
                        return _json.dumps({"thought": "No Ollama models found.", "action_needed": False, "conclusion": "No AI model found. Please run: ollama pull gemma2"})
                
                payload = _json.dumps({
                    "model": model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 800}
                }).encode()
                
                req = urllib.request.Request(
                    'http://localhost:11434/api/generate',
                    data=payload,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                resp = urllib.request.urlopen(req, timeout=60)
                data = _json.loads(resp.read().decode())
                return data.get('response', '')
            
            llm_fn = ollama_generate
            print("[Agent] Using Ollama (local, offline-capable)")
        except Exception:
            pass
    
    # ── Try 3: Static fallback (no AI, just acknowledges) ──
    if llm_fn is None:
        def fallback_llm(prompt: str) -> str:
            import json
            return json.dumps({
                "thought": "No LLM available.",
                "action_needed": False,
                "conclusion": "NOMAD Agent is operational but no AI backend is configured. Run Ollama, type: ollama pull gemma2 — then restart the server. This gives you FREE, offline AI!"
            })
        llm_fn = fallback_llm
        print("[Agent] Using static fallback (no AI backend found)")
    
    loop = ReACTLoop(llm_fn=llm_fn, max_rounds=5)
    
    # ── Tool 1: Browser Control (navigate, screenshot, JS injection, CSS, fullscreen) ──
    try:
        from src.agent.tools.browser_tool import execute_browser
        loop.add_tool(ToolDefinition(
            name="browser_control",
            description="Control the user's Chrome browser. Supports: navigate to URL, take screenshot, inject JavaScript (run_js), inject CSS (inject_css), force video fullscreen (fullscreen_video), click elements, type text, list tabs, remove ads, apply dark mode.",
            parameters={
                "action": "One of: navigate, screenshot, run_js, inject_css, fullscreen_video, click, type_text, get_page_info, list_tabs, switch_tab, remove_ads, dark_mode, scroll",
                "url": "(optional) URL to navigate to",
                "js_code": "(optional) JavaScript code to execute in the page console",
                "css_code": "(optional) CSS code to inject into the page",
                "selector": "(optional) CSS selector to click or type into",
                "text": "(optional) Text to type",
                "tab_index": "(optional) Tab index to switch to",
            },
            execute_fn=execute_browser
        ))
    except ImportError:
        pass
    
    # ── Tool 2: Screen Control (physical mouse/keyboard) ──
    try:
        from src.agent.tools.browser_tool import execute_screen_control
        loop.add_tool(ToolDefinition(
            name="screen_control",
            description="Physical screen control via mouse/keyboard. Use this for: opening DevTools, pressing F11 for fullscreen, taking full-screen screenshots, clicking system UI elements outside the browser.",
            parameters={
                "action": "One of: screenshot, click, type_text, press_key, move_mouse, open_devtools, toggle_fullscreen",
                "x": "(optional) X coordinate for click/move",
                "y": "(optional) Y coordinate for click/move",
                "key": "(optional) Key to press, e.g. 'f11' or 'ctrl+shift+i'",
                "text": "(optional) Text to type",
            },
            execute_fn=execute_screen_control
        ))
    except ImportError:
        pass
    
    # ── Tool 3: Fast Web Extraction ──
    try:
        from src.agent.tools.fast_browser import FastBrowserEngine
        engine = FastBrowserEngine()
        def web_extract(params):
            url = params.get('url', '')
            result = engine.extract(url)
            return f"Title: {result.title}\nText: {result.text[:1000]}\nLinks: {len(result.links)}"
        
        loop.add_tool(ToolDefinition(
            name="web_extract",
            description="Fast web page content extraction. Gets text, links, and metadata from any URL without opening a browser.",
            parameters={"url": "URL to extract content from"},
            execute_fn=web_extract
        ))
    except ImportError:
        pass
    
    # ── Tool 4: Shell Command (sandboxed) ──
    try:
        from src.agent.tools.shell import execute_shell
        loop.add_tool(ToolDefinition(
            name="shell",
            description="Execute a shell command on the user's system. Use for file operations, system info, installing packages, etc.",
            parameters={"command": "Shell command to execute"},
            execute_fn=lambda p: execute_shell(p.get('command', 'echo hello'))
        ))
    except ImportError:
        pass
    
    # ── Tool 5: Knowledge Harvester (autonomous web learning) ──
    try:
        from src.agent.intelligence.knowledge_harvester import execute_knowledge_tool, get_harvester
        # Give the harvester the same LLM for summarization
        get_harvester(llm_fn=llm_fn)
        
        loop.add_tool(ToolDefinition(
            name="knowledge",
            description="""Autonomous knowledge engine. Actions:
  harvest - Send scout agents to learn about topics from the web. Params: topics (list), max_pages (int)
  search  - Search the agent's knowledge base. Params: query (str), limit (int)
  stats   - Get knowledge base statistics (total items, topics, quality scores)
Example: {"action": "harvest", "topics": ["machine learning", "web security"]}
Example: {"action": "search", "query": "neural networks"}""",
            parameters={
                "action": "One of: harvest, search, stats",
                "topics": "(for harvest) List of topics to learn about",
                "query": "(for search) What to search for",
                "max_pages": "(for harvest, optional) Max pages per topic (default: 10)",
                "limit": "(for search, optional) Max results (default: 5)",
            },
            execute_fn=execute_knowledge_tool
        ))
    except ImportError as e:
        print(f"[Agent] Knowledge Harvester not available: {e}")
    
    # ── Tool 6: Crowd Simulator (MiroFish-style swarm intelligence) ──
    try:
        from src.agent.intelligence.crowd_simulator import execute_simulation_tool, get_simulator
        get_simulator(llm_fn=llm_fn)
        
        loop.add_tool(ToolDefinition(
            name="crowd_simulate",
            description="""MiroFish-style Swarm Intelligence Prediction Engine.
Simulate hundreds of diverse AI people to predict real-world outcomes.
Actions:
  predict - Run a full crowd simulation. Params: scenario (str), population (int), rounds (int)
  quick   - Fast prediction with 100 people, 5 rounds. Params: scenario (str)
  types   - List available scenario types (financial, business, workplace, social, political)
Examples:
  {"action": "predict", "scenario": "Tesla stock after US-Iran war", "population": 500}
  {"action": "quick", "scenario": "Will customers leave if I raise prices 20%?"}""",
            parameters={
                "action": "One of: predict, quick, types",
                "scenario": "Natural language description of the situation to predict",
                "population": "(optional) Number of simulated people, default 200",
                "rounds": "(optional) Simulation rounds, default 7",
                "scenario_type": "(optional) Override: financial/business/workplace/social/political",
            },
            execute_fn=execute_simulation_tool
        ))
    except ImportError as e:
        print(f"[Agent] Crowd Simulator not available: {e}")
    
    return loop


def run_agent_sync(prompt: str) -> str:
    """Run the agent synchronously (called from a thread)."""
    try:
        agent = _build_agent()
        result = agent.run(goal=prompt, max_rounds=5)
        
        # Build a nice response
        response_parts = []
        if result.conclusion:
            response_parts.append(result.conclusion)
        if result.tool_calls > 0:
            response_parts.append(f"\n📊 Agent Stats: {result.total_rounds} rounds, {result.tool_calls} tool calls, {result.total_time_ms:.0f}ms")
        if result.stop_reason:
            response_parts.append(f"🏁 Stop reason: {result.stop_reason}")
        
        return "\n".join(response_parts) if response_parts else "Agent completed but produced no output."
        
    except Exception as e:
        tb = traceback.format_exc()
        return f"⚠️ Agent error: {str(e)}\n\nDebug trace:\n{tb[:500]}"


async def ask_agent(prompt: str) -> str:
    """Async wrapper — runs the blocking agent in a thread pool."""
    return await asyncio.to_thread(run_agent_sync, prompt)
