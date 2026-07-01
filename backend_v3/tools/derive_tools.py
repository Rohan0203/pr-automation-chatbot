"""Derive tools — compute derivable fields from collected values + config."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from models.state import ResourceStatus
from tools.session_tools import _get_session
from db.repository import save_resource

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# Cache
_accounts: list[dict] | None = None


def _load_accounts() -> list[dict]:
    """Load the accounts config."""
    global _accounts
    if _accounts is None:
        path = _CONFIG_DIR / "accounts.yaml"
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        _accounts = data.get("accounts", [])
    return _accounts


def _load_resource_config(resource_type: str) -> dict:
    path = _CONFIG_DIR / "resources" / f"{resource_type}.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _derive_s3_fields(collected: dict[str, Any]) -> dict[str, Any]:
    """Derive S3-specific fields from collected values."""
    derived = {}
    accounts = _load_accounts()
    config = _load_resource_config("s3")

    plat_env = collected.get("plat_env", "prd")
    usage_type = collected.get("usage_type", "")
    enterprise = collected.get("enterprise_or_func_name", "")
    subgroup = collected.get("enterprise_or_func_subgrp_name", "")

    # 1. aws_region — always us-east-1
    derived["aws_region"] = "us-east-1"

    # 2. aws_account_id — based on usage_type + enterprise + plat_env
    account = None
    if usage_type == "Source":
        # Source → lakehouse for the target env
        account = next((a for a in accounts if a["type"] == "lakehouse" and a["plat_env"] == plat_env), None)
    elif usage_type == "DataProduct":
        # DataProduct → compute account matching enterprise + env
        account = next(
            (a for a in accounts if a["type"] == "compute" and a["plat_env"] == plat_env and a["enterprise"] == enterprise),
            None,
        )
    else:
        # Scripts/EngAssets → default to lakehouse for target env
        account = next((a for a in accounts if a["type"] == "lakehouse" and a["plat_env"] == plat_env), None)

    if account:
        derived["aws_account_id"] = account["id"]
        acct_abbr = account["abbreviation"]
    else:
        derived["aws_account_id"] = "UNKNOWN"
        acct_abbr = f"{plat_env}-lh1"

    # 3. bucket_name — pattern: {plat_env}-{acct_type}-{entity}[-{subgrp}]-{suffix}
    suffix_map = config.get("derivation", {}).get("bucket_name", {}).get("segments", {}).get("suffix_map") or {}
    if not suffix_map:
        suffix_map = {"Source": "src", "DataProduct": "dp", "Scripts": "scripts", "EngAssets": "eng-assets"}
    # Get from derivation config
    derivation_config = config.get("derivation", {}).get("bucket_name", {})
    actual_suffix_map = derivation_config.get("suffix_map") or suffix_map

    suffix = actual_suffix_map.get(usage_type, "src")
    entity = enterprise.lower()
    subgrp_part = f"-{subgroup.lower()}" if subgroup else ""
    derived["bucket_name"] = f"{acct_abbr}{'-' if not acct_abbr.endswith('-') else ''}{entity}{subgrp_part}-{suffix}"

    # Fix: acct_abbr already contains "prd-lh1" so pattern is "prd-lh1-agtr-src"
    # Actually the abbreviation is like "prd-lh1", entity is "agtr", so: "prd-lh1-agtr-src"
    derived["bucket_name"] = f"{acct_abbr}-{entity}{subgrp_part}-{suffix}"

    # 4. bucket_description
    subgrp_text = f" {subgroup}" if subgroup else ""
    derived["bucket_description"] = f"{usage_type} bucket for {enterprise}{subgrp_text}"

    return derived


async def derive_fields(resource_id: str, **kwargs) -> str:
    """Derive computable fields for a resource."""
    session = _get_session()
    resource = session.get_resource(resource_id)

    if not resource:
        return json.dumps({"error": f"Resource '{resource_id}' not found"})

    # Guard: all required collect_fields must be present before deriving
    config = _load_resource_config(resource.resource_type)
    missing = []
    for field_spec in config.get("collect_fields", []):
        if not field_spec.get("required", False):
            continue
        if field_spec.get("allow_empty", False):
            continue
        if field_spec["name"] not in resource.collected_fields:
            missing.append(field_spec["name"])

    if missing:
        return json.dumps({
            "error": "Cannot derive — required fields are still missing",
            "missing_fields": missing,
            "resource_id": resource.resource_id,
        })

    # Route to resource-specific derivation
    if resource.resource_type == "s3":
        derived = _derive_s3_fields(resource.collected_fields)
    else:
        derived = {}

    # Store derived fields
    resource.derived_fields = derived
    resource.status = ResourceStatus.CONFIRMING
    await save_resource(session.session_id, resource)

    return json.dumps({
        "resource_id": resource.resource_id,
        "status": "confirming",
        "derived_fields": derived,
        "all_fields": resource.all_fields,
    })
