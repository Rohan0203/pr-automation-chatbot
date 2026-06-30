"""
Persistence — bridges in-memory session state with the database.

Three entry points called by the orchestrator:
  init_session(session)  — called once when a new session starts
  flush(session)         — called at key events (resource done, etc.)
  end_session(session)   — called when session ends
"""
import json
from app.models import Session, ResourceStatus
from app.db.sessions import create_session, update_session_mode, update_session_resources, end_session as db_end_session
from app.db.messages import bulk_insert_messages


async def init_session(session: Session, user_id: int | None = None):
    """Create session row in DB. Called once at session start."""
    await create_session(session.session_id, user_id)


async def flush(session: Session):
    """Flush un-persisted messages and update session state in DB."""
    # Flush new messages since last flush
    new_messages = session.history[session._flushed_idx:]
    if new_messages:
        await bulk_insert_messages(session.session_id, new_messages)
        session._flushed_idx = len(session.history)

    # Update session state
    await update_session_mode(session.session_id, session.mode.value)
    resources_json = [
        {"id": r.resource_id, "type": r.resource_type, "status": r.status.value, "fields": r.fields}
        for r in session.resources
    ]
    await update_session_resources(session.session_id, resources_json)


async def end_session(session: Session):
    """Final flush + mark session complete."""
    await flush(session)
    await db_end_session(session.session_id)
