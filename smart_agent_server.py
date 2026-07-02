"""
JarvisBrain v5 — Autonomous AI Server

The agent that THINKS, PLANS, and ACTS on its own.
No hardcoded commands. Natural language only.

Run:  python smart_agent_server.py
Open: http://localhost:8000
"""

import json
import os
import sys
import time
import asyncio
import collections
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, Depends
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.security import APIKeyHeader
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("Run: pip install fastapi uvicorn python-multipart")
    sys.exit(1)

from typing import List, Optional, Dict

# ── CORS: tighten in production via ALLOWED_ORIGINS env var ──────────────────
_allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
app = FastAPI(
    title="Software Brain API",
    description="Autonomous AI Agent Platform",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── API KEY AUTH ──────────────────────────────────────────────────────────────
# Set DEMO_API_KEY env var to require a key on all non-health endpoints.
# Leave unset (or empty) to run without auth (local dev only).
_API_KEY = os.environ.get("DEMO_API_KEY", "")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def require_api_key(key: str = Depends(_api_key_header)):
    if _API_KEY and key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")

# ── RATE LIMITER ──────────────────────────────────────────────────────────────
# Simple in-process sliding-window rate limit: N requests per IP per minute.
_RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MIN", "20"))
_rate_buckets: Dict[str, collections.deque] = {}

async def rate_limit(request: Request):
    if _RATE_LIMIT <= 0:
        return  # disabled
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    bucket = _rate_buckets.setdefault(ip, collections.deque())
    # Drop timestamps older than 60 seconds
    while bucket and bucket[0] < now - 60:
        bucket.popleft()
    if len(bucket) >= _RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {_RATE_LIMIT} requests/minute per IP",
        )
    bucket.append(now)

# Combined dependency for protected endpoints
_protected = [Depends(rate_limit), Depends(require_api_key)]

# -- Global Agent --
brain = None
_agent_ref = None
_jarvis_ref = None


def get_brain():
    global brain, _agent_ref, _jarvis_ref
    if brain is None:
        from src.agent.jarvis_brain import JarvisBrain
        brain = JarvisBrain.from_env(data_dir="./agent_data/smart_demo")
        _agent_ref = brain.agent
        _jarvis_ref = brain.jarvis
    return brain


def get_agent():
    get_brain()
    return _agent_ref


def get_jarvis():
    get_brain()
    return _jarvis_ref


# -- Request Models --
class ChatRequest(BaseModel):
    message: str

class TeachRequest(BaseModel):
    name: str
    description: str
    examples: Optional[List[str]] = None
    category: str = "general"

class RememberRequest(BaseModel):
    fact: str
    importance: float = 0.7

class RecallRequest(BaseModel):
    query: str
    limit: int = 10

class CorrectRequest(BaseModel):
    wrong: str
    correct: str

class SkillRequest(BaseModel):
    name: str
    description: str
    steps: List[str]

class RecognizeRequest(BaseModel):
    text: str
    category: Optional[str] = None

class HarvestTopicRequest(BaseModel):
    query: str
    max_articles: int = 3

class HarvestUrlRequest(BaseModel):
    url: str
    topic: str = "web"

class HarvestPackRequest(BaseModel):
    pack_name: str

class HarvestTextRequest(BaseModel):
    text: str
    topic: str = "custom"

class SmartHarvestRequest(BaseModel):
    query: str

class WikiHowRequest(BaseModel):
    query: str

class StackExchangeRequest(BaseModel):
    query: str
    site: str = "stackoverflow"

class ArxivRequest(BaseModel):
    query: str
    max_papers: int = 3

class JarvisCheckRequest(BaseModel):
    command: str
    file_path: str = ""
    code_text: str = ""

class JarvisErrorRequest(BaseModel):
    traceback_text: str
    file_path: str = ""
    command: str = ""
    code_snippet: str = ""

class ToolRequest(BaseModel):
    action: str
    args: Dict = {}

class BrowseRequest(BaseModel):
    url: str
    wait_for: str = "load"

class FillFormRequest(BaseModel):
    url: str
    fields: Dict[str, str]
    submit_selector: str = ""

class OpenAppRequest(BaseModel):
    app_name: str
    args: Optional[List[str]] = None

class RunCommandRequest(BaseModel):
    command: str
    cwd: str = ""
    timeout: int = 30

# Thread pool for blocking LLM calls
_executor = ThreadPoolExecutor(max_workers=2)


# ===== MAIN: AUTONOMOUS CHAT (streaming with step progress) =====

@app.post("/api/smart-chat/stream", dependencies=_protected)
async def smart_chat_stream(req: ChatRequest):
    b = get_brain()
    import queue, threading

    q: queue.Queue = queue.Queue()
    _DONE = object()

    def producer():
        try:
            for chunk in b.smart_chat_stream(req.message):
                q.put(json.dumps(chunk))
        except Exception as e:
            q.put(json.dumps({"type": "error", "content": str(e)}))
        finally:
            q.put(_DONE)

    threading.Thread(target=producer, daemon=True).start()

    async def stream():
        while True:
            # Non-blocking check with async sleep to avoid blocking event loop
            try:
                item = q.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.02)  # 20ms poll
                continue
            if item is _DONE:
                break
            yield f"data: {item}\n\n"

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/cancel")
async def cancel_execution():
    """Cancel the current autonomous execution."""
    b = get_brain()
    b.cancel()
    return {"status": "cancelled"}


# ===== LEARN MODE =====

@app.post("/api/learn/start")
async def learn_start():
    """Start recording user actions across all apps."""
    b = get_brain()
    result = b.start_learn()
    return result


@app.post("/api/learn/stop")
async def learn_stop():
    """Stop recording and return summary."""
    b = get_brain()
    result = b.stop_learn()
    return result


@app.post("/api/learn/analyze")
async def learn_analyze():
    """Analyze recorded actions with LLM to extract intent."""
    b = get_brain()
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_executor, b.analyze_learn)
    return result


class LearnApplyRequest(BaseModel):
    preferences: str = ""


@app.post("/api/learn/apply")
async def learn_apply(req: LearnApplyRequest):
    """Replay the learned workflow."""
    b = get_brain()
    import queue, threading

    q: queue.Queue = queue.Queue()
    _DONE = object()

    def producer():
        try:
            for event in b.replay_learn(req.preferences):
                q.put(json.dumps(event))
        except Exception as e:
            q.put(json.dumps({"type": "error", "content": str(e)}))
        finally:
            q.put(_DONE)

    threading.Thread(target=producer, daemon=True).start()

    async def stream():
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.02)
                continue
            if item is _DONE:
                break
            yield f"data: {item}\n\n"

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ===== HEALTH CHECK =====

@app.get("/api/status")
async def health_check():
    """Standard health check endpoint. Returns 200 when the server is running."""
    return {"status": "ok", "version": "1.0.0"}


# ===== SECURITY STATUS =====

@app.get("/api/security/status")
async def security_status():
    """Get current security status."""
    b = get_brain()
    engine = b._engine
    if hasattr(engine, '_security') and engine._security:
        return {
            "active": True,
            "authority": str(engine._security._authority.name),
            "blocked_count": getattr(engine, '_blocked_count', 0),
        }
    return {"active": False, "authority": "NONE", "blocked_count": 0}


@app.post("/api/smart-chat")
async def smart_chat(req: ChatRequest):
    b = get_brain()
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, b.smart_chat, req.message)


# ===== REGULAR CHAT (backward compat) =====

@app.post("/api/chat")
async def chat(req: ChatRequest):
    a = get_agent()
    response = a.chat(req.message)
    return {
        "content": response.content,
        "model": response.model_used,
        "provider": response.provider,
        "memories_retrieved": response.memories_retrieved,
        "new_facts_learned": response.new_facts_learned,
        "latency_ms": round(response.latency_ms),
    }


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    a = get_agent()

    def gen():
        for chunk in a.chat_stream(req.message):
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ===== DESKTOP CONTROL =====

@app.post("/api/desktop/open-app")
async def desktop_open_app(req: OpenAppRequest):
    b = get_brain()
    r = b.desktop.open_app(req.app_name, req.args)
    return {"success": r.success, "detail": r.detail, "error": r.error}


@app.post("/api/desktop/close-app")
async def desktop_close_app(req: OpenAppRequest):
    b = get_brain()
    r = b.desktop.close_app(req.app_name)
    return {"success": r.success, "detail": r.detail, "error": r.error}


@app.post("/api/desktop/run-command")
async def desktop_run_command(req: RunCommandRequest):
    b = get_brain()
    r = b.desktop.run_command(req.command, cwd=req.cwd or None, timeout=req.timeout)
    return {"success": r.success, "output": r.detail[:5000], "error": r.error}


@app.post("/api/desktop/screenshot")
async def desktop_screenshot():
    b = get_brain()
    r = b.desktop.screenshot()
    return {"success": r.success, "path": r.screenshot_path, "error": r.error}


@app.get("/api/desktop/running-apps")
async def desktop_running_apps():
    b = get_brain()
    apps = b.desktop.list_running_apps()
    return {"apps": apps}


@app.get("/api/desktop/system-info")
async def desktop_system_info():
    b = get_brain()
    return b.desktop.get_system_info()


# ===== BROWSER AUTOMATION =====

@app.post("/api/browser/goto")
async def browser_goto(req: BrowseRequest):
    b = get_brain()
    r = b.browser.goto(req.url, req.wait_for)
    return {"success": r.success, "url": r.url, "title": r.title,
            "error": r.error, "duration_ms": r.duration_ms}


@app.post("/api/browser/click")
async def browser_click(req: ToolRequest):
    b = get_brain()
    r = b.browser.click(req.args.get("selector", ""))
    return {"success": r.success, "error": r.error}


@app.post("/api/browser/fill")
async def browser_fill(req: ToolRequest):
    b = get_brain()
    r = b.browser.fill(req.args.get("selector", ""), req.args.get("value", ""))
    return {"success": r.success, "error": r.error}


@app.post("/api/browser/fill-form")
async def browser_fill_form(req: FillFormRequest):
    b = get_brain()
    r = b.browse_and_fill(req.url, req.fields, req.submit_selector or None)
    return r


@app.post("/api/browser/read-page")
async def browser_read_page():
    b = get_brain()
    r = b.browser.read_page()
    return {"success": r.success, "text": r.data[:10000] if r.data else "",
            "url": r.url, "title": r.title, "error": r.error}


@app.post("/api/browser/search")
async def browser_search(req: ChatRequest):
    b = get_brain()
    r = b.browser.google_search(req.message)
    return {"success": r.success, "url": r.url, "title": r.title, "error": r.error}


@app.post("/api/browser/screenshot")
async def browser_screenshot():
    b = get_brain()
    r = b.browser.screenshot()
    return {"success": r.success, "path": r.screenshot_path, "error": r.error}


@app.get("/api/browser/status")
async def browser_status():
    b = get_brain()
    return b.browser.get_status()


@app.get("/api/browser/links")
async def browser_links():
    b = get_brain()
    r = b.browser.get_links()
    return {"success": r.success, "links": r.data if r.data else [], "error": r.error}


@app.get("/api/browser/inputs")
async def browser_inputs():
    b = get_brain()
    r = b.browser.get_inputs()
    return {"success": r.success, "inputs": r.data if r.data else [], "error": r.error}


# ===== LEARNING =====

@app.post("/api/teach")
async def teach(req: TeachRequest):
    a = get_agent()
    result = a.teach(req.name, req.description, req.examples, req.category)
    return {"result": result}


@app.post("/api/remember")
async def remember(req: RememberRequest):
    a = get_agent()
    result = a.remember(req.fact, req.importance)
    return {"result": result}


@app.post("/api/recall")
async def recall(req: RecallRequest):
    a = get_agent()
    results = a.recall(req.query, req.limit)
    return {"results": results}


@app.post("/api/correct")
async def correct(req: CorrectRequest):
    a = get_agent()
    result = a.correct(req.wrong, req.correct)
    return {"result": result}


@app.post("/api/recognize")
async def recognize(req: RecognizeRequest):
    a = get_agent()
    result = a.recognize(req.text, req.category)
    return result


@app.post("/api/learn-skill")
async def learn_skill(req: SkillRequest):
    a = get_agent()
    result = a.learn_skill(req.name, req.description, req.steps)
    return {"result": result}


# ===== FULL STATUS (detailed) =====

@app.get("/api/full-status")
async def full_status():
    b = get_brain()
    return b.full_status()


@app.get("/api/diagnostics")
async def diagnostics():
    """Self-diagnosis: what's working, what's broken, and how to fix it."""
    b = get_brain()
    bridge = b.agent._brain
    status = bridge.get_status()
    health = status.get("provider_health", {})

    issues = []
    fixes = []

    # Check Ollama
    if not status["ollama_running"]:
        issues.append("Ollama not running — no local LLM available")
        fixes.append("Run: ollama pull phi3:mini && ollama serve")

    # Check cloud providers
    for name in ["openrouter", "gemini", "anthropic"]:
        h = health.get(name, "")
        if "rate-limited" in h:
            issues.append(f"{name}: {h}")
            if name == "openrouter" and "per-day" in h:
                fixes.append("OpenRouter daily limit (50 free/day). Add $0.10 at https://openrouter.ai/settings/credits for 1000/day")
            elif name == "gemini":
                fixes.append("Gemini quota exceeded. Wait or upgrade at https://ai.google.dev/gemini-api/docs/rate-limits")
            elif name == "anthropic" and "credit" in h:
                fixes.append("Anthropic out of credits. Add funds at https://console.anthropic.com/settings/billing")

    # Check if ANY provider works
    any_llm = status["ollama_running"] or any(
        status.get(f"{p}_available") for p in ["openrouter", "gemini", "anthropic"]
    )

    # Performance stats
    stats = status.get("stats", {})
    total = stats.get("total_requests", 0)
    avg_lat = stats.get("avg_latency_ms", 0)

    return {
        "healthy": any_llm,
        "active_provider": status.get("active_model") or next(
            (p for p in ["openrouter", "gemini", "anthropic"] if status.get(f"{p}_available")),
            "memory_only"
        ),
        "issues": issues,
        "fixes": fixes,
        "provider_health": health,
        "stats": {"total_requests": total, "avg_latency_ms": round(avg_lat, 1)},
        "capabilities": {
            "chat": True,
            "memory": True,
            "learning": True,
            "autonomous": any_llm,
            "browser": b.browser._playwright_available if hasattr(b.browser, '_playwright_available') else True,
            "desktop": True,
        }
    }


@app.post("/api/new-session")
async def new_session():
    a = get_agent()
    result = a.new_session()
    return {"result": result}


# ===== HARVEST =====

@app.post("/api/harvest/topic")
async def harvest_topic(req: HarvestTopicRequest):
    a = get_agent()
    results = a.harvest_topic(req.query, req.max_articles)
    return {"results": results}


@app.post("/api/harvest/url")
async def harvest_url(req: HarvestUrlRequest):
    a = get_agent()
    result = a.harvest_url(req.url, req.topic)
    return {"result": result}


@app.post("/api/harvest/pack")
async def harvest_pack(req: HarvestPackRequest):
    a = get_agent()
    results = a.harvest_pack(req.pack_name)
    tc = sum(r["chunks_stored"] for r in results)
    ok = sum(1 for r in results if r["success"])
    return {"results": results, "summary": {"total_articles": len(results), "successful": ok, "total_chunks": tc}}


@app.post("/api/harvest/essentials")
async def harvest_essentials():
    a = get_agent()
    results = a.harvest_essentials()
    tc = sum(r["chunks_stored"] for r in results)
    ok = sum(1 for r in results if r["success"])
    return {"results": results, "summary": {"total_articles": len(results), "successful": ok, "total_chunks": tc}}


@app.post("/api/harvest/text")
async def harvest_text(req: HarvestTextRequest):
    a = get_agent()
    result = a.harvest_custom_text(req.text, req.topic)
    return {"result": result}


@app.get("/api/harvest/stats")
async def harvest_stats():
    a = get_agent()
    return a.harvest_stats()


@app.get("/api/online")
async def check_online():
    a = get_agent()
    bridge = a._brain
    status = bridge.get_status()
    llm_available = (
        status["ollama_running"]
        or status["openrouter_available"]
        or status["gemini_available"]
        or status["anthropic_available"]
    )
    return {
        "online": a.is_online(),
        "llm_available": llm_available,
        "provider_health": status.get("provider_health", {}),
    }


@app.post("/api/harvest/smart")
async def smart_harvest(req: SmartHarvestRequest):
    a = get_agent()
    results = a.smart_harvest(req.query)
    tc = sum(r["chunks_stored"] for r in results)
    return {"results": results, "summary": {"total_sources_searched": len(results), "successful": sum(1 for r in results if r["success"]), "total_chunks": tc}}


@app.post("/api/harvest/wikihow")
async def harvest_wikihow(req: WikiHowRequest):
    a = get_agent()
    result = a.harvest_wikihow(req.query)
    return {"result": result}


@app.post("/api/harvest/stackexchange")
async def harvest_stackexchange(req: StackExchangeRequest):
    a = get_agent()
    result = a.harvest_stackexchange(req.query, req.site)
    return {"result": result}


@app.post("/api/harvest/arxiv")
async def harvest_arxiv(req: ArxivRequest):
    a = get_agent()
    result = a.harvest_arxiv(req.query, req.max_papers)
    return {"result": result}


@app.get("/api/harvest/multi-stats")
async def multi_harvest_stats():
    a = get_agent()
    return a.multi_harvest_stats()


# ===== VISION =====

@app.post("/api/vision/analyze")
async def vision_analyze(file: UploadFile = File(...), question: str = Form(""), auto_harvest: bool = Form(True)):
    a = get_agent()
    contents = await file.read()
    if len(contents) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 100MB)")
    result = a.analyze_image_bytes(contents, file.filename or "upload.jpg", question, auto_harvest)
    return result


@app.get("/api/vision/status")
async def vision_status():
    a = get_agent()
    return a.vision_status()


# ===== JARVIS =====

@app.post("/api/jarvis/check")
async def jarvis_check(req: JarvisCheckRequest):
    j = get_jarvis()
    if not j:
        return {"warnings": [], "error": "Jarvis not available"}
    warnings = j.check_before_run(req.command, req.file_path, req.code_text or None)
    return {"warnings": warnings, "total": len(warnings)}


@app.post("/api/jarvis/error")
async def jarvis_error(req: JarvisErrorRequest):
    j = get_jarvis()
    if not j:
        return {"error": "Jarvis not available"}
    result = j.record_error(req.traceback_text, req.file_path, req.command, req.code_snippet)
    return result


@app.post("/api/jarvis/explain")
async def jarvis_explain(req: JarvisErrorRequest):
    j = get_jarvis()
    if not j:
        return {"error": "Jarvis not available"}
    result = j.explain_error(req.traceback_text, req.code_snippet)
    return result


@app.get("/api/jarvis/status")
async def jarvis_status():
    j = get_jarvis()
    if not j:
        return {"available": False}
    s = j.status()
    s["available"] = True
    return s


@app.get("/api/jarvis/patterns")
async def jarvis_patterns():
    j = get_jarvis()
    if not j:
        return {"patterns": []}
    return {"patterns": j.weekly_patterns()}


# ===== WEB UI =====

@app.get("/", response_class=HTMLResponse)
async def index():
    return CHAT_HTML


CHAT_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>JarvisBrain v5 — Autonomous AI</title>
<style>
:root{--bg:#09090b;--bg2:#0f0f13;--bg3:#18181b;--bg4:#1c1c24;--border:#27272a;--border2:#3f3f46;--text:#e4e4e7;--text2:#a1a1aa;--text3:#71717a;--accent:#7c3aed;--accent2:#6d28d9;--cyan:#06b6d4;--green:#22c55e;--red:#ef4444;--orange:#f97316;--blue:#3b82f6;--gold:#fbbf24}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);height:100vh;display:flex;flex-direction:column;overflow:hidden}

/* Header */
.hdr{background:linear-gradient(135deg,#18181b,#1e1b4b);padding:8px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.hdr h1{font-size:16px;background:linear-gradient(90deg,var(--cyan),var(--accent));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hdr .sub{font-size:9px;color:var(--text3);margin-top:1px}
.hdr-right{display:flex;align-items:center;gap:10px}
.stats{display:flex;gap:8px;font-size:10px;color:var(--text2)}
.stat{display:flex;align-items:center;gap:3px}
.dot{width:6px;height:6px;border-radius:50%}
.shield{font-size:14px;cursor:pointer;transition:all .2s;filter:drop-shadow(0 0 4px rgba(34,197,94,.4))}
.shield:hover{transform:scale(1.2)}
.shield.warn{filter:drop-shadow(0 0 4px rgba(249,115,22,.6))}
.shield.danger{filter:drop-shadow(0 0 4px rgba(239,68,68,.6))}

/* Main layout */
.main{flex:1;display:flex;flex-direction:column;overflow:hidden}

/* Step Progress Bar */
.step-bar{background:var(--bg2);border-bottom:1px solid var(--border);padding:0;overflow:hidden;transition:max-height .3s;max-height:0;flex-shrink:0}
.step-bar.active{max-height:200px;padding:10px 20px}
.step-bar .intent{font-size:12px;color:var(--cyan);margin-bottom:8px;display:flex;align-items:center;gap:6px}
.step-bar .intent .brain{font-size:14px}
.steps{display:flex;gap:4px;overflow-x:auto;padding-bottom:4px}
.step-tab{padding:6px 14px;border-radius:8px;font-size:11px;background:var(--bg3);border:1px solid var(--border);color:var(--text3);white-space:nowrap;transition:all .3s;position:relative}
.step-tab.running{background:#1e1b4b;border-color:var(--accent);color:#c4b5fd;animation:stepPulse 1s infinite}
.step-tab.done{background:#052e16;border-color:#15803d;color:#86efac}
.step-tab.failed{background:#450a0a;border-color:#b91c1c;color:#fca5a5}
.step-tab .num{font-weight:700;margin-right:4px}
.thinking-bar{font-size:11px;color:var(--text3);padding:6px 20px;background:var(--bg2);border-bottom:1px solid var(--border);display:none;align-items:center;gap:6px;flex-shrink:0}
.thinking-bar.active{display:flex}
.thinking-bar .spinner{width:12px;height:12px;border:2px solid var(--border2);border-top-color:var(--accent);border-radius:50%;animation:spin .6s linear infinite}

/* Chat Messages */
.msgs{flex:1;overflow-y:auto;padding:14px 20px;display:flex;flex-direction:column;gap:8px}
.msg{display:flex;gap:8px;max-width:85%;animation:fadeIn .2s ease}
.msg.user{align-self:flex-end;flex-direction:row-reverse}
.msg.bot{align-self:flex-start}
.msg.sys{align-self:center;max-width:90%}
.msg .av{width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;flex-shrink:0}
.msg.user .av{background:var(--accent2);color:#fff}
.msg.bot .av{background:#0e7490;color:#fff}
.msg .bub{padding:8px 14px;border-radius:14px;font-size:13px;line-height:1.5;white-space:pre-wrap;word-break:break-word}
.msg.user .bub{background:#4c1d95;color:#e9d5ff;border-bottom-right-radius:4px}
.msg.bot .bub{background:var(--bg4);color:var(--text);border-bottom-left-radius:4px;border:1px solid var(--border)}
.msg.sys .bub{background:var(--bg3);color:var(--text2);font-size:11px;border:1px solid var(--border);text-align:center;border-radius:20px;padding:5px 16px}
.msg .meta{font-size:9px;color:var(--text3);margin-top:2px}
.msg-actions{display:flex;gap:4px;margin-top:4px;opacity:0;transition:opacity .2s}
.msg:hover .msg-actions{opacity:1}
.msg-btn{background:none;border:1px solid var(--border);border-radius:6px;padding:2px 6px;cursor:pointer;font-size:11px;color:var(--text3);transition:all .15s}
.msg-btn:hover{background:var(--bg3);color:var(--text);border-color:var(--accent)}

/* Answer Card — instant answers with glow */
.answer-card{max-width:85%;animation:answerAppear .3s ease;align-self:flex-start;margin:6px 0}
.answer-card .ac-inner{padding:16px 20px;border-radius:16px;background:linear-gradient(135deg,#0f172a,#1e1b4b);border:1px solid var(--accent);position:relative;overflow:hidden}
.answer-card .ac-inner::before{content:'';position:absolute;top:-50%;left:-50%;width:200%;height:200%;background:radial-gradient(circle,rgba(124,58,237,.15) 0%,transparent 70%);animation:glowPulse 3s ease-in-out infinite}
.answer-card .ac-badge{display:inline-flex;align-items:center;gap:4px;font-size:9px;color:var(--accent);background:rgba(124,58,237,.15);padding:2px 8px;border-radius:10px;margin-bottom:8px;font-weight:600;letter-spacing:.5px;text-transform:uppercase}
.answer-card .ac-text{font-size:14px;line-height:1.7;color:#e2e8f0;position:relative;z-index:1}
.answer-card .ac-source{font-size:9px;color:var(--text3);margin-top:8px;position:relative;z-index:1}

/* Security Banner */
.security-banner{padding:8px 20px;background:linear-gradient(135deg,#450a0a,#1c1c24);border-bottom:1px solid var(--red);font-size:12px;color:#fca5a5;display:none;align-items:center;gap:8px;flex-shrink:0;animation:fadeIn .2s}
.security-banner.active{display:flex}
.security-banner .sb-icon{font-size:16px}
.security-banner .sb-close{margin-left:auto;background:none;border:none;color:#fca5a5;cursor:pointer;font-size:14px}

/* Chrome Action Card */
.chrome-card{display:flex;align-items:center;gap:10px;padding:12px 16px;border-radius:12px;background:linear-gradient(135deg,#172554,#1e1b4b);border:1px solid var(--blue);margin:6px 0;max-width:85%;animation:fadeIn .2s ease;cursor:default}
.chrome-card .chrome-icon{font-size:20px;flex-shrink:0}
.chrome-card .chrome-info{flex:1;min-width:0}
.chrome-card .chrome-title{font-size:13px;color:#93c5fd;font-weight:600}
.chrome-card .chrome-url{font-size:10px;color:var(--text3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px}
.chrome-card .chrome-time{font-size:10px;color:var(--green);flex-shrink:0}

/* Input */
.input-bar{padding:10px 20px 14px;border-top:1px solid var(--border);background:var(--bg2);display:flex;gap:8px;align-items:flex-end;flex-shrink:0}
.input-bar textarea{flex:1;background:var(--bg3);border:1px solid var(--border2);border-radius:14px;padding:10px 14px;color:#fafafa;font-size:13px;resize:none;outline:none;max-height:100px;min-height:42px;font-family:inherit;line-height:1.4}
.input-bar textarea:focus{border-color:var(--accent)}
.input-bar textarea::placeholder{color:var(--text3)}
.send-btn{padding:10px 20px;background:linear-gradient(135deg,var(--accent2),var(--blue));border:none;border-radius:14px;color:#fff;font-size:13px;font-weight:600;cursor:pointer;transition:opacity .15s}
.send-btn:hover{opacity:.9}
.send-btn:disabled{opacity:.3;cursor:wait}
.stop-btn{padding:10px 20px;background:var(--red);border:none;border-radius:14px;color:#fff;font-size:13px;font-weight:700;cursor:pointer;display:none;animation:fadeIn .15s ease;letter-spacing:0.5px}
.stop-btn:hover{opacity:.85}
.stop-btn.active{display:block}

/* Quick suggestions */
.suggestions{display:flex;flex-wrap:wrap;gap:5px;padding:6px 20px;background:var(--bg2);flex-shrink:0}
.sug{padding:4px 12px;background:var(--bg4);border:1px solid var(--border);border-radius:20px;color:var(--text2);font-size:10px;cursor:pointer;transition:all .15s}
.sug:hover{background:var(--bg3);color:var(--text);border-color:var(--accent)}

/* History Panel */
.history-panel{position:fixed;top:0;right:-320px;width:320px;height:100vh;background:var(--bg2);border-left:1px solid var(--border);transition:right .3s;z-index:100;display:flex;flex-direction:column;overflow:hidden}
.history-panel.open{right:0}
.history-hdr{padding:12px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.history-hdr h3{font-size:14px;color:var(--cyan)}
.history-close{background:none;border:none;color:var(--text3);font-size:18px;cursor:pointer}
.history-close:hover{color:var(--text)}
.history-list{flex:1;overflow-y:auto;padding:8px}
.history-item{padding:8px 12px;border-radius:8px;margin-bottom:4px;background:var(--bg3);border:1px solid var(--border);font-size:11px;cursor:pointer;transition:all .2s}
.history-item:hover{background:var(--bg4);border-color:var(--accent)}
.history-item .hi-intent{color:var(--text);font-weight:500;margin-bottom:2px}
.history-item .hi-meta{color:var(--text3);font-size:9px;display:flex;justify-content:space-between}
.history-item .hi-steps{color:var(--green)}
.history-item .hi-time{color:var(--text3)}
.history-btn{position:fixed;top:8px;right:8px;z-index:99;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:4px 10px;font-size:11px;color:var(--text2);cursor:pointer;display:flex;align-items:center;gap:4px;transition:all .2s}
.history-btn:hover{background:var(--bg4);color:var(--text);border-color:var(--accent)}

/* Learn Mode Floating Button */
.learn-btn{position:fixed;bottom:80px;left:20px;z-index:100;background:linear-gradient(135deg,#7c3aed,#3b82f6);border:none;border-radius:50px;padding:10px 20px;color:#fff;font-size:13px;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:6px;box-shadow:0 4px 20px rgba(124,58,237,.4);transition:all .2s}
.learn-btn:hover{transform:translateY(-2px);box-shadow:0 6px 24px rgba(124,58,237,.5)}
.learn-btn.recording{background:linear-gradient(135deg,#dc2626,#991b1b);animation:learnPulse 1.5s infinite;box-shadow:0 4px 20px rgba(220,38,38,.5)}
.learn-btn .learn-icon{font-size:16px}

/* Learn Panel */
.learn-panel{position:fixed;bottom:140px;left:20px;z-index:100;width:320px;background:var(--bg2);border:1px solid var(--border);border-radius:16px;box-shadow:0 8px 32px rgba(0,0,0,.6);display:none;flex-direction:column;overflow:hidden;animation:fadeIn .2s}
.learn-panel.active{display:flex}
.learn-panel-hdr{padding:12px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.learn-panel-hdr h3{font-size:13px;color:var(--gold);display:flex;align-items:center;gap:6px}
.learn-panel-close{background:none;border:none;color:var(--text3);font-size:16px;cursor:pointer}
.learn-panel-body{padding:12px 16px;max-height:300px;overflow-y:auto}
.learn-status{font-size:12px;color:var(--text2);margin-bottom:10px}
.learn-actions{display:flex;gap:8px;padding:10px 16px;border-top:1px solid var(--border)}
.learn-act-btn{flex:1;padding:8px;border-radius:10px;border:1px solid var(--border);background:var(--bg3);color:var(--text);font-size:12px;cursor:pointer;text-align:center;transition:all .15s}
.learn-act-btn:hover{border-color:var(--accent);background:var(--bg4)}
.learn-act-btn.primary{background:var(--accent2);border-color:var(--accent);color:#fff}
.learn-act-btn.primary:hover{background:var(--accent)}
.learn-act-btn.danger{background:#991b1b;border-color:var(--red);color:#fca5a5}
.learn-recording-indicator{display:none;align-items:center;gap:6px;font-size:11px;color:#fca5a5;padding:4px 16px}
.learn-recording-indicator.active{display:flex}
.rec-dot{width:8px;height:8px;background:var(--red);border-radius:50%;animation:recBlink 1s infinite}
.learn-workflow{background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:10px;margin-bottom:8px;font-size:11px;color:var(--text2);line-height:1.5;max-height:150px;overflow-y:auto;white-space:pre-wrap}

/* Confirmation Modal */
.confirm-modal{position:fixed;top:0;left:0;width:100vw;height:100vh;background:rgba(0,0,0,.7);z-index:200;display:none;align-items:center;justify-content:center}
.confirm-modal.active{display:flex}
.confirm-box{background:var(--bg2);border:1px solid var(--border);border-radius:16px;padding:24px;max-width:400px;width:90%;animation:fadeIn .2s}
.confirm-box h3{font-size:14px;color:var(--orange);margin-bottom:12px;display:flex;align-items:center;gap:8px}
.confirm-box p{font-size:12px;color:var(--text2);margin-bottom:16px;line-height:1.5}
.confirm-box .detail{background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:8px 12px;font-size:11px;color:var(--text);margin-bottom:16px;font-family:monospace}
.confirm-btns{display:flex;gap:8px;justify-content:flex-end}
.confirm-btns button{padding:8px 20px;border-radius:10px;border:none;font-size:12px;cursor:pointer;font-weight:600}
.confirm-allow{background:var(--green);color:#fff}
.confirm-deny{background:var(--bg3);color:var(--text2);border:1px solid var(--border) !important}

/* Esc hint */
.esc-hint{position:fixed;bottom:70px;right:20px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:4px 10px;font-size:10px;color:var(--text3);display:none;z-index:50}
.esc-hint.active{display:block}

/* Animations */
@keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes stepPulse{0%,100%{opacity:1}50%{opacity:.6}}
@keyframes answerAppear{from{opacity:0;transform:translateY(8px) scale(.98)}to{opacity:1;transform:translateY(0) scale(1)}}
@keyframes glowPulse{0%,100%{opacity:.5}50%{opacity:1}}
@keyframes learnPulse{0%,100%{box-shadow:0 4px 20px rgba(220,38,38,.3)}50%{box-shadow:0 4px 30px rgba(220,38,38,.7)}}
@keyframes recBlink{0%,100%{opacity:1}50%{opacity:.2}}
</style>
</head>
<body>

<div class="hdr">
  <div>
    <h1>JarvisBrain v5</h1>
    <div class="sub">Controls your laptop — Chrome, apps, everything</div>
  </div>
  <div class="hdr-right">
    <span class="shield" id="shieldIcon" title="Security: Active" onclick="checkSecurity()">&#128737;</span>
    <div class="stats">
      <div class="stat"><div class="dot" id="onlineDot" style="background:var(--green)"></div><span id="onlineText">Ready</span></div>
    </div>
  </div>
</div>

<div class="security-banner" id="secBanner">
  <span class="sb-icon">&#9888;</span>
  <span id="secBannerText">Action blocked for security</span>
  <button class="sb-close" onclick="document.getElementById('secBanner').classList.remove('active')">&times;</button>
</div>

<div class="thinking-bar" id="thinkBar">
  <div class="spinner"></div>
  <span id="thinkText">Thinking...</span>
</div>

<div class="step-bar" id="stepBar">
  <div class="intent"><span class="brain">&#129504;</span> <span id="intentText"></span></div>
  <div class="steps" id="stepsContainer"></div>
</div>

<div class="main">
  <div class="msgs" id="msgs"></div>
</div>

<div class="suggestions" id="suggestions">
  <span class="sug" onclick="q('Search latest AI news')">Latest AI news</span>
  <span class="sug" onclick="q('What is quantum computing?')">What is quantum computing?</span>
  <span class="sug" onclick="q('I want to watch Inception')">Watch a movie</span>
  <span class="sug" onclick="q('Open youtube.com')">Open YouTube</span>
  <span class="sug" onclick="q('Open VS Code')">Open VS Code</span>
  <span class="sug" onclick="q('What can you do?')">What can you do?</span>
</div>

<div class="input-bar">
  <textarea id="inp" rows="1" placeholder="Ask anything or tell me what to do..."
            onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();send()}"
            oninput="this.style.height='auto';this.style.height=Math.min(this.scrollHeight,100)+'px'"></textarea>
  <button class="send-btn" id="sendBtn" onclick="send()">Send</button>
  <button class="stop-btn" id="stopBtn" onclick="cancelExec()">STOP</button>
</div>

<div class="esc-hint" id="escHint">Press <b>Esc</b> to stop</div>

<!-- Learn Mode Floating Button -->
<button class="learn-btn" id="learnBtn" onclick="toggleLearnPanel()">
  <span class="learn-icon">&#127891;</span> Learn
</button>

<!-- Learn Panel -->
<div class="learn-panel" id="learnPanel">
  <div class="learn-panel-hdr">
    <h3>&#127891; Learn Mode</h3>
    <button class="learn-panel-close" onclick="toggleLearnPanel()">&times;</button>
  </div>
  <div class="learn-recording-indicator" id="learnRecIndicator">
    <div class="rec-dot"></div>
    <span>Recording your actions... (<span id="learnActionCount">0</span> actions)</span>
  </div>
  <div class="learn-panel-body" id="learnBody">
    <div class="learn-status" id="learnStatus">
      Click <b>Start Recording</b> to capture your actions across any app on your computer. I'll learn what you're doing and can replay it later.
    </div>
    <div class="learn-workflow" id="learnWorkflow" style="display:none"></div>
  </div>
  <div class="learn-actions" id="learnActions">
    <button class="learn-act-btn primary" id="learnStartBtn" onclick="startLearnRecording()">Start Recording</button>
  </div>
</div>

<!-- History Panel -->
<button class="history-btn" onclick="toggleHistory()">&#128337; History</button>
<div class="history-panel" id="historyPanel">
  <div class="history-hdr">
    <h3>&#128337; Task History</h3>
    <button class="history-close" onclick="toggleHistory()">&times;</button>
  </div>
  <div class="history-list" id="historyList"></div>
</div>

<!-- Confirmation Modal -->
<div class="confirm-modal" id="confirmModal">
  <div class="confirm-box">
    <h3>&#9888; Security Check</h3>
    <p id="confirmText">This action requires your approval.</p>
    <div class="detail" id="confirmDetail"></div>
    <div class="confirm-btns">
      <button class="confirm-deny" onclick="resolveConfirm(false)">Deny</button>
      <button class="confirm-allow" onclick="resolveConfirm(true)">Allow</button>
    </div>
  </div>
</div>

<script>
let busy=false;
let learnState='idle'; // idle, recording, analyzed

function q(text){document.getElementById('inp').value=text;send()}
function esc(t){return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}

// === Messages ===
function addMsg(role,text,meta){
  const d=document.getElementById('msgs');
  const m=document.createElement('div');
  m.className='msg '+role;
  if(role==='sys'){
    m.innerHTML='<div class="bub">'+esc(text)+'</div>';
  } else {
    const av=role==='user'?'&#128100;':'&#129302;';
    const actions=role==='bot'?'<div class="msg-actions"><button class="msg-btn copy-btn" title="Copy text" onclick="copyMsg(this)">&#128203;</button><button class="msg-btn share-btn" title="Share" onclick="shareMsg(this)">&#128279;</button></div>':'';
    m.innerHTML='<div class="av">'+av+'</div><div><div class="bub">'+esc(text)+'</div>'+actions+(meta?'<div class="meta">'+esc(meta)+'</div>':'')+'</div>';
  }
  d.appendChild(m);
  d.scrollTop=d.scrollHeight;
  return m;
}

function copyMsg(btn){
  const bub=btn.closest('.msg').querySelector('.bub');
  const text=bub.textContent||bub.innerText;
  navigator.clipboard.writeText(text).then(()=>{
    btn.innerHTML='&#10003;';btn.style.color='var(--green)';
    setTimeout(()=>{btn.innerHTML='&#128203;';btn.style.color=''},1500);
  });
}

function shareMsg(btn){
  const bub=btn.closest('.msg').querySelector('.bub');
  const text=bub.textContent||bub.innerText;
  if(navigator.share){
    navigator.share({title:'Jarvis AI',text:text}).catch(()=>{});
  } else {
    navigator.clipboard.writeText(text).then(()=>{
      btn.innerHTML='&#10003;';btn.style.color='var(--green)';
      setTimeout(()=>{btn.innerHTML='&#128279;';btn.style.color=''},1500);
    });
  }
}

// === Answer Card with Glow ===
function showAnswerCard(text,source){
  const d=document.getElementById('msgs');
  const card=document.createElement('div');
  card.className='answer-card';
  const badge=source==='local'?'&#9889; Instant Answer':'&#127760; Web Answer';
  const srcText=source==='local'?'Answered locally by AI':'Found via Chrome';
  card.innerHTML='<div class="ac-inner">'+
    '<div class="ac-badge">'+badge+'</div>'+
    '<div class="ac-text">'+esc(text)+'</div>'+
    '<div class="ac-source">'+srcText+'</div>'+
  '</div>';
  d.appendChild(card);
  d.scrollTop=d.scrollHeight;
}

// === Security Banner ===
function showSecurityBanner(msg){
  document.getElementById('secBannerText').textContent=msg;
  document.getElementById('secBanner').classList.add('active');
  setTimeout(()=>{document.getElementById('secBanner').classList.remove('active')},8000);
}

// === Chrome Card ===
function showChromeCard(title,url,timeMs){
  const d=document.getElementById('msgs');
  const card=document.createElement('div');
  card.className='chrome-card';
  card.innerHTML='<div class="chrome-icon">&#127760;</div>'+
    '<div class="chrome-info"><div class="chrome-title">'+esc(title)+'</div>'+
    '<div class="chrome-url">'+esc(url)+'</div></div>'+
    (timeMs?'<div class="chrome-time">'+timeMs+'ms</div>':'');
  d.appendChild(card);
  d.scrollTop=d.scrollHeight;
}

function showThinking(text){
  document.getElementById('thinkText').textContent=text;
  document.getElementById('thinkBar').classList.add('active');
}
function hideThinking(){document.getElementById('thinkBar').classList.remove('active')}

function showStepBar(intent,steps){
  document.getElementById('intentText').textContent=intent;
  const sc=document.getElementById('stepsContainer');
  sc.innerHTML='';
  steps.forEach(s=>{
    const tab=document.createElement('div');
    tab.className='step-tab';
    tab.id='step-'+s.id;
    tab.innerHTML='<span class="num">'+s.id+'</span>'+esc(s.description);
    sc.appendChild(tab);
  });
  document.getElementById('stepBar').classList.add('active');
}
function updateStep(id,status,detail){
  const tab=document.getElementById('step-'+id);
  if(!tab)return;
  tab.className='step-tab '+status;
  if(detail)tab.title=detail;
}
function hideStepBar(){document.getElementById('stepBar').classList.remove('active')}

// === History ===
let taskHistory=JSON.parse(localStorage.getItem('jarvis_history')||'[]');

function toggleHistory(){
  const panel=document.getElementById('historyPanel');
  panel.classList.toggle('open');
  if(panel.classList.contains('open'))renderHistory();
}

function addToHistory(intent,steps,status,durationMs){
  taskHistory.unshift({intent:intent,steps:steps,status:status,duration:durationMs,time:new Date().toLocaleString(),ts:Date.now()});
  if(taskHistory.length>50)taskHistory=taskHistory.slice(0,50);
  try{localStorage.setItem('jarvis_history',JSON.stringify(taskHistory))}catch{}
}

function renderHistory(){
  const list=document.getElementById('historyList');
  list.innerHTML='';
  if(!taskHistory.length){
    list.innerHTML='<div style="padding:20px;text-align:center;color:var(--text3);font-size:12px">No history yet</div>';
    return;
  }
  taskHistory.forEach(h=>{
    const item=document.createElement('div');
    item.className='history-item';
    const icon=h.status==='done'?'&#9989;':h.status==='failed'?'&#10060;':'&#9203;';
    item.innerHTML='<div class="hi-intent">'+icon+' '+esc(h.intent)+'</div>'+
      '<div class="hi-meta"><span class="hi-steps">'+(h.steps||'?')+' steps</span>'+
      '<span class="hi-time">'+esc(h.time)+'</span></div>';
    item.onclick=()=>{document.getElementById('inp').value=h.intent;toggleHistory();send()};
    list.appendChild(item);
  });
}

// === Cancel ===
async function cancelExec(){
  try{await fetch('/api/cancel',{method:'POST'})}catch{}
  busy=false;
  document.getElementById('sendBtn').style.display='';
  document.getElementById('stopBtn').classList.remove('active');
  document.getElementById('escHint').classList.remove('active');
  document.getElementById('sendBtn').disabled=false;
  hideThinking();
  addMsg('sys','Stopped');
}

document.addEventListener('keydown',e=>{if(e.key==='Escape'&&busy)cancelExec()});

// === Confirmation Modal ===
let confirmResolve=null;
function showConfirmModal(text,detail){
  document.getElementById('confirmText').textContent=text;
  document.getElementById('confirmDetail').textContent=detail;
  document.getElementById('confirmModal').classList.add('active');
  return new Promise(resolve=>{confirmResolve=resolve});
}
function resolveConfirm(allowed){
  document.getElementById('confirmModal').classList.remove('active');
  if(confirmResolve)confirmResolve(allowed);
  confirmResolve=null;
}

// === Learn Mode ===
function toggleLearnPanel(){
  document.getElementById('learnPanel').classList.toggle('active');
}

async function startLearnRecording(){
  try{
    const r=await(await fetch('/api/learn/start',{method:'POST'})).json();
    if(r.status==='recording'){
      learnState='recording';
      document.getElementById('learnBtn').classList.add('recording');
      document.getElementById('learnBtn').innerHTML='<span class="learn-icon">&#128308;</span> Recording...';
      document.getElementById('learnRecIndicator').classList.add('active');
      document.getElementById('learnStatus').innerHTML='Recording your actions across all apps...<br>Click, type, scroll — I\'m watching everything.';
      document.getElementById('learnWorkflow').style.display='none';
      document.getElementById('learnActions').innerHTML=
        '<button class="learn-act-btn danger" onclick="stopLearnRecording()">Stop Recording</button>';
      // Poll action count
      learnPollId=setInterval(pollLearnCount,2000);
    } else {
      document.getElementById('learnStatus').textContent='Error: '+(r.error||'Could not start recording');
    }
  }catch(e){
    document.getElementById('learnStatus').textContent='Error: '+e.message;
  }
}

let learnPollId=null;
function pollLearnCount(){
  // We'll update count on stop
}

async function stopLearnRecording(){
  if(learnPollId)clearInterval(learnPollId);
  try{
    const r=await(await fetch('/api/learn/stop',{method:'POST'})).json();
    learnState='stopped';
    document.getElementById('learnBtn').classList.remove('recording');
    document.getElementById('learnBtn').innerHTML='<span class="learn-icon">&#127891;</span> Learn';
    document.getElementById('learnRecIndicator').classList.remove('active');
    document.getElementById('learnActionCount').textContent='0';

    if(r.action_count>0){
      document.getElementById('learnStatus').textContent='Recorded '+r.action_count+' actions. Analyzing...';
      document.getElementById('learnActions').innerHTML='<div style="text-align:center;color:var(--text3);font-size:11px">Analyzing with AI...</div>';
      // Auto-analyze
      const analysis=await(await fetch('/api/learn/analyze',{method:'POST'})).json();
      learnState='analyzed';
      document.getElementById('learnStatus').textContent='I understood your workflow:';
      document.getElementById('learnWorkflow').style.display='block';
      document.getElementById('learnWorkflow').textContent=analysis.intent||analysis.summary||'Could not analyze';
      document.getElementById('learnActions').innerHTML=
        '<button class="learn-act-btn" onclick="discardLearn()">Discard</button>'+
        '<button class="learn-act-btn primary" onclick="applyLearn()">Replay This</button>';
    } else {
      document.getElementById('learnStatus').textContent='No actions recorded. Try again.';
      document.getElementById('learnActions').innerHTML=
        '<button class="learn-act-btn primary" onclick="startLearnRecording()">Start Recording</button>';
    }
  }catch(e){
    document.getElementById('learnStatus').textContent='Error: '+e.message;
  }
}

function discardLearn(){
  learnState='idle';
  document.getElementById('learnStatus').innerHTML='Click <b>Start Recording</b> to capture your actions across any app on your computer. I\'ll learn what you\'re doing and can replay it later.';
  document.getElementById('learnWorkflow').style.display='none';
  document.getElementById('learnActions').innerHTML=
    '<button class="learn-act-btn primary" onclick="startLearnRecording()">Start Recording</button>';
}

async function applyLearn(){
  document.getElementById('learnPanel').classList.remove('active');
  addMsg('sys','Replaying learned workflow...');
  busy=true;
  document.getElementById('sendBtn').style.display='none';
  document.getElementById('stopBtn').classList.add('active');

  try{
    const resp=await fetch('/api/learn/apply',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({preferences:''}),
    });
    const reader=resp.body.getReader();
    const dec=new TextDecoder();
    let buf='';

    while(true){
      const {done,value}=await reader.read();
      if(done)break;
      buf+=dec.decode(value,{stream:true});
      const lines=buf.split('\n');
      buf=lines.pop();
      for(const line of lines){
        if(!line.startsWith('data: '))continue;
        let chunk;
        try{chunk=JSON.parse(line.slice(6))}catch{continue}
        if(chunk.type==='step_start')showThinking('Replaying: '+chunk.description);
        else if(chunk.type==='step_done'){hideThinking();addMsg('sys',chunk.detail||'Step done');}
        else if(chunk.type==='complete'){hideThinking();addMsg('bot','Workflow replayed!','learned');}
      }
    }
  }catch(e){
    addMsg('sys','Replay error: '+e.message);
  }

  busy=false;
  document.getElementById('sendBtn').style.display='';
  document.getElementById('stopBtn').classList.remove('active');
  discardLearn();
}

// === Security ===
async function checkSecurity(){
  try{
    const r=await(await fetch('/api/security/status')).json();
    const shield=document.getElementById('shieldIcon');
    if(r.active){
      shield.title='Security: '+r.authority+(r.blocked_count?' | Blocked: '+r.blocked_count:'');
      shield.className='shield';
    } else {
      shield.title='Security: Basic mode';
      shield.className='shield warn';
    }
  }catch{}
}

// === Send ===
async function send(){
  const inp=document.getElementById('inp');
  const msg=inp.value.trim();
  if(!msg||busy)return;
  inp.value='';inp.style.height='auto';
  addMsg('user',msg);
  busy=true;
  document.getElementById('sendBtn').style.display='none';
  document.getElementById('stopBtn').classList.add('active');
  document.getElementById('escHint').classList.add('active');
  document.getElementById('suggestions').style.display='none';

  let botMsg=null,fullText='',buffer='',isAutonomous=false,currentIntent='';
  const sendStart=Date.now();
  let totalStepMs=0;

  try{
    const resp=await fetch('/api/smart-chat/stream',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:msg}),
    });
    const reader=resp.body.getReader();
    const dec=new TextDecoder();

    while(true){
      const {done,value}=await reader.read();
      if(done)break;
      buffer+=dec.decode(value,{stream:true});
      const lines=buffer.split('\n');
      buffer=lines.pop();

      for(const line of lines){
        if(!line.startsWith('data: '))continue;
        let chunk;
        try{chunk=JSON.parse(line.slice(6))}catch{continue}

        switch(chunk.type){
          case 'thinking':
            showThinking(chunk.content||'Working...');
            isAutonomous=true;
            break;

          case 'plan':
            hideThinking();
            currentIntent=chunk.intent||'';
            showStepBar(chunk.intent,chunk.steps||[]);
            break;

          case 'step_start':
            updateStep(chunk.step_id,'running');
            showThinking('Step '+chunk.step_id+': '+chunk.description);
            break;

          case 'step_done':
            updateStep(chunk.step_id,'done',chunk.detail);
            hideThinking();
            totalStepMs+=(chunk.duration_ms||0);
            const detail=chunk.detail||'';
            // Detect instant answer
            if(detail.startsWith('ANSWER:')){
              const ansText=detail.slice(7).trim();
              const src=detail.includes('[local]')?'local':'web';
              showAnswerCard(ansText.replace(' [local]','').replace(' [web]',''),src);
            }
            // Detect security block
            else if(detail.startsWith('BLOCKED:')){
              showSecurityBanner(detail.slice(8).trim());
            }
            // Chrome card for open_in_chrome actions
            else if(detail.includes('Chrome')){
              const urlMatch=detail.match(/Chrome .+ (.+)/);
              showChromeCard(detail,urlMatch?urlMatch[1]:'',chunk.duration_ms||'');
            }
            else if(detail){
              addMsg('sys',detail);
            }
            break;

          case 'step_failed':
            updateStep(chunk.step_id,'failed',chunk.error);
            hideThinking();
            addMsg('sys','Failed: '+chunk.error);
            break;

          case 'observe':
            showThinking(chunk.content);
            break;

          case 'replan':
            showThinking('Adapting approach...');
            break;

          case 'cancelled':
            hideThinking();hideStepBar();
            addMsg('sys','Stopped');
            break;

          case 'complete':
            hideThinking();
            const stepInfo=chunk.steps_done+'/'+chunk.steps_total+' steps';
            const displayMs=totalStepMs||(Date.now()-sendStart);
            if(!botMsg){
              botMsg=addMsg('bot',chunk.summary||'Done!',stepInfo+' | '+displayMs+'ms');
            }
            addToHistory(currentIntent||'Task',stepInfo,chunk.steps_failed>0?'failed':'done',displayMs);
            setTimeout(()=>{hideStepBar()},5000);
            break;

          case 'search_results':
            hideThinking();
            break;

          case 'suggestions':
            const sugBox=document.getElementById('suggestions');
            sugBox.innerHTML='';
            (chunk.items||[]).forEach(s=>{
              const sp=document.createElement('span');
              sp.className='sug';
              sp.textContent=s;
              sp.onclick=()=>{ document.getElementById('inp').value=s; send(); };
              sugBox.appendChild(sp);
            });
            sugBox.style.display='flex';
            break;

          case 'token':
            hideThinking();
            if(!botMsg)botMsg=addMsg('bot','','');
            fullText+=chunk.content;
            botMsg.querySelector('.bub').textContent=fullText;
            document.getElementById('msgs').scrollTop=document.getElementById('msgs').scrollHeight;
            break;

          case 'done':
            hideThinking();
            const meta=chunk.meta||{};
            if(botMsg&&!isAutonomous){
              let ms='';
              if(meta.model)ms+=meta.model;
              if(meta.latency_ms)ms+=' | '+meta.latency_ms+'ms';
              const me=botMsg.querySelector('.meta');
              if(me)me.textContent=ms;
            }
            break;

          case 'chat_mode':
            hideThinking();
            break;

          case 'error':
            hideThinking();
            if(!botMsg) botMsg=addMsg('bot','⚠ '+chunk.content,'');
            else addMsg('sys','⚠ '+chunk.content);
            break;
        }
      }
    }
    if(!botMsg&&!fullText){
      addMsg('bot','(no response — check if Ollama or an API key is configured)','');
    }
  }catch(e){
    hideThinking();hideStepBar();
    addMsg('bot','Error: '+e.message,'');
  }

  busy=false;
  document.getElementById('sendBtn').style.display='';
  document.getElementById('sendBtn').disabled=false;
  document.getElementById('stopBtn').classList.remove('active');
  document.getElementById('escHint').classList.remove('active');
}

// Minimal status check
async function checkOnline(){
  try{
    const r=await(await fetch('/api/online')).json();
    const dot=document.getElementById('onlineDot');
    const txt=document.getElementById('onlineText');
    if(r.llm_available){dot.style.background='var(--green)';txt.textContent='Ready'}
    else{dot.style.background='var(--orange)';txt.textContent='Limited'}
  }catch{
    document.getElementById('onlineDot').style.background='var(--red)';
    document.getElementById('onlineText').textContent='Offline';
  }
}
checkOnline();setInterval(checkOnline,60000);
checkSecurity();

addMsg('bot','I control your laptop directly. Ask me anything or tell me what to do.\n\n  Ask a question  \u2192  Instant answer with highlight\n  "Search latest AI news"  \u2192  Opens Chrome\n  "Watch Inception"  \u2192  Chrome with streaming options\n  "Open youtube.com"  \u2192  Opens in your browser\n  "Open VS Code"  \u2192  Launches the app\n\n\ud83c\udf93 Learn button: Record your actions, I\'ll learn and replay them.\n\ud83d\udee1 Security: Auto-protects against dangerous actions.\nPress Esc or STOP to cancel anytime.','ready');
</script>
</body>
</html>"""


if __name__ == "__main__":
    print("=" * 50)
    print("  JarvisBrain v5 — Autonomous AI Agent")
    print("  http://localhost:8000")
    print("=" * 50)
    print()
    print("Loading agent...")
    get_brain()

    # Background knowledge bootstrap — downloads essential knowledge so Jarvis
    # can answer questions offline. Runs in background, doesn't block startup.
    def _background_knowledge_bootstrap():
        import time as _time
        _time.sleep(5)  # Let server start first
        try:
            a = get_agent()
            if hasattr(a, "_memory"):
                stats = a._memory.get_stats()
                web_count = stats.entries_by_collection.get("web_knowledge", 0)
                if web_count < 50:
                    print("[Knowledge] Bootstrapping essential knowledge in background...")
                    if hasattr(a, "harvest_essentials"):
                        a.harvest_essentials()
                        print("[Knowledge] Essential knowledge downloaded.")
                    elif hasattr(a, "_harvester") and hasattr(a._harvester, "harvest_essentials"):
                        a._harvester.harvest_essentials()
                        print("[Knowledge] Essential knowledge downloaded.")
                else:
                    print(f"[Knowledge] Already have {web_count} web knowledge entries. Skipping bootstrap.")
        except Exception as e:
            print(f"[Knowledge] Bootstrap skipped: {e}")

    import threading as _threading
    _threading.Thread(target=_background_knowledge_bootstrap, daemon=True).start()

    # Skip pre-warming — keeps laptop cool, Chrome-first approach rarely needs Ollama
    _port = int(os.environ.get("PORT", 8000))
    print(f"Ready! Open http://localhost:{_port}")
    print()
    uvicorn.run(app, host="0.0.0.0", port=_port, log_level="info")
