
# src/rag_service/api/v1/conversations.py
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
#from core.security import require_api_key
from sqlalchemy.orm import Session

from core.database import get_db
from services.conversation_service import ConversationService
from schemas.conversation import (
    ConversationCreate,
    ConversationUpdate,
    ConversationOut,
    ConversationDetailOut,
    ConversationFeedbackRequest,
)

router = APIRouter(
    prefix="/api/v1/conversations",
    tags=["Conversations"],
    #dependencies=[Depends(require_api_key)],
)

@router.post("", response_model=ConversationOut)
def create_conversation(req: ConversationCreate, db: Session = Depends(get_db)):
    return ConversationService.create_conversation(
        db=db,
        app_id=req.appId,
        tenant_id=req.tenantId,
        user_id=req.userId,
        title=req.title,
        user_name=req.userName,
        tenant_desc=req.tenantDesc,
    )

@router.get("", response_model=List[ConversationOut])
def list_conversations(
    tenantId: str = Query(...),
    userId: str = Query(...),
    appId: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    return ConversationService.list_conversations(
        db=db,
        tenant_id=tenantId,
        user_id=userId,
        app_id=appId,
        limit=limit,
        offset=offset
    )


@router.get("/{conv_id}", response_model=ConversationDetailOut)
def get_conversation(
    conv_id: uuid.UUID,
    tenantId: Optional[str] = Query(None),
    userId: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    conv = ConversationService.get_conversation(db, conv_id, tenant_id=tenantId, user_id=userId)
    if not conv:
        raise HTTPException(status_code=404, detail="مکالمه یافت نشد.")
    return conv


@router.patch("/{conv_id}", response_model=ConversationOut)
def update_conversation(
    conv_id: uuid.UUID,
    req: ConversationUpdate,
    db: Session = Depends(get_db)
):
    conv = ConversationService.get_conversation(db, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="مکالمه یافت نشد.")
    return ConversationService.update_conversation(db, conv, title=req.title, status=req.status)


@router.patch("/{conv_id}/feedback")
def set_conversation_feedback(
    conv_id: uuid.UUID,
    req: ConversationFeedbackRequest,
    db: Session = Depends(get_db),
):
    conv = ConversationService.set_conversation_feedback(
        db, conv_id, req.feedbackScore
    )
    if not conv:
        raise HTTPException(status_code=404, detail="مکالمه یافت نشد.")
    return {"status": "success"}
