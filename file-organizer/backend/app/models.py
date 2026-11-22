from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

FILE_INBOX = "inbox"
FILE_CLASSIFIED = "classified"
FILE_NEEDS_REVIEW = "needs_review"
FILE_ORGANIZED = "organized"
FILE_UNSUPPORTED = "unsupported"
FILE_FAILED = "failed"
FILE_TRASHED = "trashed"

FILE_STATUSES = {
    FILE_INBOX,
    FILE_CLASSIFIED,
    FILE_NEEDS_REVIEW,
    FILE_ORGANIZED,
    FILE_UNSUPPORTED,
    FILE_FAILED,
    FILE_TRASHED,
}

EXTRACTION_PENDING = "pending"
EXTRACTION_READY = "ready"
EXTRACTION_UNSUPPORTED = "unsupported"
EXTRACTION_FAILED = "failed"


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    auto_organize_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_organize_threshold: Mapped[float] = mapped_column(Float, default=0.8)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Folder(Base):
    __tablename__ = "folders"
    __table_args__ = (
        UniqueConstraint("user_id", "parent_id", "name", name="uq_folder_sibling_name"),
        Index("ix_folder_user_parent", "user_id", "parent_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("folders.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        Index("ix_file_user_folder", "user_id", "folder_id"),
        Index("ix_file_user_status", "user_id", "status"),
        Index("ix_file_user_hash", "user_id", "sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    folder_id: Mapped[str] = mapped_column(String(36), ForeignKey("folders.id", ondelete="RESTRICT"))
    original_name: Mapped[str] = mapped_column(String(255))
    current_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default=FILE_INBOX)
    previous_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    extraction_status: Mapped[str] = mapped_column(String(24), default=EXTRACTION_PENDING)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    duplicate_of_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("files.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Classification(Base):
    __tablename__ = "classifications"
    __table_args__ = (Index("ix_classification_file", "file_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("files.id", ondelete="CASCADE"), index=True)
    document_type: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(120))
    subcategory: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    suggested_name: Mapped[str] = mapped_column(String(255))
    suggested_path_json: Mapped[str] = mapped_column(Text, default="[]")
    date_candidates_json: Mapped[str] = mapped_column(Text, default="[]")
    entities_json: Mapped[str] = mapped_column(Text, default="[]")
    confidence: Mapped[float] = mapped_column()
    rationale: Mapped[str] = mapped_column(Text, default="")
    requires_review: Mapped[bool] = mapped_column(Boolean, default=True)
    provider: Mapped[str] = mapped_column(String(80), default="")
    model: Mapped[str] = mapped_column(String(160), default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Operation(Base):
    __tablename__ = "operations"
    __table_args__ = (Index("ix_operation_user", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24), default="organize")
    status: Mapped[str] = mapped_column(String(24), default="applied")
    created_folder_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OperationItem(Base):
    __tablename__ = "operation_items"
    __table_args__ = (Index("ix_operation_item_operation", "operation_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    operation_id: Mapped[str] = mapped_column(String(36), ForeignKey("operations.id", ondelete="CASCADE"))
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("files.id", ondelete="CASCADE"))
    from_folder_id: Mapped[str] = mapped_column(String(36))
    to_folder_id: Mapped[str] = mapped_column(String(36))
    from_name: Mapped[str] = mapped_column(String(255))
    to_name: Mapped[str] = mapped_column(String(255))
    from_path: Mapped[str] = mapped_column(Text)
    to_path: Mapped[str] = mapped_column(Text)
    from_status: Mapped[str] = mapped_column(String(24), default=FILE_INBOX)
    classification_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    previous_classification_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="applied")


class Feedback(Base):
    """User-confirmed decisions used to improve future proposals."""

    __tablename__ = "feedback"
    __table_args__ = (
        Index("ix_feedback_user_type", "user_id", "document_type"),
        Index("ix_feedback_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    file_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("files.id", ondelete="SET NULL"), nullable=True
    )
    decision: Mapped[str] = mapped_column(String(16))
    document_type: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(120), default="")
    subcategory: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    path_json: Mapped[str] = mapped_column(Text, default="[]")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
