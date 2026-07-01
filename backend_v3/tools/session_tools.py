"""Session tools — manage session state and resources."""
from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any

from models.state import Session, Resource, ResourceStatus
from db.repository import save_resource

# Per-task session context — safe under concurrent async requests
_session_var: ContextVar[Session | None] = ContextVar("_session_var", default=None)


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
    created = []

    for spec in resources:
        rtype = spec.get("resource_type", "").strip().lower()
        if not rtype:
            continue

        rid = session.next_resource_id(rtype)
        resource = Resource(resource_id=rid, resource_type=rtype)
        session.resources.append(resource)
        await save_resource(session.session_id, resource)
        created.append({"resource_id": rid, "resource_type": rtype, "status": "collecting"})

    return json.dumps({"created": created})


async def drop_resource(resource_id: str, **kwargs) -> str:
    """Drop a resource by ID."""
    session = _get_session()
    resource = session.get_resource(resource_id)

    if not resource:
        return json.dumps({"error": f"Resource '{resource_id}' not found"})

    resource.status = ResourceStatus.DROPPED
    await save_resource(session.session_id, resource)
    return json.dumps({"dropped": resource.resource_id})
