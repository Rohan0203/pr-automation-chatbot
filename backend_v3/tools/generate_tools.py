"""Generate tools — produce final YAML from confirmed resource fields."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml as pyyaml

from models.state import ResourceStatus
from tools.session_tools import _get_session
from db.repository import save_resource

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_resource_config(resource_type: str) -> dict:
    path = _CONFIG_DIR / "resources" / f"{resource_type}.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return pyyaml.safe_load(f)


def _generate_s3_yaml(all_fields: dict[str, Any], config: dict) -> str:
    """Generate S3 YAML following field order and quoting rules."""
    yaml_config = config.get("yaml_output", {})
    field_order = yaml_config.get("field_order", [])
    quoting = yaml_config.get("quoting", {})
    conditional = yaml_config.get("conditional_fields", [])

    lines = []
    usage_type = all_fields.get("usage_type", "")

    for field_name in field_order:
        # Check conditional fields
        is_conditional = False
        for cond in conditional:
            if cond["field"] == field_name:
                is_conditional = True
                condition = cond.get("include_when", "")
                if "Scripts" in condition and usage_type != "Scripts":
                    break  # skip this field
                # Include with fixed value
                lines.append(f"{field_name}: {cond['value']}")
                break

        if is_conditional:
            continue

        value = all_fields.get(field_name)
        if value is None:
            continue

        # Apply quoting rules
        quote_rule = quoting.get(field_name, quoting.get("default", "none"))

        if quote_rule == "single":
            lines.append(f"{field_name}: '{value}'")
        elif quote_rule == "double_if_spaces" and " " in str(value):
            lines.append(f'{field_name}: "{value}"')
        elif quote_rule == "double_if_empty" and value == "":
            lines.append(f'{field_name}: ""')
        else:
            lines.append(f"{field_name}: {value}")

    return "\n".join(lines) + "\n"


def _condition_matches(condition: str, all_fields: dict[str, Any]) -> bool:
    if "==" not in condition:
        return False
    field_name, expected = condition.split("==", 1)
    field_name = field_name.strip()
    expected = expected.strip().strip('"').strip("'")
    return str(all_fields.get(field_name, "")) == expected


def _format_yaml_value(field_name: str, value: Any, quoting: dict[str, str]) -> str:
    quote_rule = quoting.get(field_name, quoting.get("default", "none"))
    if quote_rule == "double":
        return f'"{value}"'
    if quote_rule == "single":
        return f"'{value}'"
    return str(value)


def _generate_ordered_yaml(all_fields: dict[str, Any], config: dict) -> str:
    yaml_config = config.get("yaml_output", {})
    field_order = yaml_config.get("field_order", [])
    quoting = yaml_config.get("quoting", {})
    conditional = yaml_config.get("conditional_fields", [])

    lines = []
    for field_name in field_order:
        include_field = True
        for cond in conditional:
            if cond.get("field") != field_name:
                continue
            include_field = _condition_matches(cond.get("include_when", ""), all_fields)
            break

        if not include_field:
            continue

        value = all_fields.get(field_name)
        if value is None or value == "":
            continue

        lines.append(f"{field_name}: {_format_yaml_value(field_name, value, quoting)}")

    return "\n".join(lines) + "\n"


async def generate_yaml(resource_id: str, **kwargs) -> str:
    """Generate YAML for a confirmed resource."""
    session = _get_session()
    resource = session.get_resource(resource_id)

    if not resource:
        return json.dumps({"error": f"Resource '{resource_id}' not found"})

    if resource.status not in (ResourceStatus.CONFIRMING, ResourceStatus.DONE):
        return json.dumps({"error": f"Resource must be confirmed before YAML generation. Current status: {resource.status.value}"})

    config = _load_resource_config(resource.resource_type)
    all_fields = resource.all_fields

    # Route to resource-specific generator
    if resource.resource_type == "s3":
        yaml_output = _generate_s3_yaml(all_fields, config)
    elif resource.resource_type in {"gluedb", "glue_db"}:
        yaml_output = _generate_ordered_yaml(all_fields, config)
    else:
        # Generic: just dump fields in order
        yaml_output = pyyaml.dump(all_fields, default_flow_style=False)

    # Mark as done and store output
    resource.yaml_output = yaml_output
    resource.status = ResourceStatus.DONE
    await save_resource(session.session_id, resource)

    return json.dumps({
        "resource_id": resource.resource_id,
        "status": "done",
        "yaml": yaml_output,
    })
