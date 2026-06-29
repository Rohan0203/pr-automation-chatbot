"""
YAML Validator — Python-side validation of LLM-generated YAML.

Runs between LLM generation and user preview to catch:
1. Syntax errors (yaml.safe_load fails)
2. Missing required fields
3. Hallucinated fields (keys not in the resource guide)

Design: Lightweight, no LLM calls. Uses known field definitions
per resource type extracted from the MD guides.
"""
import logging
from dataclasses import dataclass, field

import yaml

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# KNOWN FIELDS PER RESOURCE TYPE
# These are the top-level YAML keys that the resource guides define.
# Any key NOT in this set is a hallucination.
# ═══════════════════════════════════════════════════════════════

KNOWN_FIELDS: dict[str, set[str]] = {
    "s3": {
        "intake_id",
        "bucket_name",
        "bucket_description",
        "aws_account_id",
        "aws_region",
        "usage_type",
        "enterprise_or_func_name",
        "enterprise_or_func_subgrp_name",
        "versioning_enabled",
        "public_access_blocked",
        "encryption_enabled",
        "encryption_type",
        "encryption_key_arn",
    },
    "glue_db": {
        "intake_id",
        "database_name",
        "database_s3_location",
        "database_description",
        "aws_account_id",
        "region",
        "data_env",
        "data_construct",
        "data_layer",
        "source_name",
        "data_product_name",
        "data_classification",
        "data_privacy",
        "enterprise_or_func_name",
        "enterprise_or_func_subgrp_name",
        "data_owner_email",
        "data_owner_github_uname",
        "data_leader",
    },
    "iam": {
        "intake_id",
        "role_name",
        "role_description",
        "aws_account_id",
        "enterprise_or_func_name",
        "enterprise_or_func_subgrp_name",
        "role_owner",
        "data_env",
        "usage_type",
        "principal_role_arn",
        "data_prefixes",
        "execution_asset_prefixes",
        "glue_crawler",
        "glue_databases",
        "enable_glue_interactive_session",
        "snowflake_iceberg_support",
        "max_session_duration",
        "stsExternalIds",
        "athena_access_config",
        "glue_job_access_config",
    },
}

# Required fields — must be present in the YAML output
REQUIRED_FIELDS: dict[str, set[str]] = {
    "s3": {"intake_id", "bucket_name", "aws_account_id"},
    "glue_db": {"intake_id", "database_name", "aws_account_id"},
    "iam": {"intake_id", "role_name", "aws_account_id"},
}


@dataclass
class ValidationResult:
    """Result of YAML validation."""
    valid: bool
    yaml_data: dict | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def error_summary(self) -> str:
        """One-line summary of all errors for LLM retry prompt."""
        return "; ".join(self.errors)


def validate_yaml(yaml_string: str, resource_type: str, collected_fields: dict) -> ValidationResult:
    """
    Validate LLM-generated YAML before showing it to the user.

    Checks:
    1. YAML syntax (yaml.safe_load)
    2. Required fields present
    3. No hallucinated fields (keys not in resource guide)

    Args:
        yaml_string: The raw YAML string from the LLM.
        resource_type: e.g. "s3", "glue_db", "iam"
        collected_fields: The fields the agent collected from the user.

    Returns:
        ValidationResult with valid flag, errors, and warnings.
    """
    errors = []
    warnings = []

    # ── 1. Syntax check ──
    try:
        data = yaml.safe_load(yaml_string)
    except yaml.YAMLError as e:
        return ValidationResult(
            valid=False,
            errors=[f"YAML syntax error: {e}"],
        )

    if not isinstance(data, dict):
        return ValidationResult(
            valid=False,
            errors=["YAML did not parse to a dictionary. Expected key-value pairs."],
        )

    yaml_keys = set(data.keys())

    # ── 2. Required fields check ──
    required = REQUIRED_FIELDS.get(resource_type, set())
    missing = required - yaml_keys
    for field_name in missing:
        # Check if it was in collected_fields (LLM forgot to include it)
        if field_name in collected_fields:
            errors.append(f"Missing required field '{field_name}' (was collected but not in YAML)")
        else:
            warnings.append(f"Required field '{field_name}' not in YAML or collected fields")

    # ── 3. Hallucination detection ──
    known = KNOWN_FIELDS.get(resource_type, set())
    if known:
        unknown_keys = yaml_keys - known
        # Allow comment-like keys that YAML parsers might pick up, but flag others
        for key in unknown_keys:
            errors.append(f"Unknown field '{key}' — not in {resource_type} resource guide")

    # ── 4. Collected fields consistency ──
    # Check that key collected fields actually appear in the YAML
    for field_name, value in collected_fields.items():
        if field_name in known and field_name in required and field_name not in yaml_keys:
            # Already caught in step 2, skip duplicate
            pass

    is_valid = len(errors) == 0

    if errors:
        logger.warning(
            f"YAML validation failed for {resource_type}: {errors}"
        )
    if warnings:
        logger.info(f"YAML validation warnings for {resource_type}: {warnings}")

    return ValidationResult(
        valid=is_valid,
        yaml_data=data,
        errors=errors,
        warnings=warnings,
    )
