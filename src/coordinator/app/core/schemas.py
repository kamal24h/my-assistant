# src/coordinator/app/core/schemas.py
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    requestId: UUID = Field(default_factory=uuid4)
    conversationId: Optional[UUID] = None
    messageId: Optional[UUID] = None
    appId: str = Field(min_length=1, max_length=100)
    tenantId: str = Field(min_length=1, max_length=100)
    userId: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=12000)
    locale: str = Field(default="fa-IR", max_length=20)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    requestId: UUID
    conversationId: Optional[UUID] = None
    messageId: Optional[UUID] = None
    status: str
    answer: Optional[str] = None
    selectedPath: Optional[str] = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    message: Optional[str] = None
    approvalId: Optional[UUID] = None
    approvalExpiresAt: Optional[str] = None


class ApprovalActionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    tenantId: str = Field(min_length=1, max_length=100)
    approverUserId: str = Field(min_length=1, max_length=200)
    comment: Optional[str] = Field(default=None, max_length=1000)
