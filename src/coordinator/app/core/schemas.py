# src/coordinator/app/core/schemas.py
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    requestId: UUID = Field(default_factory=uuid4)
    conversationId: Optional[UUID] = None
    messageId: Optional[UUID] = None
    appIds: list[str] = Field(min_length=1, max_length=50)
    tenantId: str = Field(min_length=1, max_length=100)
    userId: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=12000)
    locale: str = Field(default="fa-IR", max_length=20)
    metadata: dict[str, Any] = Field(default_factory=dict)

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
    def _promote_legacy_app_id(cls, data):
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "appIds" not in data and "appId" in data:
            legacy = data.get("appId")
            if isinstance(legacy, str) and legacy.strip():
                data["appIds"] = [legacy]
        data.pop("appId", None)
        return data

    # --- دسترسی سازگار برای کدهای موجود ---
    @property
    def app_id(self) -> str:
        """Legacy accessor: first app id (for code paths that still use a single id)."""
        return self.appIds[0] if self.appIds else ""

class ClarificationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    question: str
    missingFields: list[str] = Field(default_factory=list)
    partialContext: dict[str, Any] = Field(default_factory=dict)
    clarificationId: UUID


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
    clarification: Optional[ClarificationRequest] = None


class ApprovalActionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    tenantId: str = Field(min_length=1, max_length=100)
    approverUserId: str = Field(min_length=1, max_length=200)
    comment: Optional[str] = Field(default=None, max_length=1000)