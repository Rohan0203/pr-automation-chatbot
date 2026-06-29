"""
Field specifications for each resource type.
Derived from actual approved PR YAMLs — this is the source of truth for what fields exist.
"""
from app.models.state import FieldSpec

# ─── S3 Fields ────────────────────────────────────────────────────────────────

S3_FIELDS: list[FieldSpec] = [
    FieldSpec(
        name="intake_id",
        description="Request tracking ID (e.g. M0000485)",
        validation="Alphanumeric, starts with M or I, followed by digits",
    ),
    FieldSpec(
        name="bucket_name",
        description="S3 bucket name following naming convention",
        validation="3-63 chars, lowercase + hyphens + numbers. Pattern: {env}-{account_prefix}-{enterprise_lower}-{purpose}",
    ),
    FieldSpec(
        name="bucket_description",
        description="Human-readable description of the bucket's purpose",
        validation="1-256 chars, wrapped in double quotes in YAML",
    ),
    FieldSpec(
        name="aws_account_id",
        description="AWS account ID where the bucket will be created",
        validation="12-digit number, single-quoted in YAML",
        options=["438465132548", "578647603827", "904233109241", "650252464149",
                 "339712742964", "113552184874", "058264261952", "851725225495",
                 "533267408704", "471112630934"],
    ),
    FieldSpec(
        name="aws_region",
        derivable=True,
        default="us-east-1",
        description="AWS region (always us-east-1)",
    ),
    FieldSpec(
        name="usage_type",
        description="Purpose category of the bucket",
        options=["Source", "DataProduct", "Scripts", "EngAssets"],
    ),
    FieldSpec(
        name="enterprise_or_func_name",
        description="Enterprise or functional area",
        options=["AGTR", "CORP", "FOOD", "SPEC"],
    ),
    FieldSpec(
        name="enterprise_or_func_subgrp_name",
        description="Subgroup within the enterprise (can be empty string)",
        validation="Short uppercase string e.g. EMEA, TDA, HR, FIN. Use empty string if not applicable",
    ),
]

# ─── Glue DB Fields ──────────────────────────────────────────────────────────

GLUE_DB_FIELDS: list[FieldSpec] = [
    FieldSpec(
        name="intake_id",
        description="Request tracking ID (e.g. M0000934)",
        validation="Starts with M, followed by digits, max 10 chars",
    ),
    FieldSpec(
        name="database_name",
        derivable=True,
        description="Derived from naming convention using other fields",
    ),
    FieldSpec(
        name="database_s3_location",
        derivable=True,
        description="Derived S3 path for the database",
    ),
    FieldSpec(
        name="database_description",
        derivable=True,
        description="Auto-generated description",
    ),
    FieldSpec(
        name="aws_account_id",
        derivable=True,
        description="Derived from data_layer + enterprise + environment",
    ),
    FieldSpec(
        name="region",
        derivable=True,
        default="us-east-1",
        description="AWS region (always us-east-1)",
    ),
    FieldSpec(
        name="data_construct",
        description="Whether this is a Source or DataProduct database",
        options=["Source", "DataProduct"],
    ),
    FieldSpec(
        name="data_env",
        description="Environment for the database",
        options=["dev", "prd"],
    ),
    FieldSpec(
        name="data_layer",
        description="Data layer in the lakehouse architecture",
        options=["raw", "raw_serving", "curated", "serving", "internal"],
    ),
    FieldSpec(
        name="source_name",
        description="Name of the source system (lowercase, underscores, no spaces)",
        validation="Lowercase letters, digits, and underscores only",
        depends_on={"data_construct": "Source"},
    ),
    FieldSpec(
        name="data_product_name",
        description="Name of the data product (lowercase, underscores, no spaces)",
        validation="Lowercase letters, digits, and underscores only",
        depends_on={"data_construct": "DataProduct"},
    ),
    FieldSpec(
        name="data_classification",
        description="Data sensitivity classification",
        options=["Confidential - General Use", "Confidential - Limited", "Confidential - Restricted", "Internal"],
        default="Confidential - General Use",
    ),
    FieldSpec(
        name="data_privacy",
        description="Data privacy designation",
        default="None",
        validation="Usually 'None' or empty string",
    ),
    FieldSpec(
        name="enterprise_or_func_name",
        description="Enterprise or functional area",
        options=["AGTR", "CORP", "FOOD", "SPEC"],
    ),
    FieldSpec(
        name="enterprise_or_func_subgrp_name",
        description="Subgroup within the enterprise",
        validation="Short uppercase string e.g. ANH, EMEA, FS_NA. Use empty string if not applicable",
    ),
    FieldSpec(
        name="data_owner_email",
        description="Email of the data owner",
        validation="Valid email address, double-quoted in YAML",
    ),
    FieldSpec(
        name="data_owner_github_uname",
        description="GitHub username of the data owner",
        validation="Alphanumeric, max 30 chars (e.g. ShawnYeager)",
    ),
    FieldSpec(
        name="data_leader",
        description="Data leader's ID",
        validation="Alphanumeric, max 10 chars (e.g. jawillho)",
    ),
]

# ─── Registry ─────────────────────────────────────────────────────────────────

FIELD_SPECS: dict[str, list[FieldSpec]] = {
    "s3": S3_FIELDS,
    "glue_db": GLUE_DB_FIELDS,
}

SUPPORTED_RESOURCES = list(FIELD_SPECS.keys())
