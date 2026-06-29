"""
Path Resolver — Resolves the correct file path in the upstream repo
based on resource type and collected fields.

Uses data/account_directory_map.yaml for account → folder mapping.
"""
import logging
from pathlib import Path
from typing import Optional

import yaml

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# LOAD MAPPING
# ═══════════════════════════════════════════════════════════════

_MAP_FILE = DATA_DIR / "account_directory_map.yaml"
_account_map: dict = {}


def _load_map() -> dict:
    """Load account directory mapping from YAML file. Cached after first load."""
    global _account_map
    if _account_map:
        return _account_map
    try:
        with open(_MAP_FILE, "r", encoding="utf-8") as f:
            _account_map = yaml.safe_load(f) or {}
        logger.info(f"Loaded account directory map with {len(_account_map.get('accounts', {}))} accounts")
    except FileNotFoundError:
        logger.warning(f"Account directory map not found: {_MAP_FILE}")
        _account_map = {}
    except Exception as e:
        logger.error(f"Failed to load account directory map: {e}")
        _account_map = {}
    return _account_map


def reload_map():
    """Force reload the mapping (useful after editing the YAML file)."""
    global _account_map
    _account_map = {}
    return _load_map()


# ═══════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════

def resolve_file_path(resource_type: str, fields: dict) -> str:
    """
    Resolve the full file path for a resource in the upstream repo.

    Args:
        resource_type: e.g. "s3", "glue_db", "iam"
        fields: collected fields dict (must include aws_account_id and the name field)

    Returns:
        Full path like "aws_lakehouse/lakehouse-001/s3/prd-lh1-agtr-src.yaml"

    Raises:
        ValueError: if account ID not found or required fields missing
    """
    mapping = _load_map()
    accounts = mapping.get("accounts", {})
    resource_folders = mapping.get("resource_folders", {})
    name_fields = mapping.get("resource_name_fields", {})

    # 1. Resolve account folder
    account_id = fields.get("aws_account_id", "")
    # Strip surrounding quotes — YAML single-quoted values may arrive as "'123'"
    account_id = str(account_id).strip("'\"")
    account_info = accounts.get(account_id)

    if not account_info:
        raise ValueError(
            f"Unknown aws_account_id: '{account_id}'. "
            f"Add it to data/account_directory_map.yaml."
        )

    account_folder = account_info["folder"]

    # 2. Resolve resource subfolder
    subfolder = resource_folders.get(resource_type)
    if not subfolder:
        raise ValueError(
            f"Unknown resource_type: '{resource_type}'. "
            f"Add it to resource_folders in data/account_directory_map.yaml."
        )

    # 3. Resolve filename from the appropriate field
    name_field = name_fields.get(resource_type, "")
    resource_name = fields.get(name_field, "") if name_field else ""

    if not resource_name:
        # Fallback: try common name fields
        resource_name = (
            fields.get("bucket_name")
            or fields.get("database_name")
            or fields.get("role_name")
            or fields.get("intake_id", "unknown")
        )

    return f"{account_folder}/{subfolder}/{resource_name}.yaml"


def resolve_batch_paths(resources: list[dict]) -> list[dict]:
    """
    Resolve file paths for a batch of resources.

    Args:
        resources: list of dicts with {resource_type, fields, ...} or
                   {resource_type, intake_id, resource_name, yaml_content}

    Returns:
        Same list with 'resolved_path' added to each dict.
        If resolution fails, falls back to configs/{type}/{name}.yaml
    """
    for r in resources:
        fields = r.get("fields", r)  # Support both batch entries and scm resource dicts
        rtype = r.get("resource_type", "unknown")
        try:
            r["resolved_path"] = resolve_file_path(rtype, fields)
        except ValueError as e:
            logger.warning(f"Path resolution failed for {rtype}: {e}")
            name = (
                r.get("resource_name")
                or fields.get("bucket_name")
                or fields.get("database_name")
                or fields.get("role_name")
                or r.get("intake_id", "unknown")
            )
            r["resolved_path"] = f"configs/{rtype}/{name}.yaml"
    return resources


def get_account_info(account_id: str) -> Optional[dict]:
    """Get account info for a given account ID, or None if not found."""
    mapping = _load_map()
    return mapping.get("accounts", {}).get(str(account_id))
