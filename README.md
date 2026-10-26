# AI-Coordinator-ERP-System

Monorepo for the Phase 7 ERP Smart Assistant, reorganized from the latest `opt-assist(2).zip` integration.

- Persian guide: [`README.fa.md`](README.fa.md)
- Monorepo migration notes: [`docs/Monorepo_Migration.fa.md`](docs/Monorepo_Migration.fa.md)
- Docker Compose manages the currently implemented services: Coordinator, RAG FastAPI, PostgreSQL, Redis, Qdrant, and Ollama. A real ERP MCP Server is not included yet.

Start with `.env.example`, then run `docker compose up -d --build`. See the Persian README for configuration and API examples.
