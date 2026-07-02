"""Session tools — manage session state and resources."""
from __future__ import annotations

import json
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import yaml as pyyaml

from models.state import Session, Resource, ResourceStatus
from db.repository import save_resource

# Per-task session context — safe under concurrent async requests
_session_var: ContextVar[Session | None] = ContextVar("_session_var", default=None)

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_supported_resources: list[str] | None = None


def _load_resource_config(resource_type: str) -> dict | None:
    """Load resource config YAML."""
    path = _CONFIG_DIR / "resources" / f"{resource_type}.yaml"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return pyyaml.safe_load(f)


def _prefill_from_session(session: Session, new_resource: Resource) -> dict[str, Any]:
    """Auto-fill fields on a new resource from existing resources in the session.

    Returns dict of prefilled field names → values (for reporting to agent).
    """
    config = _load_resource_config(new_resource.resource_type)
    if not config:
        return {}

    valid_fields = {fs["name"] for fs in config.get("collect_fields", [])}

    # Gather values from other resources (prefer most recent first)
    existing = [
        r for r in session.resources
        if r.resource_id != new_resource.resource_id and r.collected_fields
    ]

    prefilled = {}
    for r in reversed(existing):  # most recent first wins
        for field_name, value in r.collected_fields.items():
            if field_name in valid_fields and field_name not in new_resource.collected_fields:
                new_resource.collected_fields[field_name] = value
                prefilled[field_name] = value

    return prefilled


def _all_required_present(resource: Resource, config: dict) -> bool:
    """Check if all required collect_fields are present on the resource."""
    for field_spec in config.get("collect_fields", []):
        is_required = field_spec.get("required", False)
        allow_empty = field_spec.get("allow_empty", False)

        # Handle required_when condition
        required_when = field_spec.get("required_when")
        if required_when and not is_required:
            if " == " in required_when:
                cond_field, cond_value = required_when.split(" == ", 1)
                actual = resource.collected_fields.get(cond_field.strip(), "")
                if str(actual).strip() == cond_value.strip():
                    is_required = True
                    allow_empty = False

        if not is_required:
            continue
        if allow_empty:
            continue
        if field_spec["name"] not in resource.collected_fields:
            return False
    return True


def _load_supported_resources() -> list[str]:
    """Load supported resource types from settings.yaml."""
    global _supported_resources
    if _supported_resources is None:
        path = _CONFIG_DIR / "settings.yaml"
        with open(path, "r", encoding="utf-8") as f:
            data = pyyaml.safe_load(f)
        _supported_resources = data.get("supported_resources", [])
    return _supported_resources


def bind_session(session: Session):
    """Bind the active session for tools to operate on (async-safe per-task)."""
    _session_var.set(session)


def _get_session() -> Session:
    session = _session_var.get()
    if session is None:
        raise RuntimeError("No active session bound")
    return session


async def get_session_state(**kwargs) -> str:
    """Return current session state as JSON."""
    session = _get_session()
    return json.dumps(session.to_state_summary(), indent=2)


async def create_resources(resources: list[dict], **kwargs) -> str:
    """Create new resources and add them to the session."""
    from tools.derive_tools import derive_fields

    session = _get_session()
    supported = _load_supported_resources()
    created = []
    errors = []

    for spec in resources:
        rtype = spec.get("resource_type", "").strip().lower()
        if not rtype:
            continue

        # Scope control: reject unsupported resource types
        if rtype not in supported:
            errors.append({
                "resource_type": rtype,
                "error": f"'{rtype}' is not supported yet. Currently available: {', '.join(supported)}",
            })
            continue

        rid = session.next_resource_id(rtype)
        resource = Resource(resource_id=rid, resource_type=rtype)
        session.resources.append(resource)

        # 1. Apply initial_fields from user's message (highest priority)
        initial = spec.get("initial_fields") or {}
        config = _load_resource_config(rtype)
        valid_fields = {fs["name"] for fs in config.get("collect_fields", [])} if config else set()
        applied_initial = {}
        for k, v in initial.items():
            if k in valid_fields and v:
                resource.collected_fields[k] = v
                applied_initial[k] = v

        # 2. Prefill remaining fields from session history (won't overwrite initial_fields)
        prefilled = _prefill_from_session(session, resource)

        # 3. Check if all required fields are now present → auto-derive
        auto_derived = None
        if config and _all_required_present(resource, config):
            derive_result = await derive_fields(resource_id=rid)
            try:
                auto_derived = json.loads(derive_result)
            except (json.JSONDecodeError, TypeError):
                auto_derived = derive_result

        await save_resource(session.session_id, resource)
        entry: dict[str, Any] = {
            "resource_id": rid,
            "resource_type": rtype,
            "status": resource.status.value,
        }
        if applied_initial:
            entry["initial_fields_set"] = applied_initial
        if prefilled:
            entry["prefilled_fields"] = prefilled
        if auto_derived:
            entry["auto_derived"] = auto_derived
        created.append(entry)

    result: dict[str, Any] = {"created": created}
    if errors:
        result["errors"] = errors
    return json.dumps(result)


async def drop_resource(resource_id: str, **kwargs) -> str:
    """Drop a resource by ID."""
    session = _get_session()
    resource = session.get_resource(resource_id)

    if not resource:
        return json.dumps({"error": f"Resource '{resource_id}' not found"})

    resource.status = ResourceStatus.DROPPED
    await save_resource(session.session_id, resource)
    return json.dumps({"dropped": resource.resource_id})


async def clone_resource(source_resource_id: str, overrides: dict | None = None, **kwargs) -> str:
    """Clone a resource from an existing one, optionally overriding specific fields."""
    session = _get_session()
    source = session.get_resource(source_resource_id)

    if not source:
        return json.dumps({"error": f"Source resource '{source_resource_id}' not found"})

    # Create new resource of the same type
    rid = session.next_resource_id(source.resource_type)
    new_resource = Resource(resource_id=rid, resource_type=source.resource_type)

    # Copy collected fields from source
    new_resource.collected_fields = dict(source.collected_fields)

    # Apply overrides
    if overrides:
        for k, v in overrides.items():
            new_resource.collected_fields[k] = v

    session.resources.append(new_resource)
    await save_resource(session.session_id, new_resource)

    return json.dumps({
        "cloned_from": source.resource_id,
        "new_resource_id": rid,
        "resource_type": source.resource_type,
        "collected_fields": new_resource.collected_fields,
        "status": "collecting",
    })
