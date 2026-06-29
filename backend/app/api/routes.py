"""
API Routes — Chat, History, Health, Schemas, PR Creation

All chat endpoints require authentication via X-GitHub-User header.
Single session per GitHub user (WhatsApp-style).

Endpoints:
- POST /chat             — Send a message, get a response
- GET  /chat/history     — Get chat history for authenticated user
- DELETE /chat/history   — Clear conversation (escape hatch)
- POST /chat/create-pr   — Manually trigger PR creation
- GET  /health           — Health check
- GET  /schemas          — List supported resource schemas
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.database import get_db
from app.models.schemas import (
    ChatSession,
    ChatMessage,
    PRRecord,
    ResourceState,
    SessionStatus,
    MessageRole,
    ResourceStatus,
)
from app.models.api_models import (
    ChatRequest,
    ChatResponse,
    ChatSummaryInfo,
    MessageInfo,
    HealthResponse,
)
from app.agents.generator_agent import generator_agent
from app.agents.session_state import get_session as get_agent_session, delete_session
from app.services.schema_registry import schema_registry
from app.services.scm_adapter import create_pr_for_resource
from app.agents.history_provider import maybe_update_summary
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _build_chat_title(first_user_message: Optional[str]) -> str:
    """Build a compact sidebar title from the first user message."""
    text = (first_user_message or "").strip()
    if not text:
        return "New Chat"
    text = " ".join(text.split())
    return text if len(text) <= 48 else f"{text[:45].rstrip()}..."


async def get_latest_user_session(
    github_username: str,
    db: AsyncSession,
) -> Optional[ChatSession]:
    """Return the most recently updated chat session for a GitHub user."""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.github_username == github_username)
        .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_user_session(
    github_username: str,
    db: AsyncSession,
    github_token: Optional[str] = None,
) -> ChatSession:
    """Create a new chat session for a GitHub user."""
    session = ChatSession(
        id=str(uuid.uuid4()),
        github_username=github_username,
        created_by=github_username,
        status=SessionStatus.ACTIVE,
        github_token=github_token,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    logger.info(f"Created new session for user: {github_username}")
    return session


async def get_or_create_user_session(
    github_username: str,
    db: AsyncSession,
    session_id: Optional[str] = None,
) -> ChatSession:
    """Resolve a chat session for the current user, creating one if needed."""
    if session_id:
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == session_id,
                ChatSession.github_username == github_username,
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Chat session not found")
        return session

    session = await get_latest_user_session(github_username, db)
    if session:
        return session

    return await create_user_session(github_username, db)


async def get_session_messages(
    db: AsyncSession,
    session_id: str,
) -> list[ChatMessage]:
    """Return all messages for a chat session in chronological order."""
    msg_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    return list(msg_result.scalars().all())


def serialize_messages(messages: list[ChatMessage]) -> list[MessageInfo]:
    """Convert chat messages into API response objects."""
    return [
        MessageInfo(
            id=m.id,
            role=m.role.value,
            content=m.content,
            created_at=m.created_at,
            metadata_json=m.metadata_json,
        )
        for m in messages
    ]


async def build_chat_summary(
    db: AsyncSession,
    session: ChatSession,
) -> ChatSummaryInfo:
    """Build sidebar metadata for a chat session."""
    title_result = await db.execute(
        select(ChatMessage.content)
        .where(
            ChatMessage.session_id == session.id,
            ChatMessage.role == MessageRole.USER,
        )
        .order_by(ChatMessage.created_at)
        .limit(1)
    )
    first_message = title_result.scalar_one_or_none()

    count_result = await db.execute(
        select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session.id)
    )
    message_count = count_result.scalar_one() or 0

    return ChatSummaryInfo(
        id=session.id,
        title=_build_chat_title(first_message),
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=message_count,
    )


def require_github_user(
    x_github_user: Optional[str] = Header(None, alias="X-GitHub-User"),
) -> str:
    """Dependency: extract and validate X-GitHub-User header."""
    if not x_github_user or not x_github_user.strip():
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please log in with GitHub.",
        )
    return x_github_user.strip()


# ═══════════════════════════════════════════════════════════════
# CHAT
# ═══════════════════════════════════════════════════════════════

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    github_user: str = Depends(require_github_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Main chat endpoint. Sends a message to the generator agent.
    Requires authenticated user via X-GitHub-User header.
    """
    db_session = await get_or_create_user_session(github_user, db, request.session_id)
    session_id = db_session.id

    # Basic trust check — if session has a stored token,
    # verify the claimed username matches the session owner
    if db_session.github_token and db_session.github_username != github_user:
        raise HTTPException(status_code=403, detail="Session mismatch")

    # Store user message
    user_msg = ChatMessage(
        session_id=session_id,
        role=MessageRole.USER,
        content=request.message,
    )
    db.add(user_msg)
    await db.flush()

    # Sync GitHub token from DB to in-memory session state
    agent_session = get_agent_session(session_id)
    if db_session.github_token and agent_session:
        agent_session.github_token = db_session.github_token
        agent_session.github_username = db_session.github_username

    # Process through generator agent
    agent_response = await generator_agent.process_message(session_id, request.message)

    # Store assistant message
    assistant_msg = ChatMessage(
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content=agent_response["message"],
        metadata_json={
            "resource_type": agent_response.get("resource_type"),
            "resource_status": agent_response.get("resource_status"),
            "needs_confirmation": agent_response.get("needs_confirmation", False),
            "options": agent_response.get("options"),
            "options_multi_select": agent_response.get("options_multi_select", False),
        },
    )
    db.add(assistant_msg)

    # Update resource state in DB if we're working on a resource
    if agent_response.get("resource_type"):
        await _update_resource_state(db, session_id, agent_response)

    # Update session timestamp
    db_session.updated_at = datetime.now(timezone.utc)

    # Schedule background summarization (creates its own DB session)
    background_tasks.add_task(maybe_update_summary, session_id)

    chat_summary = await build_chat_summary(db, db_session)

    return ChatResponse(
        message=agent_response["message"],
        session_id=session_id,
        chat_title=chat_summary.title,
        updated_at=db_session.updated_at,
        resource_type=agent_response.get("resource_type"),
        resource_status=agent_response.get("resource_status"),
        generated_yaml=agent_response.get("generated_yaml"),
        needs_confirmation=agent_response.get("needs_confirmation", False),
        pr_url=agent_response.get("pr_url"),
        review_result=agent_response.get("review_result"),
        options=agent_response.get("options"),
        options_multi_select=agent_response.get("options_multi_select", False),
    )


# ═══════════════════════════════════════════════════════════════
# CHAT HISTORY
# ═══════════════════════════════════════════════════════════════

@router.get("/chats")
async def list_chats(
    github_user: str = Depends(require_github_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all chat sessions for the authenticated user."""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.github_username == github_user)
        .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
    )
    sessions = list(result.scalars().all())

    chats = [await build_chat_summary(db, session) for session in sessions]
    return JSONResponse(content={"chats": [chat.model_dump(mode="json") for chat in chats]})


@router.post("/chats", response_model=ChatSummaryInfo)
async def create_chat(
    github_user: str = Depends(require_github_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a brand-new chat session for the authenticated user."""
    latest_session = await get_latest_user_session(github_user, db)
    github_token = latest_session.github_token if latest_session else None
    session = await create_user_session(github_user, db, github_token=github_token)
    return await build_chat_summary(db, session)


@router.get("/chats/{chat_id}/messages", response_model=list[MessageInfo])
async def get_chat_messages(
    chat_id: str,
    github_user: str = Depends(require_github_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the full message history for one chat session."""
    session = await get_or_create_user_session(github_user, db, chat_id)
    messages = await get_session_messages(db, session.id)
    return serialize_messages(messages)


@router.delete("/chats/{chat_id}")
async def delete_chat(
    chat_id: str,
    github_user: str = Depends(require_github_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete one chat session and its persisted state."""
    session = await get_or_create_user_session(github_user, db, chat_id)

    await db.execute(PRRecord.__table__.delete().where(PRRecord.session_id == session.id))
    await db.execute(ChatMessage.__table__.delete().where(ChatMessage.session_id == session.id))
    await db.execute(ResourceState.__table__.delete().where(ResourceState.session_id == session.id))
    await db.execute(ChatSession.__table__.delete().where(ChatSession.id == session.id))
    await db.commit()

    delete_session(session.id)
    return {"deleted": True, "id": chat_id}

@router.get("/chat/history", response_model=list[MessageInfo])
async def get_chat_history(
    github_user: str = Depends(require_github_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return the full message history for the authenticated user.
    If user has no session yet, returns empty list.
    """
    session = await get_latest_user_session(github_user, db)

    if not session:
        return []

    messages = await get_session_messages(db, session.id)
    return serialize_messages(messages)


@router.delete("/chat/history")
async def clear_chat_history(
    github_user: str = Depends(require_github_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Clear the user's entire conversation history (escape hatch).
    Deletes messages + resource_states + summary. Session row persists.
    Also clears in-memory agent state so agent starts fresh.
    """
    result = await db.execute(
        select(ChatSession.id).where(ChatSession.github_username == github_user)
    )
    session_ids = list(result.scalars().all())

    if not session_ids:
        return {"cleared": True}

    await db.execute(PRRecord.__table__.delete().where(PRRecord.session_id.in_(session_ids)))
    await db.execute(ChatMessage.__table__.delete().where(ChatMessage.session_id.in_(session_ids)))
    await db.execute(ResourceState.__table__.delete().where(ResourceState.session_id.in_(session_ids)))

    sessions_result = await db.execute(
        select(ChatSession).where(ChatSession.id.in_(session_ids))
    )
    for session in sessions_result.scalars().all():
        session.conversation_summary = None
        session.updated_at = datetime.now(timezone.utc)
    await db.commit()

    for session_id in session_ids:
        delete_session(session_id)

    return {"cleared": True}


# ═══════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════

@router.get("/schemas")
async def list_schemas():
    """List all supported resource types."""
    return {
        "supported_types": schema_registry.get_supported_types(),
        "primary_types": schema_registry.get_primary_types(),
    }


# ═══════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="healthy", version="0.2.0")


# ═══════════════════════════════════════════════════════════════
# PR CREATION
# ═══════════════════════════════════════════════════════════════

@router.post("/chat/create-pr")
async def create_pr_manually(
    github_user: str = Depends(require_github_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger PR creation for the most recent confirmed resource
    that doesn't have a PR yet. Used when automatic PR creation failed.
    """
    db_session = await get_latest_user_session(github_user, db)
    if not db_session:
        raise HTTPException(status_code=404, detail="No session found")

    # Check GitHub connection
    if not db_session.github_token:
        return JSONResponse(content={
            "success": False,
            "error": "GitHub account not connected. Please reconnect.",
        })

    # Find most recent confirmed resource without a PR
    res_result = await db.execute(
        select(ResourceState)
        .where(
            ResourceState.session_id == db_session.id,
            ResourceState.status == ResourceStatus.CONFIRMED,
            ResourceState.pr_url.is_(None),
        )
        .order_by(ResourceState.created_at.desc())
        .limit(1)
    )
    resource_state = res_result.scalar_one_or_none()
    if not resource_state:
        raise HTTPException(status_code=404, detail="No confirmed resource found without a PR")

    # Extract fields for PR
    collected = resource_state.collected_fields or {}
    intake_id = collected.get("intake_id", "unknown")
    rtype = resource_state.resource_type
    resource_name = (
        collected.get("bucket_name")
        or collected.get("database_name")
        or collected.get("role_name")
        or "unknown"
    )

    # Call SCM adapter
    pr_result = await create_pr_for_resource(
        github_token=db_session.github_token,
        github_username=db_session.github_username,
        resource_type=rtype,
        intake_id=intake_id,
        resource_name=resource_name,
        yaml_content=resource_state.generated_yaml,
    )

    if pr_result.get("success"):
        resource_state.pr_url = pr_result["pr_url"]
        await db.commit()

    return JSONResponse(content=pr_result)


# ═══════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════

async def _update_resource_state(
    db: AsyncSession, session_id: str, agent_response: dict
):
    """Update or create resource state record in the DB."""
    resource_type = agent_response.get("resource_type")
    if not resource_type:
        return

    # Find existing active resource state for this session and type
    result = await db.execute(
        select(ResourceState).where(
            ResourceState.session_id == session_id,
            ResourceState.resource_type == resource_type,
            ResourceState.status.in_([
                ResourceStatus.COLLECTING,
                ResourceStatus.AWAITING_CONFIRMATION,
            ]),
        )
    )
    resource_state = result.scalar_one_or_none()

    status_map = {
        "collecting": ResourceStatus.COLLECTING,
        "awaiting_confirmation": ResourceStatus.AWAITING_CONFIRMATION,
        "confirmed": ResourceStatus.CONFIRMED,
        "cancelled": ResourceStatus.CANCELLED,
    }

    agent_session = get_agent_session(session_id)
    agent = agent_session.current_agent if agent_session else None

    new_status = status_map.get(
        agent_response.get("resource_status", "collecting"),
        ResourceStatus.COLLECTING,
    )

    if resource_state:
        resource_state.status = new_status
        resource_state.generated_yaml = agent_response.get("generated_yaml")
        resource_state.collected_fields = agent.collected_fields if agent else {}
        resource_state.current_field = agent.current_field if agent else None
        resource_state.updated_at = datetime.now(timezone.utc)
    else:
        resource_state = ResourceState(
            session_id=session_id,
            resource_type=resource_type,
            status=new_status,
            collected_fields=agent.collected_fields if agent else {},
            generated_yaml=agent_response.get("generated_yaml"),
            current_field=agent.current_field if agent else None,
        )
        db.add(resource_state)
