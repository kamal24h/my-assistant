# ERP MCP Tool Selection Fix

This patch replaces the following Coordinator files:

- `src/coordinator/app/services/mcp_client.py`
- `src/coordinator/app/graphs/workflow.py`

## Changes

1. Removes hard-coded `X-PlaceId` / `X-UserId` values and sends request-scoped tenant/user context instead.
2. Sends tenant/user context on `tools/list` as well as `tools/call`.
3. Preserves MCP session IDs returned by the server and reuses them for subsequent requests in the same client session.
4. Removes response-body logging from MCP transport logs.
5. Adds read-tool policy diagnostics (discovered / allowed / excluded counts and debug-level excluded tool names).
6. Reworks tool selection to compare full descriptions and input schemas, without truncating descriptions at 500 characters.
7. Adds lexical candidate discovery for larger tool catalogs; small/medium catalogs are presented in full to the selector.
8. Validates the selected tool name against the actual policy-filtered allowlist and validates arguments against the selected tool's JSON Schema before returning.
9. Stops silently answering an explicit ERP/MCP request with unrelated RAG content when the direct MCP path fails.

## Important deployment note

Read tools are still restricted by policy. A tool is available to the selector only when the MCP server marks it with `annotations.readOnlyHint: true`, or when its name is explicitly included in `ERP_MCP_READ_ONLY_TOOLS`. Tools marked `readOnlyHint: false` or `destructiveHint: true` remain excluded. If the user-details/roles tool is missing from the `allowed` count, inspect its MCP annotations and the Coordinator read-only allowlist before changing the policy.

The MCP server must continue to validate the bearer token and enforce SSO/RBAC and tenant isolation. The forwarded user/tenant headers are context hints, not proof of identity.

## Validation performed

Both Python files passed `python -m py_compile`. Runtime integration against the actual ERP MCP endpoint was not possible here; test the updated files in the Coordinator container and verify the tool discovery log reports the expected read-only tool count.
