"""
Message repository — CRUD for the messages table.
Supports bulk insert for event-based flushing.
"""
import json
from datetime import datetime, timezone
from app.db.connection import get_db


async def bulk_insert_messages(session_id: str, messages: list[dict]):
    """
    Insert multiple messages at once (event-based flush).
    Each message dict: {"role": str, "content": str, "created_at": str, "metadata": dict|None}
    """
    if not messages:
        return

    db = await get_db()
    await db.executemany(
        "INSERT INTO messages (session_id, role, content, metadata, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (
                session_id,
                msg["role"],
                msg["content"],
                json.dumps(msg.get("metadata")) if msg.get("metadata") else None,
                msg.get("created_at", datetime.now(timezone.utc).isoformat()),
            )
            for msg in messages
        ],
    )
    await db.commit()


async def get_recent_messages(session_id: str, limit: int = 20) -> list[dict]:
    """Get last N messages for a session (returned in chronological order)."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT role, content, metadata, created_at FROM messages "
        "WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
        (session_id, limit),
    )
    rows = await cursor.fetchall()
    # Return in chronological order (oldest first)
    result = [dict(r) for r in rows]
    result.reverse()
    return result


async def get_message_count(session_id: str) -> int:
    """Get total message count for a session."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) FROM messages WHERE session_id = ?",
        (session_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0
