# src/rag_service/schemas/conversation.py
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import (
    BaseModel, ConfigDict, Field, conint, model_validator, AliasChoices,
)


class ConversationCreate(BaseModel):
    appId: Optional[str] = None
    appIds: Optional[List[str]] = None
    tenantId: str
    userId: str
    userName: Optional[str] = None
    tenantDesc: Optional[str] = None
    title: Optional[str] = None

    @model_validator(mode="after")
    def _normalize_app_ids(self):
        ids = self.appIds or ([self.appId] if self.appId else [])
        # حذف تکراری‌ها و مقادیر خالی
        self.appIds = list(dict.fromkeys(x.strip() for x in ids if x and x.strip()))
        if not self.appIds:
            raise ValueError("حداقل یک appId لازم است.")
        return self


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[Literal["active", "closed", "archived"]] = None


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    query: Optional[str] = None
    answer: Optional[str] = None
    duration: Optional[float] = None
    error: Optional[str] = None
    meta_info: Optional[Dict[str, Any]] = None
    liked: Optional[bool] = None
    created_at: datetime

    # برای سازگاری با داده‌های مهاجرت‌شده
    role: Optional[str] = None
    content: Optional[str] = None

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    id: uuid.UUID
    appId: Optional[str] = Field(None, validation_alias=AliasChoices("appId", "app_id"))
    appIds: List[str] = Field(default_factory=list, validation_alias=AliasChoices("appIds", "app_ids"))
    tenant_id: str
    user_id: str
    user_name: Optional[str] = None
    tenant_desc: Optional[str] = None
    title: Optional[str] = None
    status: str
    feedback_score: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    ended_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _fill_app_ids(self):
        if not self.appIds:
            self.appIds = [self.appId] if self.appId else []
        if self.appId is None and self.appIds:
            self.appId = self.appIds[0]
        return self

    class Config:
        from_attributes = True


class ConversationDetailOut(ConversationOut):
    messages: List[MessageOut] = Field(default_factory=list)


class SendMessageRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    tenantId: Optional[str] = None
    userId: Optional[str] = None


class MessageLikeRequest(BaseModel):
    liked: bool


class ConversationFeedbackRequest(BaseModel):
    feedbackScore: int = Field(..., ge=1, le=5)
