"""
SQLAlchemy models for chat sessions, messages, and resource state.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
import enum

from app.models.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ResourceStatus(str, enum.Enum):
    COLLECTING = "collecting"          # Still collecting fields
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # YAML shown, waiting for user
    CONFIRMED = "confirmed"            # User confirmed
    CANCELLED = "cancelled"            # User cancelled this resource


class ChatSession(Base):
    """Represents a conversation session. One per GitHub user (WhatsApp-style)."""
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True, default=generate_uuid)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    status = Column(SQLEnum(SessionStatus), default=SessionStatus.ACTIVE)
    github_token = Column(String, nullable=True)
    github_username = Column(String, nullable=True, index=True)
    created_by = Column(String, nullable=True)  # Kept for backward compat; use github_username
    conversation_summary = Column(Text, nullable=True)  # Rolling LLM summary of older messages

    # Relationships
    messages = relationship("ChatMessage", back_populates="session", order_by="ChatMessage.created_at")
    resources = relationship("ResourceState", back_populates="session")


class ChatMessage(Base):
    """Stores individual chat messages."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(SQLEnum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Metadata for tracking what the agent did
    metadata_json = Column(JSON, nullable=True)  # e.g., extracted fields, validation errors

    # Relationships
    session = relationship("ChatSession", back_populates="messages")


class ResourceState(Base):
    """
    Tracks the state of a resource being built in a session.
    One session can have multiple resources (built sequentially).
    """
    __tablename__ = "resource_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False)
    resource_type = Column(String, nullable=False)  # e.g., "s3", "glue_db", "iam"
    status = Column(SQLEnum(ResourceStatus), default=ResourceStatus.COLLECTING)
    collected_fields = Column(JSON, default=dict)  # Fields collected so far
    generated_yaml = Column(Text, nullable=True)    # Final YAML output
    validation_errors = Column(JSON, nullable=True)  # Any validation errors
    current_field = Column(String, nullable=True)    # Field currently being asked about
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    pr_url = Column(String, nullable=True)

    # Relationships
    session = relationship("ChatSession", back_populates="resources")


class PRRecord(Base):
    """Tracks PRs created by the chatbot for status tracking."""
    __tablename__ = "pr_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False)
    github_username = Column(String, nullable=False, index=True)
    pr_url = Column(String, nullable=False)
    pr_number = Column(Integer, nullable=True)
    repo_full_name = Column(String, nullable=False)  # "owner/repo"
    branch_name = Column(String, nullable=True)
    target_branch = Column(String, nullable=True)
    resource_types = Column(JSON, nullable=True)  # ["s3", "glue_db"]
    resource_count = Column(Integer, default=1)
    title = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    session = relationship("ChatSession", backref="pr_records")
