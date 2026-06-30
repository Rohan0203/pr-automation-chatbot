"""
Derivation context loader.
Loads only the required context packs for requested derivable fields.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

_DERIVATION_ROOT = Path(__file__).resolve().parent.parent.parent / "context" / "derivation"

# field -> pack ids for each resource type
_FIELD_PACK_MAP: dict[str, dict[str, list[str]]] = {
    "s3": {
        "bucket_name": ["variables", "naming_rules", "examples"],
        "bucket_description": ["description_templates", "variables"],
        "aws_account_id": ["shared/account_abbreviations", "variables"],
        "aws_region": ["variables"],
    }
}

_pack_cache: dict[str, Any] = {}


def _pack_path(resource_type: str, pack_id: str) -> Path:
    if pack_id.startswith("shared/"):
        return _DERIVATION_ROOT / f"{pack_id}.yaml"
    return _DERIVATION_ROOT / resource_type / f"{pack_id}.yaml"


def _load_pack(resource_type: str, pack_id: str) -> Any:
    cache_key = f"{resource_type}:{pack_id}"
    if cache_key in _pack_cache:
        return _pack_cache[cache_key]

    path = _pack_path(resource_type, pack_id)
    if not path.exists():
        _pack_cache[cache_key] = None
        return None

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    _pack_cache[cache_key] = data
    return data


def _pack_to_text(pack_id: str, pack_data: Any) -> str:
    if pack_data is None:
        return f"PACK: {pack_id}\nMISSING"
    body = json.dumps(pack_data, indent=2, ensure_ascii=True)
    return f"PACK: {pack_id}\n{body}"


def load_derivation_context(resource_type: str, requested_fields: list[str]) -> dict[str, Any]:
    """
    Build minimal prompt context for requested derivable fields.

    Returns:
      {
        "field_context": {field_name: "..."},
        "packs_used": [pack ids],
        "prompt_contract": {...} | None,
      }
    """
    mapping = _FIELD_PACK_MAP.get(resource_type, {})

    field_context: dict[str, str] = {}
    packs_used: set[str] = set()
    all_pack_data: dict[str, Any] = {}

    for field_name in requested_fields:
        pack_ids = mapping.get(field_name, [])
        if not pack_ids:
            continue

        chunks: list[str] = []
        for pack_id in pack_ids:
            pack_value = _load_pack(resource_type, pack_id)
            chunks.append(_pack_to_text(pack_id, pack_value))
            packs_used.add(pack_id)
            if pack_id not in all_pack_data:
                all_pack_data[pack_id] = pack_value

        field_context[field_name] = "\n\n".join(chunks)

    prompt_contract = _load_pack(resource_type, "prompt_contract")
    if "prompt_contract" not in all_pack_data:
        all_pack_data["prompt_contract"] = prompt_contract

    return {
        "field_context": field_context,
        "packs_used": sorted(packs_used),
        "prompt_contract": prompt_contract,
        "pack_data": all_pack_data,
    }
