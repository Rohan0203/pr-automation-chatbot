"""
Session repository — CRUD for the sessions table.
"""
import json
from datetime import datetime, timezone
from app.db.connection import get_db


async def create_session(session_id: str, user_id: int | None = None):
    """Insert a new session row."""
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT OR IGNORE INTO sessions (id, user_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (session_id, user_id, now, now),
    )
    await db.commit()


async def get_session(session_id: str) -> dict | None:
    """Fetch a session by ID. Returns None if not found."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, user_id, mode, status, resources, summary, created_at, updated_at "
        "FROM sessions WHERE id = ?",
        (session_id,),
    )
    row = await cursor.fetchone()
    if row:
        result = dict(row)
        if isinstance(result["resources"], str):
            result["resources"] = json.loads(result["resources"])
        return result
    return None


async def update_session_mode(session_id: str, mode: str):
    """Update session mode (idle/working)."""
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE sessions SET mode = ?, updated_at = ? WHERE id = ?",
        (mode, now, session_id),
    )
    await db.commit()


async def update_session_resources(session_id: str, resources_json: list):
    """Update the resources JSON column."""
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE sessions SET resources = ?, updated_at = ? WHERE id = ?",
        (json.dumps(resources_json), now, session_id),
    )
    await db.commit()


async def update_session_summary(session_id: str, summary: str):
    """Update the conversation summary."""
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE sessions SET summary = ?, updated_at = ? WHERE id = ?",
        (summary, now, session_id),
    )
    await db.commit()


async def end_session(session_id: str, status: str = "completed"):
    """Mark session as completed or cancelled."""
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE sessions SET status = ?, mode = 'idle', updated_at = ? WHERE id = ?",
        (status, now, session_id),
    )
    await db.commit()


async def get_user_sessions(user_id: int, limit: int = 10) -> list[dict]:
    """Get recent sessions for a user (ordered by most recent)."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, mode, status, resources, summary, created_at, updated_at "
        "FROM sessions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
