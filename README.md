# Software Brain — Autonomous AI Agent Platform

> An AI agent platform with multi-provider LLM routing, persistent memory, multi-agent orchestration, and a security layer. Built from scratch in Python.

[![Tests](https://github.com/Soulfullmens/software-brain/actions/workflows/tests.yml/badge.svg)](https://github.com/Soulfullmens/software-brain/actions/workflows/tests.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)]()

---

## What Is Verified vs What Exists

> **Important:** A file named `security_kernel.py` is not proof of enterprise-grade security. A file named `desktop.py` is not proof of safe desktop autonomy. This section tells you what has actually been tested.

### Verified (37 tests passing)

- **Prompt injection detection** — 14 attack patterns blocked: `ignore previous instructions`, `you are now`, `bypass safety`, credential exfiltration, privilege escalation, system shutdown, disk format, role-playing attacks, and hidden instructions in scraped content. Case-insensitive. Returns clean for normal inputs.
- **Filesystem jail** — Path traversal (`../../../etc/passwd`) blocked. Absolute paths outside workspace blocked. Nested traversal blocked. Snapshot + restore verified: write file, snapshot, agent modifies it, restore confirms original content.
- **Shell blocking** — `rm -rf /`, `mkfs`, `dd if=`, `> /dev/` blocked before execution.
- **LLM router types** — Module imports, `Message/Role/LLMRequest` types work.

### Exists as Code (Not Yet Integration Tested)

- Desktop mouse/keyboard control — built on `pyautogui`, `FAILSAFE=True` is set. **Not tested automatically** — requires a display environment.
- Multi-provider LLM fallback (Claude → Gemini → GPT-4 → Ollama) — code path exists. **Not tested** without live API keys.
- Operator approval gates — code present in `operator_approval.py`. **Not verified** that they are wired into the live agentic loop end-to-end.
- Multi-agent business orchestration — 5 agents (CRM, Support, Real Estate, Scheduling, Marketing) exist. **Not tested** without a live LLM.
- Persistent ChromaDB memory — vector store code exists. **Not tested** in CI (requires chromadb installed).

See [`VERIFIED_STATUS.md`](VERIFIED_STATUS.md) for the full table.

---

## Architecture

```
User Request
    │
    ▼
┌─────────────────────────────────┐
│  smart_agent_server.py          │  ← FastAPI REST API (port 8000)
│  POST /api/smart-chat/stream    │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│  JarvisBrain / ClaudeAgent      │  ← Top-level agent coordinator
└──────┬──────────────────────────┘
       │
       ├──► LLMRouter              →  Claude / Gemini / GPT-4 / Ollama
       │
       ├──► AutonomousEngine       →  Think → Plan → Act → Observe → Reflect
       │
       ├──► SecurityKernel         →  Injection scan → Impact → Approval gate
       │
       ├──► ToolProtocol           →  Desktop / Browser / Shell / Email
       │
       ├──► VectorStore (ChromaDB) →  Episodic / Semantic / Procedural memory
       │
       └──► SwarmOrchestrator      →  CRM / Support / RealEstate / Scheduling / Marketing
```

---

## Security Design

The security layer has three goals: block prompt injection, confine file access, and require approval for risky actions.

**Prompt injection (verified):** `PromptInjectionDetector` runs regex + semantic patterns against every input — including scraped web page content, file contents, and tool outputs. 14 attack categories blocked. See `tests/test_security_kernel.py`.

**Filesystem jail (verified):** All file/shell operations are resolved through `FilesystemJail`. Path traversal is blocked at the `resolve_path` level, before any I/O. Pre-execution snapshots allow rollback. See `tests/test_filesystem_jail.py`.

**Shell blocking (verified):** `ShellTool` checks a static blocklist (`rm -rf /`, `mkfs`, `dd if=`, `> /dev/`) before execution. Note: this is a list of known dangerous signatures, not a complete sandbox — an attacker with shell access could construct bypasses not in the list.

**Operator approval (unverified in integration):** `OperatorApprovalQueue` creates an async queue where risky actions wait for human approval. The code structure is correct. Whether it is consistently triggered in the live agentic loop needs an integration test.

**What "safe desktop autonomy" requires to be proven:**
- [ ] Desktop actions trigger `SecurityKernel` before execution
- [ ] `ASK_USER` verdict blocks execution and waits for approval
- [ ] Approval cannot be bypassed by prompt injection
- [ ] Tested end-to-end on a real desktop

---

## Quick Start

```bash
git clone https://github.com/Soulfullmens/software-brain.git
cd software-brain

python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Linux/Mac

pip install -r requirements.txt

cp .env.example .env
# Add at least one: GEMINI_API_KEY or ANTHROPIC_API_KEY

# Run the API server
python smart_agent_server.py
# Open http://localhost:8000

# Run tests
python -m pytest tests/test_security_kernel.py tests/test_filesystem_jail.py tests/test_shell_tool.py -v
```

### Docker

```bash
docker-compose up -d
```

### CLI Interfaces

```bash
python run_agent.py --chat          # ClaudeAgent chat
python main.py                      # NOMAD Swarm CLI
python jarvis_cli.py                # JarvisV1 with authority modes
```

---

## API

Server runs at `http://localhost:8000`. Swagger UI at `/docs`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/smart-chat/stream` | Streaming autonomous chat |
| POST | `/api/chat` | Non-streaming chat |
| GET  | `/api/status` | Health check |
| POST | `/api/teach` | Store a fact in memory |
| POST | `/api/recall` | Query memory |
| POST | `/api/desktop/command` | Run shell command (sandboxed) |
| POST | `/api/browser/goto` | Navigate browser |
| POST | `/api/learn/start` | Start recording user actions |
| POST | `/api/learn/replay` | Replay recorded workflow |

---

## Project Structure

```
software-brain/
├── src/
│   ├── agent/
│   │   ├── llm_router.py           # Multi-provider LLM with fallback
│   │   ├── autonomous_engine.py    # Think→Plan→Act loop
│   │   ├── reasoning_engine.py     # CoT, ToT, self-reflection
│   │   ├── claude_agent.py         # Unified agent interface
│   │   ├── security/
│   │   │   ├── security_kernel.py  # Injection detection + authority levels
│   │   │   ├── filesystem_jail.py  # Path traversal prevention + snapshots
│   │   │   ├── operator_approval.py
│   │   │   └── safety_governor.py
│   │   ├── tools/
│   │   │   ├── desktop.py          # pyautogui wrapper
│   │   │   ├── shell.py            # Shell execution (sandboxed)
│   │   │   └── browser_tool.py     # Browser automation
│   │   ├── memory/
│   │   │   ├── vector_store.py     # ChromaDB (5 collections)
│   │   │   ├── episodic.py
│   │   │   └── semantic.py
│   │   └── intelligence/
│   │       ├── swarm_orchestrator.py
│   │       └── knowledge_graph.py
│   └── business/
│       ├── multi_agent.py          # 5-agent orchestrator
│       ├── dashboard.py            # FastAPI web dashboard
│       ├── crm_scheduling.py
│       └── uae_solutions.py        # Arabic/English, Dubai property data
├── tests/
│   ├── test_security_kernel.py     # 19 tests — all passing
│   ├── test_filesystem_jail.py     # 7 tests — all passing
│   ├── test_shell_tool.py          # 7 tests — all passing
│   └── test_llm_router.py          # 4 tests — all passing
├── smart_agent_server.py           # Main API server
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── VERIFIED_STATUS.md              # Full honest status table
└── requirements.txt
```

---

## Configuration

```env
# .env (copy from .env.example)
GEMINI_API_KEY=your-key-here
ANTHROPIC_API_KEY=your-key-here
OPENAI_API_KEY=your-key-here          # optional
OPEN_ROUTER_API_KEY=your-key-here     # optional
```

LLM router tries Claude first, then Gemini, then GPT-4, then Ollama. If all fail, returns an error.

---

## What This Is and Isn't

**This is:**
- A real Python codebase with working security primitives (tested)
- A structured agentic loop architecture
- A multi-provider LLM abstraction layer
- A FastAPI server with 20+ endpoints
- A starting point for a production AI agent

**This is not (yet):**
- Fully integration tested end-to-end
- Deployed to production with real users
- Comparable to Claude Computer Use or OpenAI Operator in capability — those have years of testing behind them
- A complete replacement for enterprise agent frameworks

---

## Roadmap

- [ ] Integration tests for live LLM routing (requires API keys in CI secrets)
- [ ] Integration test: desktop action → security kernel → approval gate → execute
- [ ] Deploy to Railway or Render (live demo URL)
- [ ] Add Prometheus metrics endpoint
- [ ] Adversarial fuzzing of prompt injection detector
- [ ] GitHub Actions for auto-deploy

---

## License

MIT  
Built by [Abdul Rahaman Khan](https://github.com/Soulfullmens)
