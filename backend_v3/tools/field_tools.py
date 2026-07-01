"""Field tools — set/get field values and resource specifications."""
from __future__ import annotations

import json
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
        options = field_spec.get("options", [])
        if options:
            for opt in options:
                if opt.lower() == str_value.lower():
                    return opt

        break

    return str_value


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
            if normalized not in field_spec["options"]:
                errors[field_name] = f"Must be one of: {field_spec['options']}"
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
