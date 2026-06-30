"""
Database connection — async SQLite using aiosqlite.
Reads DATABASE_URL from .env. Provides get_db() for all DB operations.
"""
import os
import aiosqlite
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)

# Extract path from sqlite:///./path or just use the raw value
_raw_url = os.getenv("DATABASE_URL", "sqlite:///./pr_chatbot.db")
if _raw_url.startswith("sqlite:///"):
    DB_PATH = _raw_url.replace("sqlite:///", "")
else:
    DB_PATH = _raw_url

# Resolve relative path from backend_v2/ directory
if not os.path.isabs(DB_PATH):
    DB_PATH = str(Path(__file__).resolve().parent.parent.parent / DB_PATH)

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Get or create the SQLite connection."""
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")  # better concurrency
        await _db.execute("PRAGMA foreign_keys=ON")
        logger.info("SQLite connected: %s", DB_PATH)
    return _db


async def close_db():
    """Close the SQLite connection."""
    global _db
    if _db:
        await _db.close()
        _db = None
        logger.info("SQLite connection closed")
