"""Public Python/FastAPI gateway for ERP Smart Assistant.

The gateway deliberately delegates orchestration to the existing Coordinator and
keeps document/RAG APIs in the existing rag_service.
"""
from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

COORDINATOR_URL = os.getenv("COORDINATOR_URL", "http://coordinator:8001").rstrip("/")
ASSISTANT_API_KEY = os.getenv("ASSISTANT_API_KEY", "").strip()
REQUEST_TIMEOUT = float(os.getenv("ASSISTANT_API_TIMEOUT_SECONDS", "90"))


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(REQUEST_TIMEOUT))
    yield
    await app.state.http.aclose()


app = FastAPI(
    title="ERP Smart Assistant API",
    description="Python/FastAPI entry point forwarding assistant requests to the LangGraph Coordinator.",
    version="1.0.0",
    lifespan=lifespan,
)


def _check_api_key(provided: str | None) -> None:
    # If configured, the gateway key is mandatory. Leave empty only for trusted
    # private-network deployments where authentication is enforced upstream.
    if ASSISTANT_API_KEY and (not provided or not hmac.compare_digest(provided, ASSISTANT_API_KEY)):
        raise HTTPException(status_code=401, detail={"code": "invalid_api_key"})


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "assistant-api", "coordinator": COORDINATOR_URL}


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

    headers: dict[str, str] = {}
    # Forward the end-user ERP SSO token unchanged; do not replace it with a
    # service credential, because the Coordinator/MCP layer needs user identity.
    if authorization:
        headers["Authorization"] = authorization

    try:
        response = await request.app.state.http.post(
            f"{COORDINATOR_URL}/api/v1/assistant/chat",
            json=payload.model_dump(exclude_none=True, by_alias=True),
            headers=headers,
        )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail={"code": "coordinator_timeout"}) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail={"code": "coordinator_unavailable"}) from exc

    # Preserve Coordinator status codes and structured error bodies.
    try:
        body = response.json()
    except ValueError:
        body = {"detail": "Coordinator returned a non-JSON response."}
    if response.is_error:
        raise HTTPException(status_code=response.status_code, detail=body.get("detail", body))
    return body
