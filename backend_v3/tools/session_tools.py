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
        await save_resource(session.session_id, resource)
        created.append({"resource_id": rid, "resource_type": rtype, "status": "collecting"})

    result = {"created": created}
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
