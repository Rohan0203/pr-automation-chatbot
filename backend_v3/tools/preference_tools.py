"""Preference tools — store and retrieve user preferences."""
from __future__ import annotations

import json

from tools.session_tools import _get_session
from db.repository import save_preference as db_save_preference


async def save_preference(key: str, value: str, **kwargs) -> str:
    """Save a user preference."""
    session = _get_session()
    await db_save_preference(session.user_id, key, value)
    return json.dumps({"saved": {"key": key, "value": value}})
