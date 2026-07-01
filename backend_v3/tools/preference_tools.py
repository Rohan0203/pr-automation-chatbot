"""Profile tools — observe and store user behavioral profile."""
from __future__ import annotations

import json

from tools.session_tools import _get_session
from db.repository import save_user_profile as db_save_profile


async def update_user_profile(profile: str, **kwargs) -> str:
    """Update the user's behavioral profile description."""
    session = _get_session()
    await db_save_profile(session.user_id, profile)
    return json.dumps({"saved": True, "profile_length": len(profile)})
