"""MCP Streamable HTTP client with separate read/write tool policies.

Read tools require an explicit read-only hint or administrator allowlist. Write tools
require an explicit administrator allowlist and are callable only by the approval path.
ERP MCP remains responsible for enforcing SSO/RBAC and tenant isolation server-side.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from jsonschema import ValidationError, validate

from coordinator.config import settings

logger = logging.getLogger(__name__)


class McpClientError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def validate_tool_arguments(tool: dict[str, Any], arguments: dict[str, Any]) -> None:
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        raise McpClientError("erp_mcp_tool_schema_missing")
    try:
        validate(instance=arguments, schema=schema)
    except ValidationError as exc:
        raise McpClientError("erp_mcp_tool_arguments_invalid") from exc
    except Exception as exc:
        raise McpClientError("erp_mcp_tool_schema_invalid") from exc


class ErpMcpClient:
    def __init__(self, base_url: str | None = None, timeout: float | None = None,
                 authorization: str | None = None):
        self.base_url = (base_url or settings.erp_mcp_url).rstrip("/")
        self.timeout = timeout or settings.erp_mcp_timeout_seconds
        self.authorization = authorization
        self._request_id = 0
        self._session_id: str | None = None

    def _require_user_auth(self) -> None:
        if settings.erp_mcp_require_user_token and not self.authorization:
            raise McpClientError("erp_mcp_user_token_required")

    def _headers(self, tenant_id: str | None = None, user_id: str | None = None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
        }
        if self.authorization:
            headers["Authorization"] = self.authorization
        elif settings.erp_mcp_bearer_token:
            headers["Authorization"] = f"Bearer {settings.erp_mcp_bearer_token}"
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        # Hints only: the MCP server must derive identity from validated credentials.
        if tenant_id:
            headers["X-ERP-Tenant-Id"] = tenant_id
        if user_id:
            headers["X-ERP-User-Id"] = user_id
        return headers

    async def _post(self, client: httpx.AsyncClient, payload: dict[str, Any], *,
                    tenant_id: str | None = None, user_id: str | None = None,
                    notification: bool = False) -> dict[str, Any] | None:
        try:
            response = await client.post(self.base_url, json=payload,
                                         headers=self._headers(tenant_id, user_id))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("ERP MCP HTTP request failed: %s", type(exc).__name__)
            raise McpClientError("erp_mcp_unavailable") from exc

        sid = response.headers.get("Mcp-Session-Id") or response.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid
        if notification or response.status_code == 202 or not response.content:
            return None

        content_type = response.headers.get("content-type", "")
        try:
            if "text/event-stream" in content_type:
                for line in response.text.splitlines():
                    if line.startswith("data:"):
                        raw = line[5:].strip()
                        if raw:
                            candidate = json.loads(raw)
                            if isinstance(candidate, dict) and ("result" in candidate or "error" in candidate):
                                return candidate
                raise McpClientError("invalid_erp_mcp_response")
            payload_out = response.json()
            if not isinstance(payload_out, dict):
                raise McpClientError("invalid_erp_mcp_response")
            return payload_out
        except (ValueError, json.JSONDecodeError) as exc:
            raise McpClientError("invalid_erp_mcp_response") from exc

    async def _rpc(self, client: httpx.AsyncClient, method: str, params: dict[str, Any] | None = None,
                   *, tenant_id: str | None = None, user_id: str | None = None) -> dict[str, Any]:
        self._request_id += 1
        result = await self._post(
            client,
            {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params or {}},
            tenant_id=tenant_id, user_id=user_id,
        )
        if not result or "error" in result or "result" not in result:
            logger.warning("ERP MCP returned an RPC error for method %s", method)
            raise McpClientError("erp_mcp_rpc_failed")
        return result["result"]

    async def _initialize(self, client: httpx.AsyncClient, tenant_id: str, user_id: str) -> None:
        await self._rpc(
            client, "initialize",
            {"protocolVersion": "2025-03-26", "capabilities": {},
             "clientInfo": {"name": "erp-assistant-coordinator", "version": "0.6.0"}},
            tenant_id=tenant_id, user_id=user_id,
        )
        await self._post(client, {"jsonrpc": "2.0", "method": "notifications/initialized"},
                         tenant_id=tenant_id, user_id=user_id, notification=True)

    @staticmethod
    def _configured_names(value: str) -> set[str]:
        # Support comma/semicolon separated environment values.
        return {name.strip() for name in value.replace(";", ",").split(",") if name.strip()}

    def _allowed_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        configured = self._configured_names(settings.erp_mcp_read_only_tools)
        safe = []
        for tool in tools:
            name = str(tool.get("name", ""))
            annotations = tool.get("annotations") or {}
            explicitly_allowed = name in configured
            marked_read_only = annotations.get("readOnlyHint") is True
            explicitly_not_read_only = annotations.get("readOnlyHint") is False
            destructive = annotations.get("destructiveHint") is True
            if name and not destructive and not explicitly_not_read_only and (explicitly_allowed or marked_read_only):
                safe.append(tool)
        return safe

    def _allowed_write_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        configured = self._configured_names(settings.erp_mcp_write_tools)
        safe = []
        for tool in tools:
            name = str(tool.get("name", ""))
            annotations = tool.get("annotations") or {}
            # Write access is never inferred from model output or tool annotations alone.
            if (name in configured and annotations.get("readOnlyHint") is not True
                    and annotations.get("destructiveHint") is not True
                    and isinstance(tool.get("inputSchema"), dict)):
                safe.append(tool)
        return safe

    async def _list_tools_with_client(self, client: httpx.AsyncClient, tenant_id: str,
                                      user_id: str, mode: str) -> list[dict[str, Any]]:
        await self._initialize(client, tenant_id, user_id)
        result = await self._rpc(client, "tools/list", {}, tenant_id=tenant_id, user_id=user_id)
        tools = result.get("tools", []) if isinstance(result, dict) else []
        if not isinstance(tools, list):
            raise McpClientError("invalid_erp_mcp_tools_response")
        if mode == "read":
            return self._allowed_tools(tools)
        if mode == "write":
            return self._allowed_write_tools(tools)
        return tools

    async def list_read_only_tools(self, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        self._require_user_auth()
        self._session_id = None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await self._list_tools_with_client(client, tenant_id, user_id, "read")

    async def list_write_tools(self, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        self._require_user_auth()
        self._session_id = None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await self._list_tools_with_client(client, tenant_id, user_id, "write")

    async def call_tool(self, name: str, arguments: dict[str, Any], tenant_id: str, user_id: str) -> dict[str, Any]:
        self._require_user_auth()
        return await self._call_tool(name, arguments, tenant_id, user_id, "read")

    async def call_write_tool(self, name: str, arguments: dict[str, Any], tenant_id: str, user_id: str) -> dict[str, Any]:
        self._require_user_auth()
        return await self._call_tool(name, arguments, tenant_id, user_id, "write")

    async def _call_tool(self, name: str, arguments: dict[str, Any], tenant_id: str,
                         user_id: str, mode: str) -> dict[str, Any]:
        self._session_id = None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            tools = await self._list_tools_with_client(client, tenant_id, user_id, mode)
            definition = next((tool for tool in tools if tool.get("name") == name), None)
            if definition is None:
                raise McpClientError("erp_mcp_tool_not_allowed")
            validate_tool_arguments(definition, arguments)
            result = await self._rpc(client, "tools/call", {"name": name, "arguments": arguments},
                                     tenant_id=tenant_id, user_id=user_id)
        if not isinstance(result, dict):
            raise McpClientError("invalid_erp_mcp_tool_result")
        if result.get("isError"):
            raise McpClientError("erp_mcp_tool_failed")
        return {"content": result.get("content", []), "structuredContent": result.get("structuredContent")}

    async def health(self) -> bool:
        # Health checks may use the configured service token; they never invoke a business tool.
        self._session_id = None
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                tools = await self._list_tools_with_client(client, "health-check", "health-check", "all")
            return isinstance(tools, list)
        except McpClientError:
            return False
