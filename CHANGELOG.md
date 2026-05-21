# Changelog

All notable changes to Software Brain are documented here.

---

## [1.0.0] — 2026-05-21

### Added
- Multi-provider LLM routing: Claude, Gemini, GPT-4, Ollama with auto-fallback
- Persistent vector memory using ChromaDB (episodic, semantic, procedural, prototype, web knowledge)
- Autonomous Think → Plan → Act → Observe → Reflect loop
- 5-agent business orchestrator: CRM, Support, Real Estate, Scheduling, Marketing
- UAE-specific intelligence: bilingual Arabic/English, Dubai property pricing, government services
- E2E encrypted WebSocket chat server with user authentication
- FastAPI streaming REST API with 20+ endpoints
- Security framework: authority levels, filesystem jail, safety governor, operator approval gates
- Docker and Docker Compose deployment configuration
- Swarm intelligence simulation (crowd simulator)
- Executive brain subsystem: plan validation, reflection, strategy engine
- ReAct framework implementation
- Knowledge graph for entity-relationship storage
- Persona engine for user modeling
- NOMAD airgap mode for offline/air-gapped environments
- JarvisV1 and JarvisV2 CLI interfaces
- Learn mode: record user actions, analyze, replay as automation
- Desktop control and browser automation APIs

### Infrastructure
- Production-grade Dockerfile with non-root user and health checks
- Comprehensive .gitignore (secrets, runtime data, OS files)
- .env.example template for easy onboarding
- Complete API documentation via Swagger UI at /docs
