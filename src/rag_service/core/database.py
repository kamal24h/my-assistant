# src/rag_service/core/database.py
import uuid
from datetime import datetime

from sqlalchemy import (
    create_engine, Column, String, DateTime, Text,
    ForeignKey, Integer, Index, Float, Boolean,
)

from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from core.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    logical_doc_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    is_current = Column(Boolean, nullable=False, default=True)
    previous_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    content_hash = Column(String(64), nullable=True)

    doc_name = Column(String(255), nullable=False)
    doc_type = Column(String(50), nullable=False)
    department = Column(String(100), nullable=False, index=True)
    app_id = Column(String(100), nullable=False, index=True)
    meta_info = Column(JSONB, nullable=True)
    chunks_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_documents_logical_current", "logical_doc_id", "is_current"),
        Index("ix_documents_app_current", "app_id", "is_current"),
        Index("ix_documents_app_name_current", "app_id", "doc_name", "is_current"),
    )

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id = Column(String(100), nullable=False)
    tenant_id = Column(String(100), nullable=False)
    user_id = Column(String(100), nullable=False)
    user_name = Column(String(255), nullable=True)
    tenant_desc = Column(String(500), nullable=True)
    title = Column(String(255), nullable=True)
    feedback_score = Column(Integer, nullable=True)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)

    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    __table_args__ = (
        Index("ix_conversations_user_tenant_app", "tenant_id", "user_id", "app_id"),
        Index("ix_conversations_updated_at", "updated_at"),
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ---- ستون‌های جدید: مدل turn-based ----
    query = Column(Text, nullable=True)     # prompt کاربر
    answer = Column(Text, nullable=True)    # پاسخ assistant (در ابتدا null)
    duration = Column(Float, nullable=True) # ثانیه، فقط برای turn کامل‌شده
    error = Column(Text, nullable=True)     # متن خطا در صورت شکست
    meta_info = Column(JSONB, nullable=True)
    liked = Column(Boolean, nullable=True)

    # ---- ستون‌های قدیمی: برای مهاجرت حفظ شده‌اند ----
    role = Column(String(20), nullable=True)
    content = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    conversation = relationship("Conversation", back_populates="messages")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()