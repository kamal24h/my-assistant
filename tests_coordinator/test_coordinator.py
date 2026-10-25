# tests_coordinator/test_coordinator.py
from uuid import uuid4

from fastapi.testclient import TestClient

from coordinator.main import app
import coordinator.main as coordinator_main

client = TestClient(app)


def payload(prompt="سلام", **extra):
    return {
        "appId": "ERP",
        "tenantId": "tenant-1",
        "userId": "user-1",
        "prompt": prompt,
        **extra,
    }


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["version"] == "0.7.0"


def test_chat_routes_general_question_to_local_llm(monkeypatch):
    async def fake_classify(question, *, force_local=False):
        assert question == "سلام"
        return "local_llm"

    class FakeChain:
        async def ainvoke(self, payload):
            assert payload["question"] == "سلام"
            return "سلام! چطور می‌توانم کمک کنم؟"

    async def fake_ensure(client, req):
        return uuid4()

    async def fake_persist(req, conversation_id, answer, selected_path, sources, duration):
        assert selected_path == "local_llm"
        return uuid4()

    monkeypatch.setattr(coordinator_main, "classify_path", fake_classify)
    monkeypatch.setattr(coordinator_main, "get_local_llm_chain", lambda: FakeChain())
    monkeypatch.setattr(coordinator_main, "_ensure_conversation", fake_ensure)
    monkeypatch.setattr(coordinator_main, "persist_non_rag_turn", fake_persist)

    response = client.post("/api/v1/assistant/chat", json=payload())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["selectedPath"] == "local_llm"
    assert body["answer"] == "سلام! چطور می‌توانم کمک کنم؟"
    assert body["sources"] == []


def test_chat_routes_document_question_to_rag(monkeypatch):
    conversation_id = uuid4()

    async def fake_classify(question, *, force_local=False):
        return "local_rag"

    async def fake_rag(req):
        assert req.prompt == "طبق مستندات، روند خرید چیست؟"
        return conversation_id, uuid4(), "طبق مستند، ابتدا درخواست خرید ثبت می‌شود.", [
            {"doc_name": "راهنمای خرید", "doc_id": "doc-1"}
        ]

    monkeypatch.setattr(coordinator_main, "classify_path", fake_classify)
    monkeypatch.setattr(coordinator_main, "invoke_rag_api", fake_rag)

    response = client.post(
        "/api/v1/assistant/chat",
        json=payload("طبق مستندات، روند خرید چیست؟"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["selectedPath"] == "local_rag"
    assert body["conversationId"] == str(conversation_id)
    assert body["answer"] == "طبق مستند، ابتدا درخواست خرید ثبت می‌شود."
    assert body["sources"][0]["doc_name"] == "راهنمای خرید"


def test_chat_rejects_empty_prompt():
    response = client.post("/api/v1/assistant/chat", json=payload(""))
    assert response.status_code == 422


def test_chat_returns_503_when_local_llm_fails(monkeypatch):
    async def fake_classify(question, *, force_local=False):
        return "local_llm"

    class BrokenChain:
        async def ainvoke(self, payload):
            raise RuntimeError("connection details should not leak")

    monkeypatch.setattr(coordinator_main, "classify_path", fake_classify)
    monkeypatch.setattr(coordinator_main, "get_local_llm_chain", lambda: BrokenChain())

    response = client.post("/api/v1/assistant/chat", json=payload())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "assistant_request_failed"
    assert "connection details" not in response.text


def test_chat_returns_controlled_error_when_rag_unavailable(monkeypatch):
    async def fake_classify(question, *, force_local=False):
        return "local_rag"

    async def broken_rag(req):
        raise coordinator_main.RagApiError(502, "rag_api_unavailable")

    monkeypatch.setattr(coordinator_main, "classify_path", fake_classify)
    monkeypatch.setattr(coordinator_main, "invoke_rag_api", broken_rag)

    response = client.post("/api/v1/assistant/chat", json=payload("طبق مستندات داخلی پاسخ بده"))
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "rag_api_unavailable"


def test_chat_rejects_unknown_fields():
    response = client.post("/api/v1/assistant/chat", json=payload(unexpected=True))
    assert response.status_code == 422


def test_chat_routes_live_erp_question_to_mcp(monkeypatch):
    async def fake_classify(question, *, force_local=False):
        return "local_mcp"

    async def fake_mcp_node(req):
        return req

    async def fake_list_tools(self, tenant_id, user_id):
        return [{"name": "inventory_get", "annotations": {"readOnlyHint": True}}]

    async def fake_select(question, tools):
        return {"name": "inventory_get", "arguments": {"item_code": "A-100"}}

    async def fake_call(self, name, arguments, tenant_id, user_id):
        assert name == "inventory_get"
        assert tenant_id == "tenant-1"
        assert user_id == "user-1"
        return {"structuredContent": {"quantity": 12}}

    async def fake_summarize(question, tool_name, result):
        return "موجودی فعلی ۱۲ عدد است."

    monkeypatch.setattr(coordinator_main, "classify_path", fake_classify)
    monkeypatch.setattr(coordinator_main.ErpMcpClient, "list_read_only_tools", fake_list_tools)
    monkeypatch.setattr(coordinator_main, "select_erp_tool", fake_select)
    monkeypatch.setattr(coordinator_main.ErpMcpClient, "call_tool", fake_call)
    async def fake_ensure(client, req):
        return uuid4()

    async def fake_persist(req, conversation_id, answer, selected_path, sources, duration):
        assert selected_path == "local_mcp"
        return uuid4()

    monkeypatch.setattr(coordinator_main, "summarize_erp_result", fake_summarize)
    monkeypatch.setattr(coordinator_main, "_ensure_conversation", fake_ensure)
    monkeypatch.setattr(coordinator_main, "persist_non_rag_turn", fake_persist)

    response = client.post("/api/v1/assistant/chat", json=payload("موجودی فعلی کالای A-100 چقدر است؟"))
    assert response.status_code == 200
    body = response.json()
    assert body["selectedPath"] == "local_mcp"
    assert body["answer"] == "موجودی فعلی ۱۲ عدد است."
    assert body["sources"][0]["tool"] == "inventory_get"


def test_mcp_read_only_filter_rejects_write_tools(monkeypatch):
    from coordinator.mcp_client import ErpMcpClient

    monkeypatch.setattr(coordinator_main.settings, "erp_mcp_read_only_tools", "")
    client_instance = ErpMcpClient()
    tools = [
        {"name": "inventory_get", "annotations": {"readOnlyHint": True}},
        {"name": "purchase_order_create", "annotations": {"readOnlyHint": False}},
        {"name": "delete_record", "annotations": {"readOnlyHint": True, "destructiveHint": True}},
    ]
    assert [tool["name"] for tool in client_instance._allowed_tools(tools)] == ["inventory_get"]


def test_mcp_selection_must_match_allowlisted_tool(monkeypatch):
    import pytest
    from coordinator.mcp_client import McpClientError

    async def fake_classify(question, *, force_local=False):
        return "local_mcp"

    async def fake_tools(self, tenant_id, user_id):
        return [{"name": "inventory_get", "annotations": {"readOnlyHint": True}}]

    async def fake_select(question, tools):
        return {"name": "purchase_order_create", "arguments": {}}

    monkeypatch.setattr(coordinator_main, "classify_path", fake_classify)
    monkeypatch.setattr(coordinator_main.ErpMcpClient, "list_read_only_tools", fake_tools)
    monkeypatch.setattr(coordinator_main, "select_erp_tool", fake_select)
    response = client.post("/api/v1/assistant/chat", json=payload("موجودی فعلی کالا چیست؟"))
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "no_matching_erp_tool"


def test_openai_health_is_configuration_only():
    response = client.get("/health/openai")
    assert response.status_code == 200
    assert response.json()["provider"] == "openai"
    assert "does not send a billable request" in response.json()["note"]


def test_sensitive_erp_question_is_never_routed_to_openai(monkeypatch):
    monkeypatch.setattr(coordinator_main.settings, "openai_enabled", True)
    monkeypatch.setattr(coordinator_main.settings, "openai_api_key", "test-key")

    async def should_not_call_router():
        raise AssertionError("router must not be called for ERP-bound prompts")

    monkeypatch.setattr(coordinator_main, "get_router_chain", should_not_call_router)
    import asyncio
    assert asyncio.run(coordinator_main.classify_path("اطلاعات مشتری شماره 123 را نشان بده")) == "local_mcp"


def test_openai_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(coordinator_main.settings, "openai_enabled", False)
    monkeypatch.setattr(coordinator_main.settings, "openai_api_key", "")

    async def unexpected_router():
        raise AssertionError("router must not be called when OpenAI is disabled")

    monkeypatch.setattr(coordinator_main, "get_router_chain", unexpected_router)
    import asyncio
    assert asyncio.run(coordinator_main.classify_path("یک تحلیل پیچیده درباره فلسفه علم ارائه کن")) == "local_llm"


def test_sanitizer_masks_common_identifiers():
    from coordinator.sanitization import sanitize_for_external_model
    result = sanitize_for_external_model("ایمیل test@example.com و شماره +989121234567")
    assert "test@example.com" not in result
    assert "+989121234567" not in result
    assert "[EMAIL_REDACTED]" in result
    assert "[PHONE_OR_ID_REDACTED]" in result


def test_general_complex_question_can_route_to_openai(monkeypatch):
    monkeypatch.setattr(coordinator_main.settings, "openai_enabled", True)
    monkeypatch.setattr(coordinator_main.settings, "openai_api_key", "test-key")

    class FakeRouter:
        async def ainvoke(self, payload):
            return "openai"

    monkeypatch.setattr(coordinator_main, "get_router_chain", lambda: FakeRouter())
    import asyncio
    assert asyncio.run(coordinator_main.classify_path("یک تحلیل چندمرحله‌ای از نظریه بازی‌ها ارائه کن")) == "openai"


def test_openai_failure_falls_back_to_local_llm(monkeypatch):
    async def fake_classify(question, *, force_local=False):
        return "openai"

    async def broken_openai(question):
        raise coordinator_main.OpenAIUnavailable("openai_request_failed")

    class FakeChain:
        async def ainvoke(self, payload):
            return "پاسخ محلی جایگزین"

    async def fake_ensure(client, req):
        return uuid4()

    async def fake_persist(req, conversation_id, answer, selected_path, sources, duration):
        assert selected_path == "local_llm_fallback"
        assert answer == "پاسخ محلی جایگزین"
        return uuid4()

    monkeypatch.setattr(coordinator_main, "classify_path", fake_classify)
    monkeypatch.setattr(coordinator_main, "generate_openai_answer", broken_openai)
    monkeypatch.setattr(coordinator_main, "get_local_llm_chain", lambda: FakeChain())
    monkeypatch.setattr(coordinator_main, "_ensure_conversation", fake_ensure)
    monkeypatch.setattr(coordinator_main, "persist_non_rag_turn", fake_persist)

    response = client.post("/api/v1/assistant/chat", json=payload("یک تحلیل پیچیده ارائه کن"))
    assert response.status_code == 200
    assert response.json()["selectedPath"] == "local_llm_fallback"
    assert response.json()["answer"] == "پاسخ محلی جایگزین"


def test_erp_write_intent_is_routed_to_approval_path():
    import asyncio
    assert asyncio.run(coordinator_main.classify_path("یک درخواست خرید برای کالای A-100 ثبت کن")) == "erp_write"


def test_write_tools_require_explicit_allowlist_and_reject_destructive(monkeypatch):
    from coordinator.mcp_client import ErpMcpClient
    monkeypatch.setattr(coordinator_main.settings, "erp_mcp_write_tools", "purchase_request_create")
    client_instance = ErpMcpClient(authorization="Bearer test-token")
    tools = [
        {"name": "purchase_request_create", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}, "annotations": {"readOnlyHint": False}},
        {"name": "purchase_order_delete", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}, "annotations": {"readOnlyHint": False, "destructiveHint": True}},
        {"name": "invoice_create", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}, "annotations": {"readOnlyHint": False}},
    ]
    assert [tool["name"] for tool in client_instance._allowed_write_tools(tools)] == ["purchase_request_create"]


def test_write_tool_argument_schema_is_enforced():
    import pytest
    from coordinator.mcp_client import McpClientError, validate_tool_arguments
    tool = {"name": "purchase_request_create", "inputSchema": {
        "type": "object", "properties": {"item_code": {"type": "string"}},
        "required": ["item_code"], "additionalProperties": False,
    }}
    validate_tool_arguments(tool, {"item_code": "A-100"})
    with pytest.raises(McpClientError) as exc:
        validate_tool_arguments(tool, {"item_code": "A-100", "admin": True})
    assert exc.value.code == "erp_mcp_tool_arguments_invalid"


def test_write_chat_creates_pending_approval_without_calling_erp(monkeypatch):
    approval_id = uuid4()
    conversation_id = uuid4()
    captured = {}

    async def fake_classify(question, *, force_local=False):
        return "erp_write"

    async def fake_tools(self, tenant_id, user_id):
        return [{
            "name": "purchase_request_create",
            "description": "ایجاد درخواست خرید",
            "inputSchema": {
                "type": "object",
                "properties": {"item_code": {"type": "string"}},
                "required": ["item_code"],
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": False, "destructiveHint": False},
        }]

    async def fake_select(question, tools):
        return {"name": "purchase_request_create", "arguments": {"item_code": "A-100"}}

    async def fake_ensure(client_arg, req):
        return conversation_id

    async def fake_create(record, ttl_seconds):
        captured["record"] = record
        captured["ttl"] = ttl_seconds

    async def fake_persist(req, conv_id, answer, selected_path, sources, duration):
        assert selected_path == "erp_write_pending"
        return uuid4()

    async def should_not_execute(*args, **kwargs):
        raise AssertionError("write tool must not run before approval")

    monkeypatch.setattr(coordinator_main, "classify_path", fake_classify)
    monkeypatch.setattr(coordinator_main.ErpMcpClient, "list_write_tools", fake_tools)
    monkeypatch.setattr(coordinator_main, "select_erp_tool", fake_select)
    monkeypatch.setattr(coordinator_main, "_ensure_conversation", fake_ensure)
    monkeypatch.setattr(coordinator_main.approval_store, "create", fake_create)
    monkeypatch.setattr(coordinator_main, "persist_non_rag_turn", fake_persist)
    monkeypatch.setattr(coordinator_main.ErpMcpClient, "call_write_tool", should_not_execute)

    response = client.post(
        "/api/v1/assistant/chat",
        json=payload("یک درخواست خرید برای کالای A-100 ثبت کن"),
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending_approval"
    assert body["selectedPath"] == "erp_write_pending"
    assert body["approvalId"]
    assert captured["record"]["status"] == "pending"
    assert captured["record"]["toolName"] == "purchase_request_create"


def test_approval_endpoint_executes_only_pending_allowlisted_write(monkeypatch):
    approval_id = uuid4()
    conversation_id = uuid4()
    record = {
        "approvalId": str(approval_id), "requestId": str(uuid4()),
        "conversationId": str(conversation_id), "appId": "ERP",
        "tenantId": "tenant-1", "userId": "user-1",
        "prompt": "یک درخواست خرید برای کالای A-100 ثبت کن",
        "toolName": "purchase_request_create", "arguments": {"item_code": "A-100"},
        "status": "pending", "createdAt": "2026-10-18T10:00:00+00:00",
        "expiresAt": "2099-10-18T10:00:00+00:00",
    }
    executed = {"called": False}

    async def fake_lock(aid): return "lock-token"
    async def fake_release(aid, token): return None
    async def fake_get(aid): return record
    async def fake_save(updated): record.update(updated)
    async def fake_audit(event): return None
    async def fake_call(self, name, arguments, tenant_id, user_id):
        executed["called"] = True
        assert name == "purchase_request_create"
        assert user_id == "approver-1"
        return {"structuredContent": {"request_id": "PR-1001", "status": "created"}}
    async def fake_summary(question, tool_name, result): return "درخواست خرید PR-1001 ایجاد شد."
    async def fake_persist(req, conv_id, answer, selected_path, sources, duration): return uuid4()

    monkeypatch.setattr(coordinator_main.settings, "approval_api_key", "internal-test-key")
    monkeypatch.setattr(coordinator_main.settings, "approval_allow_self_approval", False)
    monkeypatch.setattr(coordinator_main.approval_store, "acquire_lock", fake_lock)
    monkeypatch.setattr(coordinator_main.approval_store, "release_lock", fake_release)
    monkeypatch.setattr(coordinator_main.approval_store, "get", fake_get)
    monkeypatch.setattr(coordinator_main.approval_store, "save", fake_save)
    monkeypatch.setattr(coordinator_main.approval_store, "audit", fake_audit)
    monkeypatch.setattr(coordinator_main.ErpMcpClient, "call_write_tool", fake_call)
    monkeypatch.setattr(coordinator_main, "summarize_erp_result", fake_summary)
    monkeypatch.setattr(coordinator_main, "persist_non_rag_turn", fake_persist)

    response = client.post(
        f"/api/v1/erp/approvals/{approval_id}/approve",
        json={"tenantId": "tenant-1", "approverUserId": "approver-1", "comment": "تأیید شد"},
        headers={"X-API-Key": "internal-test-key", "Authorization": "Bearer approver-token"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert executed["called"] is True
    assert record["status"] == "succeeded"
