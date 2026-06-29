"""
Session store — in-memory session management.

Simple dict-backed store. Replace with DB later if needed.
"""
from app.models.state import Session, SessionMode

_sessions: dict[str, Session] = {}


def get_session(session_id: str) -> Session:
    """Get or create a session."""
    if session_id not in _sessions:
        _sessions[session_id] = Session(session_id=session_id)
    return _sessions[session_id]


def reset_session(session_id: str) -> Session:
    """Reset a session to initial state."""
    _sessions[session_id] = Session(session_id=session_id)
    return _sessions[session_id]


def delete_session(session_id: str):
    """Remove a session entirely."""
    _sessions.pop(session_id, None)
