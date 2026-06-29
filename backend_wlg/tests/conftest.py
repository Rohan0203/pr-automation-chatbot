"""Shared fixtures for backend_wlg tests."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# Load env for all tests
_root = Path(__file__).resolve().parent.parent.parent
_env_path = _root / ".env"
if not _env_path.exists():
    _env_path = _root / "backend" / ".env"
load_dotenv(_env_path)
