# Tests

- `coordinator_tests/`: existing Coordinator tests.
- `rag_tests/`: reserved for RAG API/service tests; add fixtures for PostgreSQL, Qdrant, Redis, and model dependencies as appropriate.
- `integration_tests/`, `contract_tests/`, and `e2e_tests/` should be added as service contracts stabilize.

Run Python tests from repository root with `PYTHONPATH=src/coordinator:src/rag_service pytest tests`. Live integration/E2E tests require the relevant services and are not run by the lightweight unit-test command.
