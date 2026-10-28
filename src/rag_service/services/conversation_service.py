# src/rag_service/services/conversation_service.py
import logging
import uuid
from datetime import datetime
from typing import Optional, List, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session

from core.config import settings
from core.database import Conversation, Message
from core.message_broker import MessageBroker, build_message_payload
from core.redis_client import ConversationCache, get_redis_client

logger = logging.getLogger(__name__)

# پیشوندی که در تاریخچه چت به پاسخ‌های liked=True می‌چسبد
APPROVED_ANSWER_PREFIX = "[پاسخ تأییدشده توسط کاربر] "


def _safe_redis_client():
    try:
        return get_redis_client()
    except Exception as exc:
        logger.warning("Redis client unavailable: %s", exc)
        return None


class ConversationService:

    # ---------- Conversation CRUD ----------

    @staticmethod
    def create_conversation(
        db: Session,
        app_id: str,
        tenant_id: str,
        user_id: str,
        title: Optional[str] = None,
        user_name: Optional[str] = None,
        tenant_desc: Optional[str] = None,
    ) -> Conversation:
        conv = Conversation(
            id=uuid.uuid4(),
            app_id=app_id.strip(),
            tenant_id=tenant_id,
            user_id=user_id,
            user_name=user_name,
            tenant_desc=tenant_desc,
            title=title or "گفتگوی جدید",
            status="active",
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

        redis_client = _safe_redis_client()
        if redis_client is not None:
            try:
                ConversationCache.create_conversation(
                    redis_client,
                    str(conv.id),
                    app_id=conv.app_id,
                    tenant_id=conv.tenant_id,
                    user_id=conv.user_id,
                    user_name=conv.user_name,
                    tenant_desc=conv.tenant_desc,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to cache conversation meta %s: %s", conv.id, exc
                )

        return conv

    @staticmethod
    def get_conversation(
        db: Session,
        conv_id: uuid.UUID,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Optional[Conversation]:
        query = db.query(Conversation).filter(Conversation.id == conv_id)
        if tenant_id:
            query = query.filter(Conversation.tenant_id == tenant_id)
        if user_id:
            query = query.filter(Conversation.user_id == user_id)
        return query.first()

    @staticmethod
    def list_conversations(
        db: Session,
        tenant_id: str,
        user_id: str,
        app_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Conversation]:
        q = db.query(Conversation).filter(
            Conversation.tenant_id == tenant_id,
            Conversation.user_id == user_id,
        )
        if app_id:
            q = q.filter(Conversation.app_id == app_id)

        return (
            q.order_by(desc(Conversation.updated_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

    @staticmethod
    def update_conversation(
        db: Session,
        conv: Conversation,
        title: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Conversation:
        if title is not None:
            conv.title = title
        if status is not None:
            conv.status = status
            if status == "closed":
                conv.ended_at = datetime.utcnow()
        conv.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(conv)
        return conv

    # ---------- Turns ----------

    @staticmethod
    def add_query(
        db: Session,
        conversation_id: uuid.UUID,
        query: str,
        redis_client=None,
    ) -> Message:
        """
        ثبت prompt کاربر. یک ردیف جدید با query پر و answer خالی ساخته می‌شود.
        هیچ رویدادی به RabbitMQ ارسال نمی‌شود تا زمانی که پاسخ آماده شود.
        """
        msg = Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            query=query,
            answer=None,
        )
        db.add(msg)

        conv = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )
        if conv:
            conv.updated_at = datetime.utcnow()
            if conv.title == "گفتگوی جدید" or not conv.title:
                conv.title = query[:60] + ("..." if len(query) > 60 else "")

        db.commit()
        db.refresh(msg)

        if redis_client is None:
            redis_client = _safe_redis_client()

        if redis_client is not None:
            try:
                ConversationCache.upsert_turn(
                    redis_client,
                    str(conversation_id),
                    message_id=str(msg.id),
                    query=query,
                    created_at=msg.created_at.isoformat(),
                )
            except Exception as exc:
                logger.warning(
                    "Failed to cache query turn %s: %s", msg.id, exc
                )

        return msg

    @staticmethod
    def complete_turn(
        db: Session,
        message_id: uuid.UUID,
        answer: str,
        duration: Optional[float],
        error: Optional[str] = None,
        meta_info: Optional[dict] = None,
        redis_client=None,
    ) -> Message:
        """
        به‌روزرسانی ردیف turn با answer و انتشار رویداد به RabbitMQ.
        """
        msg = db.query(Message).filter(Message.id == message_id).first()
        if not msg:
            raise ValueError(f"Message {message_id} not found")

        msg.answer = answer
        msg.duration = duration
        msg.error = error
        msg.meta_info = meta_info

        conv = (
            db.query(Conversation)
            .filter(Conversation.id == msg.conversation_id)
            .first()
        )
        if conv:
            conv.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(msg)

        if redis_client is None:
            redis_client = _safe_redis_client()

        if redis_client is not None:
            try:
                ConversationCache.upsert_turn(
                    redis_client,
                    str(msg.conversation_id),
                    message_id=str(msg.id),
                    query=msg.query,
                    answer=answer,
                    duration=duration,
                    error=error,
                    meta_info=meta_info,
                    created_at=msg.created_at.isoformat(),
                )
            except Exception as exc:
                logger.warning(
                    "Failed to update cached turn %s: %s", msg.id, exc
                )

        # انتشار رویداد تکمیل turn به RabbitMQ (best-effort)
        if settings.rabbitmq_enabled:
            try:
                payload = build_message_payload(
                    message_id=str(msg.id),
                    conversation_id=str(msg.conversation_id),
                    tenant_id=conv.tenant_id if conv else None,
                    tenant_desc=conv.tenant_desc if conv else None,
                    user_id=conv.user_id if conv else None,
                    user_name=conv.user_name if conv else None,
                    app_id=conv.app_id if conv else None,
                    query=msg.query or "",
                    answer=answer,
                    duration=duration,
                    error=error,
                    meta_info=meta_info,
                    created_at=msg.created_at,
                )
                MessageBroker.publish_message_event(payload)
            except Exception as exc:
                logger.warning(
                    "Failed to publish turn event for %s: %s", msg.id, exc
                )

        return msg

    @staticmethod
    def get_messages(
        db: Session,
        conversation_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Message]:
        return (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_recent_chat_history(
        db: Session,
        conversation_id: uuid.UUID,
        max_turns: int = settings.chat_history_max_turns,
        redis_client=None,
        exclude_disliked: bool = True,
    ) -> List[Tuple[str, str]]:
        """
        آخرین `max_turns` نوبت را به ترتیب زمانی برمی‌گرداند.

        رفتار بر اساس `liked`:
          - liked=False (و exclude_disliked=True): نوبت از تاریخچه حذف می‌شود.
            دلیل: تکرار پاسخ بد، مدل را به سمت پاسخ اشتباه هدایت می‌کند.
          - liked=True: پاسخ با پیشوند APPROVED_ANSWER_PREFIX نشانه‌گذاری می‌شود
            تا مدل بداند پاسخ تأییدشده است.
          - liked=None: رفتار عادی (بدون پیشوند).

        استراتژی:
          ۱. تلاش از Redis
          ۲. Fallback به Postgres + repopulate Redis
        """
        if redis_client is None:
            redis_client = _safe_redis_client()

        turns: List[dict] = []

        # ۱. تلاش از Redis
        if redis_client is not None:
            try:
                turns = ConversationCache.get_recent_turns(
                    redis_client, str(conversation_id), max_turns
                )
            except Exception as exc:
                logger.warning(
                    "Redis turns read failed for %s: %s", conversation_id, exc
                )
                turns = []

        # ۲. Fallback به Postgres
        if not turns:
            recent = (
                db.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(desc(Message.created_at))
                .limit(max_turns)
                .all()
            )
            turns = [
                {
                    "message_id": str(m.id),
                    "query": m.query,
                    "answer": m.answer,
                    "duration": m.duration,
                    "error": m.error,
                    "meta_info": m.meta_info or {},
                    "liked": m.liked,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in reversed(recent)
            ]

            # ۳. Repopulate Redis
            if redis_client is not None and turns:
                try:
                    ConversationCache.set_turns(
                        redis_client, str(conversation_id), turns
                    )
                except Exception as exc:
                    logger.warning(
                        "Redis turns repopulate failed for %s: %s",
                        conversation_id,
                        exc,
                    )

        # تبدیل turn ها به پیام‌های (role, content) با احترام به liked
        history: List[Tuple[str, str]] = []
        for t in turns:
            liked = t.get("liked")

            # فیلتر: نوبت‌های disliked از تاریخچه حذف می‌شوند
            if exclude_disliked and liked is False:
                continue

            if t.get("query"):
                history.append(("user", t["query"]))

            if t.get("answer"):
                if liked is True:
                    content = APPROVED_ANSWER_PREFIX + t["answer"]
                else:
                    content = t["answer"]
                history.append(("assistant", content))

        return history

    @staticmethod
    def set_message_like(
        db: Session,
        message_id: uuid.UUID,
        like_value: bool,
    ) -> Optional[Message]:
        msg = db.query(Message).filter(Message.id == message_id).first()
        if not msg:
            return None
        msg.liked = like_value
        db.commit()
        db.refresh(msg)

        # به‌روزرسانی Redis تا liked در تاریخچه بعدی دیده شود.
        redis_client = _safe_redis_client()
        if redis_client is not None:
            try:
                ConversationCache.upsert_turn(
                    redis_client,
                    str(msg.conversation_id),
                    message_id=str(msg.id),
                    liked=like_value,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to update cached liked for message %s: %s",
                    msg.id,
                    exc,
                )

        if settings.rabbitmq_enabled:
            try:
                from core.message_broker import MessageBroker, build_message_row_payload
                conv = (
                    db.query(Conversation)
                    .filter(Conversation.id == msg.conversation_id)
                    .first()
                )
                MessageBroker.publish_to_queue(
                    "like_queue",
                    build_message_row_payload(
                        msg, app_id=conv.app_id if conv else None
                    ),
                )
            except Exception as exc:
                logger.warning(
                    "Failed to publish like event for message %s: %s",
                    msg.id,
                    exc,
                )

        return msg

    @staticmethod
    def set_conversation_feedback(
        db: Session,
        conv_id: uuid.UUID,
        feedback_score: int,
    ) -> Optional[Conversation]:
        conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
        if not conv:
            return None
        conv.feedback_score = feedback_score
        conv.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(conv)

        if settings.rabbitmq_enabled:
            try:
                from core.message_broker import (
                    MessageBroker,
                    build_conversation_row_payload,
                )
                MessageBroker.publish_to_queue(
                    "conv_feedback",
                    build_conversation_row_payload(conv),
                )
            except Exception as exc:
                logger.warning(
                    "Failed to publish conv feedback for conversation %s: %s",
                    conv.id,
                    exc,
                )

        return conv