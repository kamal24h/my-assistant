# src/assistant_api/app/main.py
"""Public Python/FastAPI gateway for ERP Smart Assistant.

Architecture:
  - Client talks ONLY to this service.
  - Chat/stream/approvals/conversations -> Coordinator (internal).
  - Documents -> RAG (internal, direct).
  - Coordinator, RAG, LLM, MCP are NOT exposed outside the assistant_network.
  - Backward compatibility endpoints preserved for existing clients.

Authentication:
  - Client authenticates with X-API-Key (ASSISTANT_API_KEY).
  - End-user SSO token is forwarded as Authorization: Bearer for MCP/approval.
  - Service-to-service credentials (APPROVAL_API_KEY) are added by this
    gateway only when calling Coordinator approval endpoints.

appId -> appIds migration (Option B, backward compatible):
  - Input:  accepts both `appIds` (preferred) and legacy `appId`.
            If only `appId` is provided it is promoted to `appIds=[appId]`.
  - Output: `ConversationOut` exposes BOTH `app_ids` (canonical) and
            `app_id` (first element, kept for legacy clients).
  - Chat endpoints still use a single `appId` because the Coordinator's
    ChatRequest contract has not migrated yet.
"""
from __future__ import annotations

import hmac
import json
import os
from contextlib import asynccontextmanager
from typing import Any, Literal, Optional
from uuid import UUID

import httpx
from fastapi import (
    FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import (
    BaseModel, ConfigDict, Field, field_validator, model_validator,
)

COORDINATOR_URL = os.getenv("COORDINATOR_URL", "http://coordinator:8101").rstrip("/")
RAG_API_URL = os.getenv("RAG_API_URL", "http://rag:8102").rstrip("/")
ASSISTANT_API_KEY = os.getenv("ASSISTANT_API_KEY", "").strip()
APPROVAL_API_KEY = os.getenv("APPROVAL_API_KEY", "").strip()
REQUEST_TIMEOUT = float(os.getenv("ASSISTANT_API_TIMEOUT_SECONDS", "90"))


# ============================================================
# Schemas
# ============================================================

# ---------- New schemas (chat, approvals) ----------

class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    requestId: str | None = None
    conversationId: str | None = None
    messageId: str | None = None
    appId: str = Field(min_length=1, max_length=100)
    tenantId: str = Field(min_length=1, max_length=100)
    userId: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=12000)
    locale: str = Field(default="fa-IR", max_length=20)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("requestId", "conversationId", "messageId")
    @classmethod
    def _validate_uuid_format(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            UUID(value)
        except (ValueError, TypeError) as exc:
            raise ValueError("must be a valid UUID string") from exc
        return value


class ApprovalActionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    tenantId: str = Field(min_length=1, max_length=100)
    approverUserId: str = Field(min_length=1, max_length=200)
    comment: str | None = Field(default=None, max_length=1000)


# ---------- Compat schemas (from previous version) ----------

class ConversationCreate(BaseModel):
    """Conversation creation payload.

    Preferred field is `appIds: list[str]`.
    Legacy `appId: str` is still accepted and promoted to `appIds=[appId]`.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    appIds: list[str] = Field(min_length=1, max_length=50)
    tenantId: str
    userId: str
    userName: Optional[str] = None
    tenantDesc: Optional[str] = None
    title: Optional[str] = None

    @field_validator("appIds")
    @classmethod
    def _validate_app_ids(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip() for v in value if isinstance(v, str) and v.strip()]
        if not cleaned:
            raise ValueError("appIds must contain at least one non-empty id")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("appIds must not contain duplicates")
        return cleaned

    @model_validator(mode="before")
    @classmethod
    def _promote_legacy_app_id(cls, data: Any) -> Any:
        """Backward compatibility: accept `appId` and map it to `appIds`.

        - If `appIds` is already present, `appId` is dropped (extra=forbid).
        - If only `appId` is present, it becomes `appIds=[appId]`.
        - If neither is present, leave untouched so `appIds` validation fails
          with a clear error.
        """
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "appIds" not in data and "appId" in data:
            legacy = data.get("appId")
            if isinstance(legacy, str) and legacy.strip():
                data["appIds"] = [legacy]
        # `appId` is not a declared field (extra=forbid) — drop it after mapping.
        data.pop("appId", None)
        return data


class ConversationUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    title: Optional[str] = None
    status: Optional[Literal["active", "closed", "archived"]] = None


class ConversationOut(BaseModel):
    """Public conversation representation.

    Exposes both `app_ids` (canonical) and `app_id` (first element) for
    backward compatibility with clients reading the legacy field.
    """

    model_config = ConfigDict(from_attributes=True)
    id: UUID
    app_ids: list[str] = Field(default_factory=list)
    app_id: Optional[str] = None
    tenant_id: str
    user_id: str
    user_name: Optional[str] = None
    tenant_desc: Optional[str] = None
    title: Optional[str] = None
    status: str
    feedback_score: Optional[int] = None
    created_at: Any  # datetime — Any برای سازگاری
    updated_at: Any
    ended_at: Optional[Any] = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    conversation_id: UUID
    query: Optional[str] = None
    answer: Optional[str] = None
    duration: Optional[float] = None
    error: Optional[str] = None
    meta_info: Optional[dict[str, Any]] = None
    liked: Optional[bool] = None
    created_at: Any
    role: Optional[str] = None
    content: Optional[str] = None


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut] = Field(default_factory=list)


class SendMessageRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    prompt: str = Field(min_length=1)
    tenantId: Optional[str] = None
    userId: Optional[str] = None


class MessageLikeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    liked: bool


class ConversationFeedbackRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    feedbackScore: int = Field(ge=1, le=5)


# ---------- Documents schemas (from RAG) ----------

class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    logicalDocId: UUID
    version: int
    isCurrent: bool
    previousVersionId: Optional[UUID] = None
    contentHash: Optional[str] = None
    docName: str
    docType: str
    department: str
    appId: str
    metadata: Optional[dict[str, Any]] = None
    chunksCount: int
    createdAt: Any


class DocumentVersionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version: int
    isCurrent: bool
    contentHash: Optional[str] = None
    chunksCount: int
    createdAt: Any
    previousVersionId: Optional[UUID] = None


class TextDocumentItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    doc_name: str
    metadata: Optional[dict[str, Any]] = None
    doc_type: Literal["text"] = "text"
    doc: str


class TextDocumentsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    app_id: str
    version: Optional[str] = None
    documents: list[TextDocumentItem]


# ============================================================
# App lifecycle
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(REQUEST_TIMEOUT))
    yield
    await app.state.http.aclose()


app = FastAPI(
    title="Arian Smart Assistant API",
    description=(
        "Public entry point for ERP Smart Assistant. "
        "Chat, streaming, conversations, and approvals are forwarded to the Coordinator. "
        "Document management is forwarded directly to the RAG service. "
        "Legacy endpoints (POST /conversations, POST /messages) are preserved for compatibility."
    ),
    version="1.4.0",
    lifespan=lifespan,
)


# ============================================================
# Auth helpers
# ============================================================

def _check_api_key(provided: str | None) -> None:
    # If ASSISTANT_API_KEY is configured, it is mandatory for every client call.
    # Empty value is allowed ONLY for trusted private-network deployments where
    # authentication is enforced by an upstream gateway (e.g. reverse proxy).
    if ASSISTANT_API_KEY and (not provided or not hmac.compare_digest(provided, ASSISTANT_API_KEY)):
        raise HTTPException(status_code=401, detail={"code": "invalid_api_key"})


def _coordinator_headers(
    *,
    forward_auth: str | None = None,
    include_approval_key: bool = False,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    if forward_auth:
        headers["Authorization"] = forward_auth
    if include_approval_key:
        service_key = APPROVAL_API_KEY or ASSISTANT_API_KEY
        if service_key:
            headers["X-API-Key"] = service_key
    return headers


# ============================================================
# Forward helpers
# ============================================================

async def _coordinator_forward(
    request: Request,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    forward_auth: str | None = None,
    include_approval_key: bool = False,
) -> Any:
    """Forward a request to the Coordinator and normalize errors.

    Raises HTTPException with the Coordinator's status code and body (if JSON).
    """
    url = f"{COORDINATOR_URL}{path}"
    headers = _coordinator_headers(
        forward_auth=forward_auth, include_approval_key=include_approval_key,
    )
    try:
        response = await request.app.state.http.request(
            method, url, params=params, json=json_body, headers=headers,
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail={"code": "coordinator_timeout"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail={"code": "coordinator_unavailable"}) from exc

    try:
        body = response.json()
    except ValueError:
        body = {"detail": "Coordinator returned a non-JSON response."}
    if response.is_error:
        detail = body.get("detail", body) if isinstance(body, dict) else body
        raise HTTPException(status_code=response.status_code, detail=detail)
    return body


async def _rag_forward(
    request: Request,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    files: Any = None,
    data: dict[str, Any] | None = None,
) -> Any:
    url = f"{RAG_API_URL}{path}"
    try:
        response = await request.app.state.http.request(
            method, url, params=params, json=json_body, files=files, data=data,
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail={"code": "rag_timeout"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail={"code": "rag_unavailable"}) from exc

    try:
        body = response.json()
    except ValueError:
        body = {"detail": "RAG returned a non-JSON response."}
    if response.is_error:
        detail = body.get("detail", body) if isinstance(body, dict) else body
        raise HTTPException(status_code=response.status_code, detail=detail)
    return body


def _normalize_conversation_out(body: Any) -> Any:
    """Ensure both `app_ids` and `app_id` are present in a conversation payload.

    Accepts dict or list of dicts. Non-dict payloads are returned unchanged so
    FastAPI can produce a proper validation error if the upstream returned
    something unexpected.
    """
    if isinstance(body, list):
        return [_normalize_conversation_out(item) for item in body]
    if not isinstance(body, dict):
        return body

    body = dict(body)

    app_ids_raw = body.get("app_ids")
    if app_ids_raw is None:
        app_ids_raw = body.get("appIds")

    legacy_app_id = body.get("app_id")
    if legacy_app_id is None:
        legacy_app_id = body.get("appId")

    # Build canonical list
    if isinstance(app_ids_raw, list):
        app_ids = [v for v in app_ids_raw if isinstance(v, str) and v.strip()]
    elif isinstance(app_ids_raw, str) and app_ids_raw.strip():
        app_ids = [app_ids_raw]
    elif isinstance(legacy_app_id, str) and legacy_app_id.strip():
        app_ids = [legacy_app_id]
    else:
        app_ids = []

    body["app_ids"] = app_ids
    body["app_id"] = app_ids[0] if app_ids else None
    # Remove alternate casing keys to keep the response surface consistent
    body.pop("appIds", None)
    body.pop("appId", None)
    return body


# ============================================================
# Health
# ============================================================

@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "service": "assistant-api",
        "coordinator": COORDINATOR_URL,
        "rag": RAG_API_URL,
    }


# ============================================================
# Chat  (new non-stream)
# ============================================================

@app.post("/api/v1/assistant/chat", tags=["Assistant"])
async def chat(
    payload: ChatRequest,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    if authorization and not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"code": "invalid_authorization_scheme"})
    return await _coordinator_forward(
        request, "POST", "/api/v1/assistant/chat",
        json_body=payload.model_dump(exclude_none=True, by_alias=True),
        forward_auth=authorization,
    )


# ---------------------------------------------------------
# Chat (SSE streaming)
# ---------------------------------------------------------

async def _stream_coordinator(
    request: Request,
    payload_json: dict[str, Any],
    forward_auth: str | None,
):
    headers = _coordinator_headers(forward_auth=forward_auth)
    url = f"{COORDINATOR_URL}/api/v1/assistant/chat/stream"
    try:
        async with request.app.state.http.stream(
            "POST", url, json=payload_json, headers=headers,
        ) as response:
            if response.status_code >= 400:
                raw = await response.aread()
                try:
                    detail = json.loads(raw).get("detail", {"code": "coordinator_error"})
                except Exception:
                    detail = {"code": "coordinator_error", "message": "Non-JSON error response."}
                data = json.dumps(detail, ensure_ascii=False)
                yield f"event: error\ndata: {data}\n\n".encode("utf-8")
                return
            async for chunk in response.aiter_bytes():
                yield chunk
    except httpx.TimeoutException:
        yield b'event: error\ndata: {"code": "coordinator_timeout"}\n\n'
    except httpx.HTTPError:
        yield b'event: error\ndata: {"code": "coordinator_unavailable"}\n\n'


@app.post("/api/v1/assistant/chat/stream", tags=["Assistant"])
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    if authorization and not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"code": "invalid_authorization_scheme"})
    return StreamingResponse(
        _stream_coordinator(
            request,
            payload.model_dump(exclude_none=True, by_alias=True),
            authorization,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================
# Conversation Management (compat + new)
# ============================================================

@app.post(
    "/api/v1/conversations",
    response_model=ConversationOut,
    tags=["Conversations"],
    summary="Create conversation (legacy, forwarded to RAG)",
    description=(
        "Legacy endpoint. In the new flow, conversations are created automatically on the first chat. "
        "Preserved for backward compatibility. "
        "Accepts both `appIds: list[str]` (preferred) and legacy `appId: str`."
    ),
)
async def create_conversation(
    payload: ConversationCreate,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)

    # Send canonical `appIds` plus a legacy `appId` alias so that RAG services
    # that have not yet migrated keep working.
    body = payload.model_dump(exclude_none=True, by_alias=True)
    if body.get("appIds"):
        body.setdefault("appId", body["appIds"][0])

    result = await _rag_forward(
        request, "POST", "/api/v1/conversations",
        json_body=body,
    )
    return _normalize_conversation_out(result)


@app.get(
    "/api/v1/conversations",
    response_model=list[ConversationOut],
    tags=["Conversations"],
    description=(
        "List conversations. Filters by `appIds` (repeatable query param). "
        "Legacy `appId` is also accepted and treated as a single-element list."
    ),
)
async def list_conversations(
    request: Request,
    tenant_id: str = Query(alias="tenantId", min_length=1, max_length=100),
    user_id: str = Query(alias="userId", min_length=1, max_length=200),
    app_ids: list[str] | None = Query(default=None, alias="appIds"),
    app_id: str | None = Query(default=None, alias="appId", max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)

    effective_app_ids: list[str] = []
    if app_ids:
        effective_app_ids = [v.strip() for v in app_ids if v and v.strip()]
    elif app_id:
        effective_app_ids = [app_id.strip()]

    params: dict[str, Any] = {
        "tenantId": tenant_id, "userId": user_id,
        "limit": limit, "offset": offset,
    }
    if effective_app_ids:
        params["appIds"] = effective_app_ids
        # Compatibility: also send the first id under the legacy key.
        params["appId"] = effective_app_ids[0]

    result = await _coordinator_forward(
        request, "GET", "/api/v1/conversations", params=params,
    )
    return _normalize_conversation_out(result)


@app.get(
    "/api/v1/conversations/{conv_id}",
    response_model=ConversationDetailOut,
    tags=["Conversations"],
)
async def get_conversation(
    conv_id: UUID,
    request: Request,
    tenant_id: str | None = Query(default=None, alias="tenantId", max_length=100),
    user_id: str | None = Query(default=None, alias="userId", max_length=200),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    params: dict[str, Any] = {}
    if tenant_id:
        params["tenantId"] = tenant_id
    if user_id:
        params["userId"] = user_id
    result = await _coordinator_forward(
        request, "GET", f"/api/v1/conversations/{conv_id}",
        params=params or None,
    )
    return _normalize_conversation_out(result)


@app.patch(
    "/api/v1/conversations/{conv_id}",
    response_model=ConversationOut,
    tags=["Conversations"],
)
async def update_conversation(
    conv_id: UUID,
    payload: ConversationUpdate,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    result = await _coordinator_forward(
        request, "PATCH", f"/api/v1/conversations/{conv_id}",
        json_body=payload.model_dump(exclude_none=True, by_alias=True),
    )
    return _normalize_conversation_out(result)


@app.patch(
    "/api/v1/conversations/{conv_id}/feedback",
    tags=["Conversations"],
)
async def conversation_feedback(
    conv_id: UUID,
    payload: ConversationFeedbackRequest,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _coordinator_forward(
        request, "PATCH", f"/api/v1/conversations/{conv_id}/feedback",
        json_body=payload.model_dump(exclude_none=True, by_alias=True),
    )


# ============================================================
# Messages (compat + new)
# ============================================================

@app.get(
    "/api/v1/conversations/{conv_id}/messages",
    response_model=list[MessageOut],
    tags=["Messages"],
)
async def list_messages(
    conv_id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _coordinator_forward(
        request, "GET", f"/api/v1/conversations/{conv_id}/messages",
        params={"limit": limit, "offset": offset},
    )


@app.post(
    "/api/v1/conversations/{conv_id}/messages",
    response_model=MessageOut,
    tags=["Messages"],
    summary="Send message (legacy alias for /assistant/chat)",
    description=(
        "Legacy endpoint. Preserved for backward compatibility. "
        "Internally forwarded to /api/v1/assistant/chat on the Coordinator. "
        "New clients should use POST /api/v1/assistant/chat directly."
    ),
)
async def send_message_legacy(
    conv_id: UUID,
    payload: SendMessageRequest,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
):
    """Legacy: forward to Coordinator as a regular chat, then normalize the response
    into the legacy MessageOut shape so old clients keep working unchanged."""
    _check_api_key(x_api_key)
    if authorization and not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"code": "invalid_authorization_scheme"})

    # Build a Coordinator ChatRequest. tenantId/userId are optional in legacy;
    # if missing, we forward None and the Coordinator will reject with a clear error.
    chat_payload: dict[str, Any] = {
        "appId": "",  # filled below after resolving conversation
        "tenantId": payload.tenantId or "",
        "userId": payload.userId or "",
        "prompt": payload.prompt,
        "conversationId": str(conv_id),
    }

    # Resolve appId from the existing conversation (needed by Coordinator's ChatRequest).
    try:
        conv = await _rag_forward(
            request, "GET", f"/api/v1/conversations/{conv_id}",
            params={"tenantId": payload.tenantId} if payload.tenantId else None,
        )
    except HTTPException:
        raise

    # Accept both migrated (`app_ids`/`appIds`) and legacy (`app_id`/`appId`) shapes.
    conv_app_ids: list[str] = []
    raw_ids = conv.get("app_ids") or conv.get("appIds")
    if isinstance(raw_ids, list):
        conv_app_ids = [v for v in raw_ids if isinstance(v, str) and v.strip()]
    elif isinstance(raw_ids, str) and raw_ids.strip():
        conv_app_ids = [raw_ids]
    if not conv_app_ids:
        single = conv.get("app_id") or conv.get("appId")
        if isinstance(single, str) and single.strip():
            conv_app_ids = [single]

    chat_payload["appId"] = conv_app_ids[0] if conv_app_ids else ""
    if not chat_payload["tenantId"] and conv.get("tenant_id"):
        chat_payload["tenantId"] = conv["tenant_id"]
    if not chat_payload["userId"] and conv.get("user_id"):
        chat_payload["userId"] = conv["user_id"]

    if not chat_payload["appId"] or not chat_payload["tenantId"] or not chat_payload["userId"]:
        raise HTTPException(
            status_code=422,
            detail={"code": "missing_required_context",
                    "message": "appId/tenantId/userId must be provided or resolvable from the conversation."},
        )

    chat_response = await _coordinator_forward(
        request, "POST", "/api/v1/assistant/chat",
        json_body=chat_payload,
        forward_auth=authorization,
    )

    # Normalize ChatResponse -> MessageOut for legacy clients.
    # Legacy MessageOut fields: id, conv_id, query, answer, duration,
    # error, meta_info, liked, created_at, role, content.
    message_id = chat_response.get("messageId") or chat_response.get("requestId")
    answer = chat_response.get("answer")
    selected = chat_response.get("selectedPath")
    sources = chat_response.get("sources") or []
    meta_info = {
        "status": chat_response.get("status", "completed"),
        "selectedPath": selected,
        "sources": sources,
    }
    # If clarification or approval, surface them via meta_info so legacy UI still
    # has something to show (answer already contains the human-readable text).
    if chat_response.get("clarification"):
        meta_info["clarification"] = chat_response["clarification"]
    if chat_response.get("approvalId"):
        meta_info["approvalId"] = chat_response["approvalId"]
        meta_info["approvalExpiresAt"] = chat_response.get("approvalExpiresAt")

    return {
        "id": message_id,
        "conversation_id": chat_response.get("conversationId") or str(conv_id),
        "query": payload.prompt,
        "answer": answer,
        "duration": None,
        "error": None,
        "meta_info": meta_info,
        "liked": None,
        "created_at": None,  # RAG will fill on GET /messages
        "role": None,
        "content": None,
    }


@app.patch(
    "/api/v1/conversations/{conv_id}/messages/{message_id}/liked",
    response_model=MessageOut,
    tags=["Messages"],
)
async def message_liked(
    conv_id: UUID,
    message_id: UUID,
    payload: MessageLikeRequest,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _coordinator_forward(
        request, "PATCH",
        f"/api/v1/conversations/{conv_id}/messages/{message_id}/liked",
        json_body=payload.model_dump(exclude_none=True, by_alias=True),
    )


# ---------------------------------------------------------
# Approval proxies (to Coordinator)
# ---------------------------------------------------------

@app.get("/api/v1/erp/approvals/{approval_id}", tags=["ERP Approvals"])
async def get_erp_approval(
    approval_id: UUID,
    request: Request,
    tenant_id: str = Query(alias="tenantId", min_length=1, max_length=100),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _coordinator_forward(
        request, "GET", f"/api/v1/erp/approvals/{approval_id}",
        params={"tenantId": tenant_id},
        include_approval_key=True,
    )


@app.post("/api/v1/erp/approvals/{approval_id}/approve", tags=["ERP Approvals"])
async def approve_erp_operation(
    approval_id: UUID,
    payload: ApprovalActionRequest,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"code": "approver_bearer_token_required"})
    return await _coordinator_forward(
        request, "POST", f"/api/v1/erp/approvals/{approval_id}/approve",
        json_body=payload.model_dump(exclude_none=True, by_alias=True),
        forward_auth=authorization,
        include_approval_key=True,
    )


@app.post("/api/v1/erp/approvals/{approval_id}/reject", tags=["ERP Approvals"])
async def reject_erp_operation(
    approval_id: UUID,
    payload: ApprovalActionRequest,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
):
    _check_api_key(x_api_key)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"code": "approver_bearer_token_required"})
    return await _coordinator_forward(
        request, "POST", f"/api/v1/erp/approvals/{approval_id}/reject",
        json_body=payload.model_dump(exclude_none=True, by_alias=True),
        forward_auth=authorization,
        include_approval_key=True,
    )


# ============================================================
# Documents management proxies (to RAG, direct + with response_model + descriptions)
# ============================================================

@app.get(
    "/api/v1/documents",
    response_model=list[DocumentOut],
    tags=["Documents"],
)
async def list_documents(
    request: Request,
    app_id: str | None = Query(default=None, alias="appId", max_length=100),
    department: str | None = Query(default=None, max_length=100),
    include_all_versions: bool = Query(default=False, alias="includeAllVersions"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    params: dict[str, Any] = {"includeAllVersions": include_all_versions}
    if app_id:
        params["appId"] = app_id
    if department:
        params["department"] = department
    return await _rag_forward(request, "GET", "/api/v1/documents", params=params)


@app.get(
    "/api/v1/documents/app-ids",
    response_model=list[str],
    tags=["Documents"],
)
async def list_document_app_ids(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _rag_forward(request, "GET", "/api/v1/documents/app-ids")


@app.get(
    "/api/v1/documents/by-logical/{logical_doc_id}/versions",
    response_model=list[DocumentVersionItem],
    tags=["Documents"],
)
async def list_document_versions(
    logical_doc_id: UUID,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _rag_forward(
        request, "GET",
        f"/api/v1/documents/by-logical/{logical_doc_id}/versions",
    )


@app.post(
    "/api/v1/documents/create",
    tags=["Documents"],
    summary="Upload a PDF or DOCX document",
    description="Uploads a file, extracts text, chunks it, and indexes it in Qdrant. Creates a new version if the doc already exists.",
)
async def create_document_file(
    request: Request,
    file: UploadFile = File(...),
    doc_name: str = Form(..., alias="docName"),
    doc_type: str = Form(..., alias="docType"),
    department: str = Form(...),
    app_id: str = Form(..., alias="appId"),
    metadata: str | None = Form(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)

    # Stream the upload to RAG without buffering the whole file in memory.
    async def file_stream():
        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            yield chunk

    files = {"file": (file.filename, file_stream(), file.content_type)}
    form_data: dict[str, Any] = {
        "docName": doc_name,
        "docType": doc_type,
        "department": department,
        "appId": app_id,
    }
    if metadata is not None:
        form_data["metadata"] = metadata

    return await _rag_forward(
        request, "POST", "/api/v1/documents/create",
        files=files, data=form_data,
    )


@app.post(
    "/api/v1/documents/create-text",
    tags=["Documents"],
    summary="Replace all text documents of an app (atomic)",
    description=(
        "Replaces all text documents of an app_id in a single batch. "
        "If any document fails, none are committed (all-or-nothing). "
        "For per-document upsert/versioning, use /create-text2."
    ),
)
async def create_text_documents_replace(
    payload: TextDocumentsRequest,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _rag_forward(
        request, "POST", "/api/v1/documents/create-text",
        json_body=payload.model_dump(exclude_none=True, by_alias=True),
    )


@app.post(
    "/api/v1/documents/create-text2",
    tags=["Documents"],
    summary="Upsert text documents (per-document commit)",
    description=(
        "Upserts text documents with per-document commit/rollback. "
        "A failure in one document does not block the others. "
        "Creates a new version if the doc already exists (based on content hash)."
    ),
)
async def create_text_documents_upsert(
    payload: TextDocumentsRequest,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _rag_forward(
        request, "POST", "/api/v1/documents/create-text2",
        json_body=payload.model_dump(exclude_none=True, by_alias=True),
    )


@app.delete(
    "/api/v1/documents/by-logical/{logical_doc_id}",
    tags=["Documents"],
    summary="Delete versions of a logical document",
    description=(
        "Deletes versions of a logical document. "
        "allVersions=False: only current, previous becomes current. "
        "allVersions=True: all versions from Postgres and Qdrant."
    ),
)
async def delete_documents_by_logical_id(
    logical_doc_id: UUID,
    request: Request,
    all_versions: bool = Query(default=False, alias="allVersions"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _rag_forward(
        request, "DELETE",
        f"/api/v1/documents/by-logical/{logical_doc_id}",
        params={"allVersions": all_versions},
    )


@app.delete(
    "/api/v1/documents/by-app/{app_id}",
    tags=["Documents"],
    summary="Delete all documents of an app",
)
async def delete_documents_by_app(
    app_id: str,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _rag_forward(
        request, "DELETE", f"/api/v1/documents/by-app/{app_id}",
    )


@app.delete(
    "/api/v1/documents/{document_id}",
    tags=["Documents"],
    summary="Delete a specific document version",
    description="If this was the current version, the previous version becomes current.",
)
async def delete_document(
    document_id: UUID,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _rag_forward(
        request, "DELETE", f"/api/v1/documents/{document_id}",
    )
# 01. imports
# 02. env constants
# 03. schemas (ChatRequest, ApprovalActionRequest)
# 04. lifespan
# 05. app = FastAPI(...)
# 06. auth helpers (_check_api_key, _coordinator_headers)
# 07. forward helpers (_coordinator_forward, _rag_forward)
# 08. health()
# 09. chat() non-stream
# 10. SSE helper (_stream_coordinator)
# 11. chat_stream()
# 12. conversation proxies (6 endpoints)
# 13. approval proxies (3 endpoints)
# 14. document proxies (9 endpoints)

