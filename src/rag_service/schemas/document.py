# src/rag_service/schemas/document.py
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentOut(BaseModel):
    id: uuid.UUID
    logicalDocId: uuid.UUID
    version: int
    isCurrent: bool
    previousVersionId: Optional[uuid.UUID] = None
    contentHash: Optional[str] = None

    docName: str
    docType: str
    department: str
    appId: str
    metadata: Optional[Dict[str, Any]] = None
    chunksCount: int
    createdAt: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentVersionItem(BaseModel):
    id: uuid.UUID
    version: int
    isCurrent: bool
    contentHash: Optional[str] = None
    chunksCount: int
    createdAt: datetime
    previousVersionId: Optional[uuid.UUID] = None

    model_config = ConfigDict(from_attributes=True)

