"""
Database initialization — creates tables on startup if they don't exist.
Reads schema.sql and executes it against the SQLite connection.
"""
import logging
from pathlib import Path
from app.db.connection import get_db

logger = logging.getLogger(__name__)

_SCHEMA_FILE = Path(__file__).parent / "schema.sql"


async def init_db():
    """Create tables if they don't exist. Safe to call multiple times."""
    db = await get_db()

    schema_sql = _SCHEMA_FILE.read_text(encoding="utf-8")

    await db.executescript(schema_sql)
    await db.commit()

    logger.info("Database schema initialized")
