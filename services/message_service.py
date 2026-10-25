# services/message_service.py

import uuid

from typing import List

from sqlalchemy.orm import Session

from database import Message


class MessageService:

    @staticmethod
    def create_message(
        db: Session,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
    ) -> Message:

        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
        )

        db.add(message)

        return message

    @staticmethod
    def get_messages(
        db: Session,
        conversation_id: uuid.UUID,
    ) -> List[Message]:

        return (
            db.query(Message)
            .filter(
                Message.conversation_id == conversation_id
            )
            .order_by(Message.created_at.asc())
            .all()
        )

    @staticmethod
    def archive_redis_messages(
        db: Session,
        conversation_id: uuid.UUID,
        cached_messages: list,
    ) -> int:

        count = 0

        for item in cached_messages:

            role = item.get("role")
            content = item.get("content")

            if not role or content is None:
                continue

            MessageService.create_message(
                db=db,
                conversation_id=conversation_id,
                role=role,
                content=content,
            )

            count += 1

        return count

    