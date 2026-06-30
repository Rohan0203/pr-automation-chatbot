"""
Context registry — single access point for resource field specs.

Loads specs from YAML files on first access and caches them.
All other modules should use this instead of importing field_specs.py directly.
"""
import logging
from app.models.state import FieldSpec
from app.context.loader import load_all_specs

logger = logging.getLogger(__name__)

# Loaded on first access, cached after that
_specs_cache: dict[str, list[FieldSpec]] | None = None


def _ensure_loaded() -> dict[str, list[FieldSpec]]:
    """Load specs from YAML if not already cached."""
    global _specs_cache
    if _specs_cache is None:
        _specs_cache = load_all_specs()
    return _specs_cache


def get_field_specs(resource_type: str) -> list[FieldSpec]:
    """Get the field spec list for a given resource type. Returns [] if unknown."""
    return _ensure_loaded().get(resource_type, [])


def get_all_field_specs() -> dict[str, list[FieldSpec]]:
    """Get the full dict of {resource_type: [FieldSpec, ...]}."""
    return _ensure_loaded()


def get_supported_resources() -> list[str]:
    """Get list of all supported resource type names."""
    return list(_ensure_loaded().keys())


def reload_specs():
    """Force reload specs from YAML files. Useful after editing spec files."""
    global _specs_cache
    _specs_cache = None
    _ensure_loaded()
    logger.info("Specs reloaded")
