# src/assistant_api/app/main.py

"""Public Python/FastAPI gateway for ERP Smart Assistant.

Architecture (final):
  - Client talks ONLY to this service.
  - Chat/stream/approvals/conversations -> Coordinator (internal).
  - Documents -> RAG (internal, direct).
  - Coordinator, RAG, LLM, MCP are NOT exposed outside the assistant_network.

Authentication model:
  - Client authenticates with X-API-Key (ASSISTANT_API_KEY).
  - End-user SSO token is forwarded as Authorization: Bearer for MCP/approval.
  - Service-to-service credentials (APPROVAL_API_KEY) are added by this
    gateway only when calling Coordinator approval endpoints.
"""
from __future__ import annotations

import hmac
import json
import os
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID
import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

COORDINATOR_URL = os.getenv("COORDINATOR_URL", "http://coordinator:8001").rstrip("/")
RAG_API_URL = os.getenv("RAG_API_URL", "http://fastapi:8000").rstrip("/")
ASSISTANT_API_KEY = os.getenv("ASSISTANT_API_KEY", "").strip()
APPROVAL_API_KEY = os.getenv("APPROVAL_API_KEY", "").strip()
REQUEST_TIMEOUT = float(os.getenv("ASSISTANT_API_TIMEOUT_SECONDS", "90"))


# ---------------------------------------------------------
# Schemas
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(REQUEST_TIMEOUT))
    yield
    await app.state.http.aclose()


app = FastAPI(
    title="ERP Smart Assistant API",
    description=(
        "Public entry point for ERP Smart Assistant. "
        "Chat, streaming, conversations, and approvals are forwarded to the Coordinator. "
        "Document management is forwarded directly to the RAG service."
    ),
    version="1.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# Forward helper
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# Health
# ---------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "assistant-api",
        "coordinator": COORDINATOR_URL,
        "rag": RAG_API_URL,
    }


# ---------------------------------------------------------
# Chat (non-stream) — passthrough to Coordinator
# ---------------------------------------------------------

@app.post("/api/v1/assistant/chat")
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
# SSE Streaming — forward to Coordinator (C5 - placeholder)
# ---------------------------------------------------------
# (implemented in C5; not included in C3)


# ---------------------------------------------------------
# Conversation proxies (to Coordinator)
# ---------------------------------------------------------

@app.get("/api/v1/conversations")
async def list_conversations(
    request: Request,
    tenant_id: str = Query(alias="tenantId", min_length=1, max_length=100),
    user_id: str = Query(alias="userId", min_length=1, max_length=200),
    app_id: str | None = Query(default=None, alias="appId", max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    params: dict[str, Any] = {
        "tenantId": tenant_id, "userId": user_id,
        "limit": limit, "offset": offset,
    }
    if app_id:
        params["appId"] = app_id
    return await _coordinator_forward(
        request, "GET", "/api/v1/conversations", params=params,
    )


@app.get("/api/v1/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: UUID,
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
    return await _coordinator_forward(
        request, "GET", f"/api/v1/conversations/{conversation_id}",
        params=params or None,
    )


@app.get("/api/v1/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _coordinator_forward(
        request, "GET", f"/api/v1/conversations/{conversation_id}/messages",
        params={"limit": limit, "offset": offset},
    )


@app.patch("/api/v1/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: UUID,
    body: dict[str, Any],
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _coordinator_forward(
        request, "PATCH", f"/api/v1/conversations/{conversation_id}",
        json_body=body,
    )


@app.patch("/api/v1/conversations/{conversation_id}/feedback")
async def conversation_feedback(
    conversation_id: UUID,
    body: dict[str, Any],
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _coordinator_forward(
        request, "PATCH", f"/api/v1/conversations/{conversation_id}/feedback",
        json_body=body,
    )


@app.patch("/api/v1/conversations/{conversation_id}/messages/{message_id}/liked")
async def message_liked(
    conversation_id: UUID,
    message_id: UUID,
    body: dict[str, Any],
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _coordinator_forward(
        request, "PATCH",
        f"/api/v1/conversations/{conversation_id}/messages/{message_id}/liked",
        json_body=body,
    )


# ---------------------------------------------------------
# Approval proxies (to Coordinator)
# ---------------------------------------------------------

@app.get("/api/v1/erp/approvals/{approval_id}")
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


@app.post("/api/v1/erp/approvals/{approval_id}/approve")
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


@app.post("/api/v1/erp/approvals/{approval_id}/reject")
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


# ---------------------------------------------------------
# RAG forward helper (for document management only)
# ---------------------------------------------------------

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
    """Forward a request to RAG and normalize errors.

    Used ONLY for document management. Chat / conversations / approvals
    always go through the Coordinator.
    """
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


# ---------------------------------------------------------
# Document management proxies (to RAG, direct)
# ---------------------------------------------------------

@app.get("/api/v1/documents")
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


@app.get("/api/v1/documents/app-ids")
async def list_document_app_ids(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _rag_forward(request, "GET", "/api/v1/documents/app-ids")


@app.get("/api/v1/documents/by-logical/{logical_doc_id}/versions")
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


@app.post("/api/v1/documents/create")
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


@app.post("/api/v1/documents/create-text")
async def create_text_documents_replace(
    body: dict[str, Any],
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _rag_forward(
        request, "POST", "/api/v1/documents/create-text",
        json_body=body,
    )


@app.post("/api/v1/documents/create-text2")
async def create_text_documents_upsert(
    body: dict[str, Any],
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _rag_forward(
        request, "POST", "/api/v1/documents/create-text2",
        json_body=body,
    )


@app.delete("/api/v1/documents/by-logical/{logical_doc_id}")
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


@app.delete("/api/v1/documents/by-app/{app_id}")
async def delete_documents_by_app(
    app_id: str,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _rag_forward(
        request, "DELETE", f"/api/v1/documents/by-app/{app_id}",
    )


@app.delete("/api/v1/documents/{document_id}")
async def delete_document(
    document_id: UUID,
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)
    return await _rag_forward(
        request, "DELETE", f"/api/v1/documents/{document_id}",
    )