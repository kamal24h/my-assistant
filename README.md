# AI-Coordinator-ERP-System

Monorepo for the Phase 7 ERP Smart Assistant, reorganized from the latest `opt-assist(2).zip` integration.

- Persian guide: [`README.fa.md`](README.fa.md)
- Monorepo migration notes: [`docs/Monorepo_Migration.fa.md`](docs/Monorepo_Migration.fa.md)
- Docker Compose manages the currently implemented services: Coordinator, RAG FastAPI, PostgreSQL, Redis, Qdrant, and Ollama. A real ERP MCP Server is not included yet.

Start with `.env.example`, then run `docker compose up -d --build`. See the Persian README for configuration and API examples.


## Python Assistant API gateway

The monorepo now includes a separate public FastAPI gateway at `src/assistant_api`. It forwards `POST /api/v1/assistant/chat` to the existing LangGraph Coordinator and leaves the full Local RAG service and its document APIs in `src/rag_service` unchanged.

- Host endpoint: `http://localhost:8003` (bound to loopback by default)
- Swagger: `http://localhost:8003/docs`
- Health: `GET /health`
- Chat: `POST /api/v1/assistant/chat`
- Optional gateway authentication: `X-API-Key: <ASSISTANT_API_KEY>` when `ASSISTANT_API_KEY` is set in `.env`
- The user's `Authorization: Bearer ...` token is forwarded to Coordinator/MCP unchanged.

Start/rebuild with `docker compose up -d --build assistant-api coordinator fastapi`. This adds a new API entry point; it does not remove the existing .NET integration example or alter Local RAG endpoints.
