"""
Auth Routes — GitHub OAuth login, callback, and status check.
Single session per GitHub user (WhatsApp-style).
Supports both web app (redirect-based) and Chrome extension (launchWebAuthFlow) OAuth.
"""
import logging
import uuid
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models.database import get_db
from app.models.schemas import ChatSession, SessionStatus
from app.auth.github_oauth import (
    get_github_auth_url,
    exchange_code_for_token,
    get_github_username,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Helpers ───────────────────────────────────────────────────

async def _find_or_create_session(
    db: AsyncSession, username: str, token: str,
) -> ChatSession:
    """Find an existing session set for the user, or create one."""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.github_username == username)
        .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
    )
    sessions = list(result.scalars().all())
    db_session = sessions[0] if sessions else None

    if not db_session:
        db_session = ChatSession(
            id=str(uuid.uuid4()),
            github_username=username,
            created_by=username,
            status=SessionStatus.ACTIVE,
            github_token=token,
        )
        db.add(db_session)
        sessions = [db_session]

    for session in sessions:
        session.github_token = token

    await db.commit()
    return db_session


# ── Routes ────────────────────────────────────────────────────

@router.get("/github")
async def github_login():
    """Redirect user to GitHub OAuth authorization page."""
    auth_url = get_github_auth_url()
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/github/callback")
async def github_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle GitHub OAuth callback for both web and Chrome extension.

    Web flow: state is a CSRF token → redirect to frontend with ?auth=success
    Extension flow: state starts with "ext:" and embeds the chromiumapp.org
    redirect URL. After token exchange, we 302 redirect to that URL with
    github_user + github_token params.
    """
    if not code:
        return RedirectResponse(
            url=f"{settings.frontend_url}?auth_error=true",
            status_code=302,
        )

    state = state or ""
    is_extension_flow = state.startswith("ext:")
    extension_redirect_url = None

    if is_extension_flow:
        # State format: "ext:<nonce>:<chromiumapp_redirect_url>"
        parts = state.split(":", 2)  # ["ext", nonce, redirect_url]
        if len(parts) >= 3:
            extension_redirect_url = parts[2]

    try:
        # Extension: skip CSRF state validation (extension manages its own)
        # Web: validate CSRF state
        oauth_state = None if is_extension_flow else state
        token = await exchange_code_for_token(code, oauth_state)
    except ValueError as e:
        if is_extension_flow and extension_redirect_url:
            params = urlencode({"error": str(e)})
            return RedirectResponse(
                url=f"{extension_redirect_url}?{params}",
                status_code=302,
            )
        return RedirectResponse(
            url=f"{settings.frontend_url}?auth_error=true",
            status_code=302,
        )
    except Exception as e:
        logger.error(f"GitHub callback token exchange failed: {e}")
        if is_extension_flow and extension_redirect_url:
            params = urlencode({"error": "OAuth token exchange failed"})
            return RedirectResponse(
                url=f"{extension_redirect_url}?{params}",
                status_code=302,
            )
        return RedirectResponse(
            url=f"{settings.frontend_url}?auth_error=true",
            status_code=302,
        )

    try:
        username = await get_github_username(token)
    except ValueError as e:
        logger.error(f"GitHub callback username lookup failed: {e}")
        if is_extension_flow and extension_redirect_url:
            params = urlencode({"error": str(e)})
            return RedirectResponse(
                url=f"{extension_redirect_url}?{params}",
                status_code=302,
            )
        return RedirectResponse(
            url=f"{settings.frontend_url}?auth_error=true",
            status_code=302,
        )

    try:
        await _find_or_create_session(db, username, token)
    except Exception as e:
        logger.error(f"GitHub callback session persistence failed: {e}")
        if is_extension_flow and extension_redirect_url:
            params = urlencode({"error": "Failed to persist OAuth session"})
            return RedirectResponse(
                url=f"{extension_redirect_url}?{params}",
                status_code=302,
            )
        return RedirectResponse(
            url=f"{settings.frontend_url}?auth_error=true",
            status_code=302,
        )

    if is_extension_flow and extension_redirect_url:
        params = urlencode({
            "github_user": username,
            "github_token": token,
            "state": state,
        })
        return RedirectResponse(
            url=f"{extension_redirect_url}?{params}",
            status_code=302,
        )

    # Web: redirect to frontend
    try:
        redirect_url = f"{settings.frontend_url}?auth=success&github_user={username}"
        return RedirectResponse(url=redirect_url, status_code=302)
    except Exception as e:
        logger.error(f"GitHub callback frontend redirect failed: {e}")
        return RedirectResponse(
            url=f"{settings.frontend_url}?auth_error=true",
            status_code=302,
        )


@router.get("/me")
async def auth_status(
    x_github_user: Optional[str] = Header(None, alias="X-GitHub-User"),
    db: AsyncSession = Depends(get_db),
):
    """Check if a GitHub user has an active session with a connected account."""
    if not x_github_user:
        return JSONResponse(content={
            "authenticated": False,
            "username": None,
            "has_session": False,
        })

    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.github_username == x_github_user)
        .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
        .limit(1)
    )
    db_session = result.scalar_one_or_none()

    if not db_session or not db_session.github_token:
        return JSONResponse(content={
            "authenticated": False,
            "username": x_github_user,
            "has_session": db_session is not None,
        })

    return JSONResponse(content={
        "authenticated": True,
        "username": db_session.github_username,
        "has_session": True,
    })


@router.get("/github-client-id")
async def get_client_id():
    """Return the GitHub OAuth client ID (public info — safe to expose)."""
    return JSONResponse(content={"client_id": settings.github_client_id or ""})


@router.post("/extension-exchange")
async def extension_exchange(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Exchange an OAuth authorization code for a token (Chrome extension only).

    The extension's background.js receives the code from GitHub via
    chrome.identity.launchWebAuthFlow, then POSTs the code here.
    We exchange it for a token, find/create the user's session, and return
    { username, token }.
    """
    code = body.get("code")
    if not code:
        return JSONResponse(
            content={"detail": "Missing authorization code"},
            status_code=400,
        )

    try:
        # No state validation for extension flow
        token = await exchange_code_for_token(code)
    except ValueError as e:
        return JSONResponse(
            content={"detail": str(e)},
            status_code=400,
        )
    except Exception as e:
        logger.error(f"Extension OAuth token exchange failed: {e}")
        return JSONResponse(
            content={"detail": "OAuth token exchange failed"},
            status_code=500,
        )

    try:
        username = await get_github_username(token)
    except ValueError as e:
        logger.error(f"Extension OAuth get username failed: {e}")
        return JSONResponse(
            content={"detail": str(e)},
            status_code=400,
        )
    except Exception as e:
        logger.error(f"Extension OAuth get username failed: {e}")
        return JSONResponse(
            content={"detail": "Failed to get GitHub username"},
            status_code=500,
        )

    await _find_or_create_session(db, username, token)

    return JSONResponse(content={
        "username": username,
        "token": token,
    })
