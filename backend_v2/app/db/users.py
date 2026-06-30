"""
User repository — CRUD for the users table.
"""
import json
from datetime import datetime, timezone
from app.db.connection import get_db


async def get_or_create_user(github_username: str) -> dict:
    """Find user by github_username or create a new one. Returns user row as dict."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, github_username, github_token, profile, created_at, updated_at "
        "FROM users WHERE github_username = ?",
        (github_username,),
    )
    row = await cursor.fetchone()
    if row:
        return _row_to_dict(row)

    now = datetime.now(timezone.utc).isoformat()
    cursor = await db.execute(
        "INSERT INTO users (github_username, created_at, updated_at) VALUES (?, ?, ?)",
        (github_username, now, now),
    )
    await db.commit()
    user_id = cursor.lastrowid

    return {
        "id": user_id,
        "github_username": github_username,
        "github_token": None,
        "profile": {},
        "created_at": now,
        "updated_at": now,
    }


async def get_user_profile(github_username: str) -> dict | None:
    """Get user profile JSON. Returns None if user doesn't exist."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT profile FROM users WHERE github_username = ?",
        (github_username,),
    )
    row = await cursor.fetchone()
    if row:
        return json.loads(row[0]) if row[0] else {}
    return None


async def update_user_profile(github_username: str, profile_updates: dict):
    """Merge updates into the user's profile JSON."""
    db = await get_db()
    # Read current profile
    cursor = await db.execute(
        "SELECT profile FROM users WHERE github_username = ?",
        (github_username,),
    )
    row = await cursor.fetchone()
    if not row:
        return

    current = json.loads(row[0]) if row[0] else {}
    current.update(profile_updates)

    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE users SET profile = ?, updated_at = ? WHERE github_username = ?",
        (json.dumps(current), now, github_username),
    )
    await db.commit()


async def update_user_token(github_username: str, token: str):
    """Store or update the GitHub OAuth token for a user."""
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE users SET github_token = ?, updated_at = ? WHERE github_username = ?",
        (token, now, github_username),
    )
    await db.commit()


def _row_to_dict(row) -> dict:
    """Convert a sqlite Row to a plain dict with parsed profile."""
    d = dict(row)
    if "profile" in d and isinstance(d["profile"], str):
        d["profile"] = json.loads(d["profile"]) if d["profile"] else {}
    return d
