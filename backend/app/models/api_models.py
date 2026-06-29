"""
Pydantic models for API request/response serialization.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ── Request Models ──────────────────────────────────────────

class ChatRequest(BaseModel):
    """Incoming chat message from user. Session resolved by X-GitHub-User header."""
    message: str = Field(..., description="User's message text")
    session_id: Optional[str] = Field(default=None, description="Optional chat session identifier")


# ── Response Models ─────────────────────────────────────────

class QuickOption(BaseModel):
    """A clickable option presented to the user."""
    label: str
    value: str
    description: Optional[str] = None


class ChatResponse(BaseModel):
    """Response from the chatbot."""
    message: str
    session_id: Optional[str] = None
    chat_title: Optional[str] = None
    updated_at: Optional[datetime] = None
    resource_type: Optional[str] = None
    resource_status: Optional[str] = None
    generated_yaml: Optional[str] = None
    needs_confirmation: bool = False
    pr_url: Optional[str] = None
    review_result: Optional[dict] = None
    options: Optional[list[QuickOption]] = None
    options_multi_select: bool = False


class MessageInfo(BaseModel):
    """A single chat message."""
    id: int
    role: str
    content: str
    created_at: datetime
    metadata_json: Optional[dict] = None


class ChatSummaryInfo(BaseModel):
    """Sidebar summary for one chat session."""
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str = "0.2.0"
