# ERP Integration / MCP Server — implementation pending

Phase 7 currently includes an MCP client in the Python Coordinator and a tool contract in `docs/MCP_TOOLS_CONTRACT.md`, but not a real ERP MCP Server implementation. This folder is a reserved location for the future .NET MCP Server. Do not enable a fake service in Docker Compose. Implement the server against the actual ERP APIs, SSO/authorization model, and approved tool catalog before adding it as a service.
