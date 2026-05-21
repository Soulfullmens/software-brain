# Software Brain — Autonomous AI Agent Platform

> A production-grade AI agent platform with multi-provider LLM routing, persistent vector memory, multi-agent business orchestration, and UAE-specific intelligence.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-Private-red.svg)]()

---

## What Is This?

Software Brain is a full-stack autonomous AI agent that **thinks, plans, and acts** — not just generates text. It coordinates multiple specialized agents, uses persistent memory, and automates real business workflows.

**Key capabilities:**
- Multi-provider LLM routing (Claude → Gemini → GPT-4 → Ollama with auto-fallback)
- Persistent episodic, semantic, and procedural memory (ChromaDB)
- Think → Plan → Act → Observe → Reflect autonomous loop
- 5 specialized business agents orchestrated by a master controller
- UAE-specific intelligence: Arabic/English bilingual, Dubai property data, government services
- E2E encrypted WebSocket chat server
- REST API with streaming responses
- Docker deployment ready

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Claude-Level Agent                         │
│  LLMRouter (4 providers)  │  ReasoningEngine (CoT/ToT)       │
│  ConversationManager      │  AutonomousEngine (loop)         │
│  ToolProtocol (agentic)   │  CodeEngine (gen/fix/run)        │
├──────────────────────────────────────────────────────────────┤
│                   Multi-Agent Business Layer                  │
│  CRM Agent │ Support Agent │ Real Estate │ Scheduling │ Mktg  │
├──────────────────────────────────────────────────────────────┤
│                   Memory & Intelligence                       │
│  VectorStore (ChromaDB)  │  KnowledgeGraph  │  PersonaEngine │
├──────────────────────────────────────────────────────────────┤
│                   Security & Governance                       │
│  SecurityKernel  │  FilesystemJail  │  SafetyGovernor        │
└──────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Option 1: Local Python

```bash
# 1. Clone the repository
git clone https://github.com/Soulfullmens/software-brain.git
cd software-brain

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate      # Linux/Mac
.venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and add your API keys (at minimum GEMINI_API_KEY or ANTHROPIC_API_KEY)

# 5. Run the web dashboard
python -m src.business.dashboard
# Open http://localhost:8000

# 6. Or run the CLI agent
python run_agent.py --chat
```

### Option 2: Docker (Recommended for Production)

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Option 3: CLI Interfaces

```bash
# NOMAD Swarm CLI (main)
python main.py

# JarvisV1 CLI (authority modes)
python jarvis_cli.py

# ClaudeAgent CLI (goal execution)
python run_agent.py --goal "Research AI trends and write a report"
python run_agent.py --chat
```

---

## API Reference

The server runs at `http://localhost:8000`. Interactive docs at `/docs` (Swagger UI).

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/smart-chat/stream` | Autonomous streaming chat |
| POST | `/api/chat` | Regular chat (non-streaming) |
| GET  | `/api/status` | Server health + agent status |
| GET  | `/docs` | Swagger UI (API explorer) |

### Memory

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/teach` | Teach the agent a fact |
| POST | `/api/remember` | Store a memory explicitly |
| POST | `/api/recall` | Query stored memories |

### Desktop Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/desktop/app` | Launch an application |
| POST | `/api/desktop/command` | Run a shell command |
| POST | `/api/desktop/screenshot` | Capture screen |

### Browser Automation

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/browser/goto` | Navigate to URL |
| POST | `/api/browser/click` | Click element |
| POST | `/api/browser/fill` | Fill form field |
| POST | `/api/browser/screenshot` | Browser screenshot |

### Learn Mode (Record & Replay)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/learn/start` | Start recording user actions |
| POST | `/api/learn/stop` | Stop recording |
| POST | `/api/learn/analyze` | Analyze recorded session |
| POST | `/api/learn/replay` | Replay learned workflow |

### Example: Chat Request

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Analyze the Dubai real estate market for 2024"}'
```

### Example: Streaming Chat

```python
import requests, json

response = requests.post(
    "http://localhost:8000/api/smart-chat/stream",
    json={"message": "Create a business plan for a Dubai tech startup"},
    stream=True
)
for line in response.iter_lines():
    if line:
        print(json.loads(line).get("content", ""), end="", flush=True)
```

---

## Multi-Agent System

5 specialized agents coordinated by a master orchestrator — just describe what you need in natural language:

```python
from src.business.multi_agent import Orchestrator

orch = Orchestrator()
result = orch.handle_natural("I need a 3-bedroom villa in Dubai Marina under 3M AED")
# Automatically routes to Real Estate Agent
```

| Agent | Capabilities |
|-------|-------------|
| **CRM Agent** | Lead management, contact tracking, deal pipeline, lead scoring |
| **Support Agent** | Ticket creation, knowledge base search, issue resolution |
| **Real Estate Agent** | Property search, market analysis, Dubai district pricing |
| **Scheduling Agent** | Appointment booking, calendar management, reminders |
| **Marketing Agent** | Campaign creation, content generation, analytics |

---

## UAE Intelligence

- **Bilingual** — auto-detects Arabic or English, responds in same language
- **Dubai property pricing** — area-based predictions for 15+ districts (Marina, Downtown, Hills, etc.)
- **Government services** — visa requirements, Emirates ID, business licensing guides
- **Smart city metrics** — traffic, energy, environment data by district
- **Cultural awareness** — UAE customs, Sun–Thu work week, AED currency, prayer times

---

## Configuration

Copy `.env.example` to `.env` and fill in your API keys:

```env
# Primary LLM (choose at least one)
GEMINI_API_KEY=your-gemini-api-key-here
ANTHROPIC_API_KEY=your-anthropic-api-key-here

# Optional
OPENAI_API_KEY=your-openai-api-key-here
OPEN_ROUTER_API_KEY=your-openrouter-api-key-here

# Local fallback (no API key needed)
# OLLAMA_URL=http://localhost:11434
```

**Getting API Keys:**
- Gemini: [aistudio.google.com](https://aistudio.google.com) — free tier available
- Claude: [console.anthropic.com](https://console.anthropic.com)
- OpenRouter: [openrouter.ai](https://openrouter.ai) — aggregates multiple providers

The LLM router tries each provider in order and automatically falls back if one fails.

---

## Project Structure

```
software-brain/
├── src/
│   ├── agent/                     # Core AI Agent
│   │   ├── llm_router.py          # Multi-provider LLM routing
│   │   ├── claude_agent.py        # Unified agent interface
│   │   ├── autonomous_engine.py   # Think→Plan→Act loop
│   │   ├── reasoning_engine.py    # CoT, ToT, self-reflection
│   │   ├── conversation_manager.py
│   │   ├── tool_protocol.py       # Agentic tool execution loop
│   │   ├── code_engine.py         # Code gen/fix/run
│   │   ├── brain/                 # Executive brain subsystem
│   │   │   ├── controller.py
│   │   │   ├── safety_governor.py
│   │   │   ├── reflection.py
│   │   │   └── strategy_engine.py
│   │   ├── intelligence/          # Swarm, knowledge graph, personas
│   │   │   ├── swarm_orchestrator.py
│   │   │   ├── knowledge_graph.py
│   │   │   └── persona_engine.py
│   │   ├── memory/                # Persistent vector memory
│   │   │   ├── vector_store.py    # ChromaDB (5 collections)
│   │   │   ├── episodic.py
│   │   │   └── semantic.py
│   │   ├── security/              # Authority levels + safety gates
│   │   │   ├── security_kernel.py
│   │   │   ├── filesystem_jail.py
│   │   │   └── safety_governor.py
│   │   └── tools/                 # Browser, desktop, shell, email
│   ├── business/                  # Business Automation Layer
│   │   ├── multi_agent.py         # 5-agent orchestrator
│   │   ├── dashboard.py           # FastAPI web UI + REST API
│   │   ├── crm_scheduling.py      # CRM + appointments
│   │   ├── uae_solutions.py       # UAE-specific intelligence
│   │   └── workflow_engine.py
│   └── memory/                    # Top-level memory manager
├── chat_platform/                 # Secure WebSocket Chat Server
│   ├── server.py                  # aiohttp + E2E encryption
│   ├── db.py                      # User auth + message storage
│   └── crypto.py                  # PBKDF2 hashing
├── jarvis_v2/                     # Jarvis V2 framework (CLI)
├── smart_agent_server.py          # FastAPI streaming server (main API)
├── main.py                        # NOMAD Swarm CLI
├── run_agent.py                   # ClaudeAgent CLI
├── jarvis_cli.py                  # JarvisV1 CLI
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Deployment

### Docker Compose (Recommended)

```bash
docker-compose up -d
```

The service starts on port `8000` with:
- Auto-restart on failure
- Health checks every 30 seconds
- Persistent `agent_data/` volume
- Non-root container user for security

### Manual Server Start

```bash
uvicorn smart_agent_server:app --host 0.0.0.0 --port 8000 --reload
```

### Production Checklist

- [ ] Set all API keys in `.env`
- [ ] Mount `agent_data/` to persistent storage
- [ ] Set up a reverse proxy (nginx) for HTTPS
- [ ] Configure firewall rules (only expose port 80/443)
- [ ] Set up log rotation
- [ ] Monitor `/api/status` endpoint

---

## Security

- **Authority levels**: LOCKED → PARANOID → SAFE → BALANCED → EXPERT
- **Filesystem jail**: Agent can only write to allowed directories
- **Safety governor**: Risk assessment before any destructive action
- **Operator approval gates**: Confirmation required for high-risk operations
- **E2E encrypted chat**: PBKDF2-hashed credentials, encrypted messages

---

## Contributing

This is a private repository. If you have access and want to contribute:

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make your changes
3. Test thoroughly: `python -m pytest tests/ -v`
4. Submit a pull request

---

## License

Private — All Rights Reserved  
Built by [Abdul Rahaman Khan](https://github.com/Soulfullmens)
