"""
MiNi — FastAPI server
Connects the agent to the frontend.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add backend_v3 to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from models.state import Session, ResourceStatus
from db.connection import set_db_path, init_db, close_db
from db.repository import (
    save_session, load_session, list_sessions, delete_session,
    update_session_title, get_session_messages,
)
from tools.session_tools import bind_session
from agent.loop import run_agent_turn


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    db_path = Path(__file__).parent / "mini.db"
    set_db_path(db_path)
    await init_db()
    yield
    await close_db()


app = FastAPI(title="MiNi Agent API", version="3.0.0", lifespan=lifespan)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_user(request: Request) -> str:
    """Extract user from header (stub auth)."""
    return request.headers.get("X-GitHub-User", "default")


def _generate_title(message: str) -> str:
    """Generate a short chat title from the first message."""
    clean = message.strip()[:60]
    if len(message) > 60:
        clean += "..."
    return clean


# ─── Auth routes ──────────────────────────────────────────────────────────────

@app.get("/auth/github")
async def auth_github():
    """Redirect user to Cargill GitHub Enterprise OAuth page."""
    from fastapi.responses import RedirectResponse
    from auth import get_auth_url
    return RedirectResponse(url=get_auth_url(), status_code=302)


@app.get("/auth/github/callback")
async def auth_github_callback(code: str | None = None, state: str | None = None):
    """Handle GitHub OAuth callback — exchange code, get username, redirect to frontend."""
    from fastapi.responses import RedirectResponse
    from auth import exchange_code, get_username, FRONTEND_URL
    import logging

    if not code:
        return RedirectResponse(url=f"{FRONTEND_URL}?auth_error=true", status_code=302)

    try:
        token = await exchange_code(code, state)
        username = await get_username(token)
    except Exception as e:
        logging.getLogger(__name__).error(f"OAuth callback failed: {e}")
        return RedirectResponse(url=f"{FRONTEND_URL}?auth_error=true", status_code=302)

    return RedirectResponse(
        url=f"{FRONTEND_URL}?auth=success&github_user={username}",
        status_code=302,
    )


@app.get("/auth/me")
async def auth_me(request: Request):
    """Check if user is authenticated (based on X-GitHub-User header from frontend)."""
    user = _get_user(request)
    if not user or user == "default":
        return {"authenticated": False}
    return {"authenticated": True, "github_user": user}


# ─── Chat CRUD ────────────────────────────────────────────────────────────────

@app.get("/api/chats")
async def list_chats(request: Request):
    """List all chats for the current user."""
    user = _get_user(request)
    sessions = await list_sessions(user)
    return {"chats": sessions}


@app.post("/api/chats")
async def create_chat(request: Request):
    """Create a new empty chat session."""
    user = _get_user(request)
    session_id = str(uuid.uuid4())
    session = Session(session_id=session_id, user_id=user)
    await save_session(session, title="New Chat")
    return {
        "id": session_id,
        "title": "New Chat",
        "created_at": session.created_at.isoformat(),
        "updated_at": session.created_at.isoformat(),
        "message_count": 0,
    }


@app.get("/api/chats/{chat_id}/messages")
async def get_chat_messages(chat_id: str, request: Request):
    """Get all messages for a chat."""
    messages = await get_session_messages(chat_id)
    return messages


@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str, request: Request):
    """Delete a chat session."""
    await delete_session(chat_id)
    return None


# ─── Main chat endpoint ───────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str


@app.post("/api/chat")
async def chat(body: ChatRequest, request: Request):
    """Process a user message through the agent and return the response."""
    user = _get_user(request)
    session_id = body.session_id
    message = body.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Load or create session
    session = await load_session(session_id)
    if session is None:
        session = Session(session_id=session_id, user_id=user)
        await save_session(session, title=_generate_title(message))

    # Bind session for tools
    bind_session(session)

    # Run agent
    response = await run_agent_turn(session, message)

    # Update title if this is the first real message
    if len(session.messages) <= 2:  # user + assistant
        await update_session_title(session_id, _generate_title(message))

    # Check if any resource has YAML generated
    generated_yaml = None
    for r in session.resources:
        if r.status == ResourceStatus.DONE and r.yaml_output:
            generated_yaml = r.yaml_output
            break

    return {
        "message": response,
        "session_id": session_id,
        "chat_title": _generate_title(message),
        "generated_yaml": generated_yaml,
        "options": None,
        "options_multi_select": False,
        "updated_at": datetime.utcnow().isoformat(),
    }


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
