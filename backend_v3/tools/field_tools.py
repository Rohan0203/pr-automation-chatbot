"""Field tools — set/get field values and resource specifications."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from models.state import ResourceStatus
from tools.session_tools import _get_session
from db.repository import save_resource

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_CONTEXT_DIR = Path(__file__).resolve().parent.parent / "context"

# Cache for loaded resource configs
_resource_configs: dict[str, dict] = {}


def _load_resource_config(resource_type: str) -> dict | None:
    """Load the YAML config for a resource type."""
    if resource_type in _resource_configs:
        return _resource_configs[resource_type]

    path = _CONFIG_DIR / "resources" / f"{resource_type}.yaml"
    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    _resource_configs[resource_type] = config
    return config


def _normalize_value(field_name: str, value: Any, config: dict) -> Any:
    """Normalize a field value using the resource config's normalize map."""
    if value is None:
        return value

    str_value = str(value).strip()

    # Check collect_fields for normalize rules
    for field_spec in config.get("collect_fields", []):
        if field_spec["name"] != field_name:
            continue

        # Case normalization
        if field_spec.get("normalize_case") == "upper":
            return str_value.upper()

        # Lookup normalization
        normalize_map = field_spec.get("normalize", {})
        if normalize_map:
            lookup = str_value.lower()
            if lookup in normalize_map:
                return normalize_map[lookup]

        # If has options, try case-insensitive match
        # Options can be plain strings or dicts with "value" key
        options = field_spec.get("options", [])
        if options:
            option_values = _extract_option_values(options)
            for opt in option_values:
                if opt.lower() == str_value.lower():
                    return opt

        break

    return str_value


def _extract_option_values(options: list) -> list[str]:
    """Extract option values from either plain strings or dicts with 'value' key."""
    values = []
    for opt in options:
        if isinstance(opt, dict):
            values.append(opt["value"])
        else:
            values.append(str(opt))
    return values


async def set_fields(resource_id: str, fields: dict, **kwargs) -> str:
    """Set field values on a resource with normalization."""
    session = _get_session()
    resource = session.get_resource(resource_id)

    if not resource:
        return json.dumps({"error": f"Resource '{resource_id}' not found"})

    config = _load_resource_config(resource.resource_type)
    if not config:
        return json.dumps({"error": f"No config for resource type '{resource.resource_type}'"})

    set_fields_result = {}
    errors = {}

    for field_name, value in fields.items():
        normalized = _normalize_value(field_name, value, config)
        # Basic validation: check options if defined
        field_spec = next(
            (f for f in config.get("collect_fields", []) if f["name"] == field_name),
            None,
        )
        if field_spec and field_spec.get("options"):
            option_values = _extract_option_values(field_spec["options"])
            if normalized not in option_values:
                errors[field_name] = f"Must be one of: {option_values}"
                continue

        # Regex validation (e.g. intake_id pattern)
        if field_spec:
            validation = field_spec.get("validation")
            if validation and not re.match(validation, str(normalized)):
                errors[field_name] = f"Invalid format. Must match pattern: {validation}"
                continue

        resource.collected_fields[field_name] = normalized
        set_fields_result[field_name] = normalized

    # Check if all required collect_fields are now set
    all_collected = True
    missing = []
    for field_spec in config.get("collect_fields", []):
        if field_spec.get("required", False):
            if field_spec["name"] not in resource.collected_fields:
                if not field_spec.get("allow_empty", False) or field_spec["name"] not in resource.collected_fields:
                    all_collected = False
                    missing.append(field_spec["name"])

    await save_resource(session.session_id, resource)

    result = {
        "resource_id": resource.resource_id,
        "set": set_fields_result,
        "errors": errors if errors else None,
        "collection_complete": all_collected,
        "missing_fields": missing if not all_collected else None,
    }
    return json.dumps({k: v for k, v in result.items() if v is not None})


async def get_resource_info(resource_type: str, **kwargs) -> str:
    """Get resource context (MD file) for the LLM to understand the resource."""
    # Load the MD context file — this is what the LLM reads
    context_path = _CONTEXT_DIR / "resources" / f"{resource_type}.md"
    if context_path.exists():
        context_md = context_path.read_text(encoding="utf-8")
    else:
        context_md = f"No context available for resource type '{resource_type}'."

    # Also include a brief field summary from config
    config = _load_resource_config(resource_type)
    if config:
        collect = [f["name"] for f in config.get("collect_fields", [])]
        derive = [f["name"] for f in config.get("derive_fields", [])]
        summary = f"\n\n---\nFields to collect from user: {collect}\nFields to derive automatically: {derive}"
    else:
        summary = ""

    return context_md + summary


async def edit_derived_field(resource_id: str, field_name: str, value: str, **kwargs) -> str:
    """Edit a derived field (user override). Validates against editability rules in config."""
    session = _get_session()
    resource = session.get_resource(resource_id)

    if not resource:
        return json.dumps({"error": f"Resource '{resource_id}' not found"})

    if resource.status not in (ResourceStatus.CONFIRMING, ResourceStatus.COLLECTING):
        return json.dumps({"error": f"Cannot edit — resource status is {resource.status.value}"})

    config = _load_resource_config(resource.resource_type)
    if not config:
        return json.dumps({"error": f"No config for resource type '{resource.resource_type}'"})

    # Find the derive field spec
    derive_spec = next(
        (f for f in config.get("derive_fields", []) if f["name"] == field_name),
        None,
    )
    if not derive_spec:
        return json.dumps({"error": f"'{field_name}' is not a derived field"})

    editable = derive_spec.get("editable", "locked")
    if editable == "locked":
        return json.dumps({"error": f"'{field_name}' is locked and cannot be edited"})

    # Validate constrained fields
    if editable == "constrained":
        validation = derive_spec.get("validation")
        if validation and not re.match(validation, str(value)):
            return json.dumps({"error": f"Invalid format for {field_name}. Must match: {validation}"})

    # Validate free fields
    if editable == "free":
        max_length = derive_spec.get("max_length", 256)
        if len(str(value)) > max_length:
            return json.dumps({"error": f"'{field_name}' exceeds max length of {max_length}"})

    # Store as user override
    resource.user_overrides[field_name] = value
    await save_resource(session.session_id, resource)

    return json.dumps({
        "resource_id": resource.resource_id,
        "field": field_name,
        "old_value": resource.derived_fields.get(field_name),
        "new_value": value,
        "source": "user_override",
    })
