from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    documents: Mapped[list["Document"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Document(Base):
    """A document uploaded into a module (category) and available to the AI."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Retained for backward compatibility; all uploads now live in one folder.
    module: Mapped[str] = mapped_column(String(64), default="files", index=True)
    # "upload" = user-uploaded file; "analysis" = saved AI chat response.
    kind: Mapped[str] = mapped_column(String(16), default="upload", index=True)
    title: Mapped[str] = mapped_column(String(255))
    original_name: Mapped[str] = mapped_column(String(255), default="")
    stored_path: Mapped[str] = mapped_column(String(512), default="")
    content_type: Mapped[str] = mapped_column(String(128), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    user: Mapped["User"] = relationship(back_populates="documents")


class ChatMessage(Base):
    """A message in the RAG assistant conversation (per user, per agent)."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    agent_key: Mapped[str] = mapped_column(String(64), default="finance")
    sender: Mapped[str] = mapped_column(String(16), default="user")  # user|assistant
    content: Mapped[str] = mapped_column(Text)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    backend: Mapped[str] = mapped_column(String(32), default="mock")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    user: Mapped["User"] = relationship(back_populates="messages")
