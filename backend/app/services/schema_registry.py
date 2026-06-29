"""
Resource Schema Registry

Loads resource guide MD files from data/resources/ at startup.
Each MD file is the SINGLE SOURCE OF TRUTH for that resource type —
it contains fields, validation, normalization, templates, everything.

No more validation_details.json, validation_rules.md, yaml_templates.md.
"""
import logging
from pathlib import Path
from typing import Optional

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

RESOURCES_DIR = DATA_DIR / "resources"

# Map of resource type key → MD filename
RESOURCE_FILES = {
    "s3": "s3.md",
    "glue_db": "glue_db.md",
    "iam": "iam.md",
}

# Trigger keywords per resource — used for detection routing
RESOURCE_TRIGGERS = {
    "s3": ["s3", "bucket", "storage", "create s3", "new bucket"],
    "glue_db": ["glue", "database", "catalog", "glue db", "glue database",
                 "new database", "create database", "configure glue"],
    "iam": ["iam", "role", "permission", "create role", "iam role",
            "new role", "configure iam", "role for"],
}


class ResourceSchema:
    """Holds the loaded context for a single resource type."""

    def __init__(self, resource_type: str, context: str):
        self.resource_type = resource_type
        self.context = context  # Full MD file content


class SchemaRegistry:
    """
    Loads and serves resource guide MD files.
    Call load() once at startup.
    """

    def __init__(self):
        self._schemas: dict[str, ResourceSchema] = {}

    def load(self):
        """Load all resource MD files from data/resources/."""
        for rtype, filename in RESOURCE_FILES.items():
            path = RESOURCES_DIR / filename
            if path.exists():
                content = path.read_text(encoding="utf-8")
                self._schemas[rtype] = ResourceSchema(rtype, content)
                logger.info(f"Loaded resource guide: {filename} ({len(content)} chars)")
            else:
                logger.warning(f"Resource guide not found: {path}")

    def get_schema(self, resource_type: str) -> Optional[ResourceSchema]:
        """Get schema for a resource type."""
        return self._schemas.get(resource_type)

    def get_resource_context(self, resource_type: str) -> str:
        """Get the full MD content for a resource type."""
        schema = self._schemas.get(resource_type)
        return schema.context if schema else ""

    def get_supported_types(self) -> list[str]:
        """Return all loaded resource types."""
        return list(self._schemas.keys())

    def get_primary_types(self) -> list[str]:
        """Return the primary resource types."""
        return [t for t in ["s3", "glue_db", "iam"] if t in self._schemas]

    def get_triggers_summary(self) -> str:
        """Build a formatted string of resource types and their trigger keywords."""
        lines = []
        for rtype, triggers in RESOURCE_TRIGGERS.items():
            if rtype in self._schemas:
                lines.append(f"- **{rtype}**: {', '.join(triggers)}")
        return "\n".join(lines)


# ── Singleton ─────────────────────────────────────────────────

schema_registry = SchemaRegistry()
