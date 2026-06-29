"""Context registry — loads and indexes resource docs and rules by resource type."""
from __future__ import annotations

from pathlib import Path

CONTEXT_DIR = Path(__file__).resolve().parent

# Supported resource types and their context doc filenames
SUPPORTED_RESOURCES = {
    "s3": "resources/s3.md",
    "glue_db": "resources/glue_db.md",
    "iam": "resources/iam.md",
    "resource_policy": "resources/resource_policy.md",
    "smus_project": "resources/smus_project.md",
    "smus_role": "resources/smus_role.md",
}


def get_resource_context(resource_type: str) -> str | None:
    """Load the context document for a given resource type.

    Returns the file content as a string, or None if the resource
    type is not supported or the file doesn't exist yet.
    """
    filename = SUPPORTED_RESOURCES.get(resource_type)
    if not filename:
        return None
    path = CONTEXT_DIR / filename
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def get_supported_resource_types() -> list[str]:
    """Return list of supported resource type keys."""
    return list(SUPPORTED_RESOURCES.keys())


def is_supported_resource(resource_type: str) -> bool:
    """Check if a resource type is in the supported catalog."""
    return resource_type in SUPPORTED_RESOURCES
