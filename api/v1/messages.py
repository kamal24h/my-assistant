# api/v1/messages.py
import time
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from config import settings

from database import Message, get_db

from services.conversation_service import ConversationService
from services.rag_service import generate_rag_response
from coordinator.guardrails import guard_output
from schemas.conversation import (
    MessageOut,
    SendMessageRequest,
    MessageLikeRequest,
)

router = APIRouter(
    prefix="/api/v1/conversations/{conv_id}/messages",
    tags=["Messages"],
)


@router.get("", response_model=List[MessageOut])
def list_messages(
    conv_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return ConversationService.get_messages(
        db,
        conversation_id=conv_id,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=MessageOut)
def send_message(
    conv_id: uuid.UUID,
    req: SendMessageRequest,
    db: Session = Depends(get_db),
):
    conv = ConversationService.get_conversation(
        db, conv_id, tenant_id=req.tenantId, user_id=req.userId
    )
    if not conv:
        raise HTTPException(status_code=404, detail="مکالمه یافت نشد.")
    if conv.status != "active":
        raise HTTPException(status_code=400, detail="این مکالمه فعال نیست.")

    # ۱. خواندن تاریخچه (۵ نوبت آخر)
    history = ConversationService.get_recent_chat_history(
        db,
        conversation_id=conv_id,
        max_turns=settings.chat_history_max_turns,
    )

    # ۲. ثبت prompt کاربر (یک ردیف با query و answer خالی)
    turn = ConversationService.add_query(
        db=db,
        conversation_id=conv_id,
        query=req.prompt,
    )

    # ۳. تولید پاسخ با RAG (اندازه‌گیری زمان)
    started_at = time.perf_counter()
    try:
        answer, sources, form_id = generate_rag_response(
            question=req.prompt,
            app_id=conv.app_id,
            chat_history=history,
        )
        answer, _guardrail_flags = guard_output(answer)
        duration = time.perf_counter() - started_at

        # ۴. به‌روزرسانی همان ردیف با answer + انتشار رویداد
        completed = ConversationService.complete_turn(
            db=db,
            message_id=turn.id,
            answer=answer,
            duration=duration,
            error=None,
            meta_info={"sources": sources or [], "status": "completed", "formId": form_id},
        )
        return completed

    except Exception as e:
        duration = time.perf_counter() - started_at
        error_text = str(e)

        ConversationService.complete_turn(
            db=db,
            message_id=turn.id,
            answer="متأسفانه در تولید پاسخ مشکلی رخ داد.",
            duration=duration,
            error=error_text,
            meta_info={"status": "failed"},
        )
        raise HTTPException(
            status_code=500,
            detail=f"خطا در پردازش هوش مصنوعی: {error_text}",
        )


@router.patch("/{message_id}/liked", response_model=MessageOut)
def like_message(
    conv_id: uuid.UUID,
    message_id: uuid.UUID,
    req: MessageLikeRequest,
    db: Session = Depends(get_db),
):
    # چک می‌کنیم پیام به این مکالمه تعلق داشته باشد
    msg = (
        db.query(Message)
        .filter(Message.id == message_id, Message.conversation_id == conv_id)
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="پیام یافت نشد.")
    updated = ConversationService.set_message_like(db, message_id, req.liked)
    return updated   