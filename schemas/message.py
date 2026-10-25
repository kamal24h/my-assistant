# schemas/message.py

import uuid

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )