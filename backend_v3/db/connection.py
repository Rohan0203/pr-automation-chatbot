"""Async SQLite connection manager."""
from __future__ import annotations

import asyncio
import aiosqlite
from pathlib import Path

_DB_PATH: Path | None = None
_connection: aiosqlite.Connection | None = None


def set_db_path(path: str | Path):
    global _DB_PATH
    _DB_PATH = Path(path)


async def get_db() -> aiosqlite.Connection:
    """Get or create the database connection."""
    global _connection
    if _connection is None:
        if _DB_PATH is None:
            raise RuntimeError("Database path not configured. Call set_db_path() first.")
        _connection = await aiosqlite.connect(_DB_PATH)
        _connection.row_factory = aiosqlite.Row
        await _connection.execute("PRAGMA journal_mode=WAL")
        await _connection.execute("PRAGMA foreign_keys=ON")
    return _connection


async def init_db():
    """Initialize database tables from schema.sql."""
    db = await get_db()
    schema_path = Path(__file__).parent / "schema.sql"
    schema = schema_path.read_text(encoding="utf-8")
    await db.executescript(schema)

    resource_columns = await db.execute_fetchall("PRAGMA table_info(resources)")
    resource_column_names = {row["name"] for row in resource_columns}
    if "user_overrides" not in resource_column_names:
        await db.execute("ALTER TABLE resources ADD COLUMN user_overrides TEXT NOT NULL DEFAULT '{}' ")

    await db.commit()


async def close_db():
    """Close the database connection."""
    global _connection
    if _connection:
        connection = _connection
        _connection = None
        try:
            await asyncio.shield(connection.close())
        except asyncio.CancelledError:
            pass
