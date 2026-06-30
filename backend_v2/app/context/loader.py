"""
Context loader — reads YAML spec files and converts them to FieldSpec objects.

Each YAML file in context/specs/ defines one resource type with its fields.
This replaces the hardcoded field_specs.py approach.
"""
import yaml
import logging
from pathlib import Path
from app.models.state import FieldSpec

logger = logging.getLogger(__name__)

# Default location: backend_v2/context/specs/
_DEFAULT_SPECS_DIR = Path(__file__).resolve().parent.parent.parent / "context" / "specs"


def load_resource_spec(file_path: Path) -> tuple[str, list[FieldSpec]]:
    """
    Load a single YAML spec file and return (resource_type, list of FieldSpec).
    Raises ValueError if the file is malformed.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    resource_type = data.get("resource_type")
    if not resource_type:
        raise ValueError(f"Missing 'resource_type' in {file_path.name}")

    raw_fields = data.get("fields", [])
    if not raw_fields:
        raise ValueError(f"No fields defined in {file_path.name}")

    specs = []
    for entry in raw_fields:
        spec = FieldSpec(
            name=entry["name"],
            required=entry.get("required", True),
            description=entry.get("description", ""),
            options=entry.get("options"),
            validation=entry.get("validation"),
            depends_on=entry.get("depends_on"),
            derivable=entry.get("derivable", False),
            default=entry.get("default"),
        )
        specs.append(spec)

    logger.info("Loaded %d fields for '%s' from %s", len(specs), resource_type, file_path.name)
    return resource_type, specs


def load_all_specs(specs_dir: Path = _DEFAULT_SPECS_DIR) -> dict[str, list[FieldSpec]]:
    """
    Load all .yaml files from the specs directory.
    Returns a dict of {resource_type: [FieldSpec, ...]}.
    """
    if not specs_dir.exists():
        raise FileNotFoundError(f"Specs directory not found: {specs_dir}")

    all_specs: dict[str, list[FieldSpec]] = {}

    for yaml_file in sorted(specs_dir.glob("*.yaml")):
        try:
            resource_type, specs = load_resource_spec(yaml_file)
            all_specs[resource_type] = specs
        except Exception as e:
            logger.error("Failed to load %s: %s", yaml_file.name, e)
            raise

    if not all_specs:
        raise ValueError(f"No spec files found in {specs_dir}")

    logger.info("Loaded specs for %d resource types: %s", len(all_specs), list(all_specs.keys()))
    return all_specs
