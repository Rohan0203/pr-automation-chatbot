"""Database repository — CRUD for sessions, resources, messages, preferences."""
from __future__ import annotations

import json
from datetime import datetime

from db.connection import get_db
from models.state import Session, Resource, Message, Preference, ResourceStatus


# ─── Sessions ─────────────────────────────────────────────────────────────────

async def save_session(session: Session):
    """Upsert session metadata."""
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO sessions (session_id, user_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (session.session_id, session.user_id, session.created_at.isoformat(), datetime.utcnow().isoformat()),
    )
    await db.commit()


async def load_session(session_id: str) -> Session | None:
    """Load a session with its resources and messages."""
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
    )
    if not row:
        return None

    session = Session(session_id=session_id, user_id=row[0]["user_id"])

    # Load resources
    resource_rows = await db.execute_fetchall(
        "SELECT * FROM resources WHERE session_id = ? ORDER BY id", (session_id,)
    )
    for r in resource_rows:
        session.resources.append(Resource(
            resource_id=r["resource_id"],
            resource_type=r["resource_type"],
            status=ResourceStatus(r["status"]),
            collected_fields=json.loads(r["collected_fields"]),
            derived_fields=json.loads(r["derived_fields"]),
            yaml_output=r["yaml_output"],
        ))

    # Load messages
    msg_rows = await db.execute_fetchall(
        "SELECT * FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
    )
    for m in msg_rows:
        session.messages.append(Message(
            role=m["role"],
            content=m["content"],
            tool_calls=json.loads(m["tool_calls"]) if m["tool_calls"] else None,
        ))

    return session


# ─── Resources ────────────────────────────────────────────────────────────────

async def save_resource(session_id: str, resource: Resource):
    """Upsert a resource."""
    db = await get_db()
    await db.execute(
        """INSERT OR REPLACE INTO resources
           (session_id, resource_id, resource_type, status, collected_fields, derived_fields, yaml_output)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            resource.resource_id,
            resource.resource_type,
            resource.status.value,
            json.dumps(resource.collected_fields),
            json.dumps(resource.derived_fields),
            resource.yaml_output,
        ),
    )
    await db.commit()


# ─── Messages ─────────────────────────────────────────────────────────────────

async def save_message(session_id: str, message: Message):
    """Append a message to the session."""
    db = await get_db()
    await db.execute(
        "INSERT INTO messages (session_id, role, content, tool_calls, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            session_id,
            message.role,
            message.content,
            json.dumps(message.tool_calls) if message.tool_calls else None,
            message.timestamp.isoformat(),
        ),
    )
    await db.commit()


# ─── Preferences ──────────────────────────────────────────────────────────────

async def save_preference(user_id: str, key: str, value: str):
    """Upsert a user preference."""
    db = await get_db()
    await db.execute(
        """INSERT INTO preferences (user_id, key, value, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
        (user_id, key, value, datetime.utcnow().isoformat()),
    )
    await db.commit()


async def load_preferences(user_id: str) -> list[Preference]:
    """Load all preferences for a user."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT key, value FROM preferences WHERE user_id = ?", (user_id,)
    )
    return [Preference(key=r["key"], value=r["value"], user_id=user_id) for r in rows]
