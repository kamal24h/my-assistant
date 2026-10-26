"""Internal endpoint for persisting answers generated outside the RAG pipeline."""
import time
import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session
from core.database import get_db
from core.security import require_api_key
from services.conversation_service import ConversationService
from schemas.conversation import MessageOut

router = APIRouter(prefix="/api/v1/conversations/{conv_id}", tags=["Assistant persistence"])

class AssistantTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=12000)
    answer: str = Field(min_length=1, max_length=30000)
    tenantId: str = Field(min_length=1, max_length=100)
    userId: str = Field(min_length=1, max_length=200)
    selectedPath: str = Field(pattern=r"^(local_llm|local_mcp)$")
    sources: list[dict[str, Any]] = Field(default_factory=list)
    duration: float = Field(ge=0)

@router.post("/assistant-turn", response_model=MessageOut, dependencies=[Depends(require_api_key)])
def save_assistant_turn(conv_id: uuid.UUID, req: AssistantTurnRequest, db: Session = Depends(get_db)):
    conv = ConversationService.get_conversation(db, conv_id, tenant_id=req.tenantId, user_id=req.userId)
    if not conv:
        raise HTTPException(status_code=404, detail="مکالمه یافت نشد.")
    if conv.status != "active":
        raise HTTPException(status_code=400, detail="این مکالمه فعال نیست.")
    turn = ConversationService.add_query(db=db, conversation_id=conv_id, query=req.prompt)
    return ConversationService.complete_turn(
        db=db, message_id=turn.id, answer=req.answer, duration=req.duration,
        error=None, meta_info={"status": "completed", "selectedPath": req.selectedPath, "sources": req.sources},
    )
