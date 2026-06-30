"""
LLM-driven derivation for missing derivable fields.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.collection.spec_registry import get_field_specs
from app.models import Resource, FieldSpec
from app.llm.client import chat_json


_SUFFIX_MAP = {
    "Source": "src",
    "DataProduct": "dp",
    "Scripts": "scripts",
    "EngAssets": "eng-assets",
}

_ACCOUNT_ABBR_PATTERN = re.compile(r"^(dev|prd)-(lh1|cmp[1-4])(?:-|$)")


def _field_spec_map(resource_type: str) -> dict[str, FieldSpec]:
    return {spec.name: spec for spec in get_field_specs(resource_type)}


def _is_valid_aws_account_id(value: str) -> bool:
    return bool(re.fullmatch(r"\d{12}", str(value or "")))


def _is_valid_s3_bucket_name(value: str) -> bool:
    text = str(value or "")
    if len(text) < 3 or len(text) > 63:
        return False
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*[a-z0-9]", text):
        return False
    if ".." in text or ".-" in text or "-." in text:
        return False
    return True


def _validate_value(spec: FieldSpec, value: Any) -> bool:
    if value is None:
        return False

    if spec.options and str(value) not in spec.options:
        return False

    if spec.name == "aws_account_id":
        return _is_valid_aws_account_id(str(value))

    if spec.name == "bucket_name":
        return _is_valid_s3_bucket_name(str(value))

    return True


def _extract_account_abbreviation(resource: Resource) -> str | None:
    bucket_name = str(resource.fields.get("bucket_name") or "").strip().lower()
    if bucket_name:
        match = _ACCOUNT_ABBR_PATTERN.match(bucket_name)
        if match:
            return f"{match.group(1)}-{match.group(2)}"

    return None


def _resolve_account_id_from_context(resource: Resource, selected_context: dict[str, Any]) -> str | None:
    all_pack_data = selected_context.get("pack_data") or {}
    shared_data = all_pack_data.get("shared/account_abbreviations") or {}
    abbr_to_id = shared_data.get("abbreviation_to_account_id") or {}

    if not isinstance(abbr_to_id, dict):
        return None

    abbr = _extract_account_abbreviation(resource)
    if not abbr:
        return None

    account_id = abbr_to_id.get(abbr)
    if account_id is None:
        return None

    text = str(account_id).strip()
    if _is_valid_aws_account_id(text):
        return text

    return None


def _fallback_derivations(
    resource: Resource,
    unresolved_fields: list[str],
    spec_map: dict[str, FieldSpec],
    selected_context: dict[str, Any],
) -> dict[str, Any]:
    """
    Conservative deterministic fallback for fields that are straightforward.
    This only fills values when confidence is high.
    """
    derived: dict[str, Any] = {}

    # Default from spec (e.g., aws_region)
    for field_name in unresolved_fields:
        spec = spec_map.get(field_name)
        if spec and spec.default is not None:
            derived[field_name] = spec.default

    # Basic description template fallback when known inputs exist.
    if "bucket_description" in unresolved_fields and "bucket_description" not in derived:
        usage_type = resource.fields.get("usage_type")
        entity = str(resource.fields.get("enterprise_or_func_name") or "").strip().lower()
        subgroup = str(resource.fields.get("enterprise_or_func_subgrp_name") or "").strip().lower()
        owner = "-".join(part for part in [entity, subgroup] if part)
        if usage_type in _SUFFIX_MAP and owner:
            derived["bucket_description"] = f"{usage_type} bucket for {owner}."

    # Resolve account ID deterministically from account abbreviation mapping.
    if "aws_account_id" in unresolved_fields and "aws_account_id" not in derived:
        mapped_account_id = _resolve_account_id_from_context(resource, selected_context)
        if mapped_account_id:
            derived["aws_account_id"] = mapped_account_id

    return derived


def _build_user_prompt(
    resource: Resource,
    requested_fields: list[str],
    selected_context: dict[str, Any],
) -> str:
    payload = {
        "resource_type": resource.resource_type,
        "requested_fields": requested_fields,
        "known_fields": resource.fields,
        "selected_context": selected_context.get("field_context", {}),
        "prompt_contract": selected_context.get("prompt_contract"),
        "instructions": {
            "output": "Return JSON only",
            "shape": {
                "derived_fields": {"<field>": "<value-or-null>"},
                "unresolved_fields": ["<field>"],
                "sources_used": ["<pack id>"]
            }
        }
    }
    return json.dumps(payload, indent=2, ensure_ascii=True)


async def derive_resource_fields(resource: Resource, selected_context: dict[str, Any]) -> dict[str, Any]:
    """
    Derive missing derivable fields for a resource.

    Returns:
      {
        "derived": {field: value},
        "unresolved": [field],
        "sources_used": [pack ids],
      }
    """
    spec_map = _field_spec_map(resource.resource_type)

    requested_fields = [
        spec.name
        for spec in spec_map.values()
        if spec.derivable and spec.name not in resource.fields
    ]

    if not requested_fields:
        return {"derived": {}, "unresolved": [], "sources_used": []}

    user_prompt = _build_user_prompt(resource, requested_fields, selected_context)

    model_result = await chat_json(
        system_prompt=(
            "You derive infrastructure fields from provided context packs. "
            "Use only given context and known fields. "
            "Return strictly valid JSON with the required shape."
        ),
        user_message=user_prompt,
    )

    raw_derived = model_result.get("derived_fields") or {}
    unresolved = set(model_result.get("unresolved_fields") or [])
    sources_used = model_result.get("sources_used") or []

    derived: dict[str, Any] = {}
    for field_name in requested_fields:
        value = raw_derived.get(field_name)
        spec = spec_map.get(field_name)
        if spec is None:
            unresolved.add(field_name)
            continue
        if _validate_value(spec, value):
            derived[field_name] = value
        else:
            unresolved.add(field_name)

    # Deterministic fallback for simple cases/defaults
    fallback = _fallback_derivations(resource, list(unresolved), spec_map, selected_context)
    for field_name, value in fallback.items():
        spec = spec_map.get(field_name)
        if spec and _validate_value(spec, value):
            derived[field_name] = value
            unresolved.discard(field_name)

    # Keep unresolved only for fields that were actually requested and still missing
    unresolved_final = [
        field_name
        for field_name in requested_fields
        if field_name not in derived
    ]

    return {
        "derived": derived,
        "unresolved": unresolved_final,
        "sources_used": sources_used,
    }
