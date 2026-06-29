"""
Field specifications for each resource type.
Derived from actual approved PR YAMLs in miw-repo — this is the source of truth.

6 resource types: s3, glue_db, iam, resource_policy, smus_role, smus_project
"""
from app.models.state import FieldSpec

# ─── S3 Fields ────────────────────────────────────────────────────────────────
# From: lakehouse-001/s3/*.yaml and compute-*/s3/*.yaml

S3_FIELDS: list[FieldSpec] = [
    FieldSpec(
        name="intake_id",
        description="Request tracking ID (e.g. M0000485)",
    ),
    FieldSpec(
        name="bucket_name",
        description="S3 bucket name (e.g. prd-lh1-agtr-src, dev-cmp1-food-scripts)",
    ),
    FieldSpec(
        name="bucket_description",
        description="Human-readable purpose of the bucket",
    ),
    FieldSpec(
        name="aws_account_id",
        description="AWS account ID (12-digit, single-quoted in YAML)",
    ),
    FieldSpec(
        name="aws_region",
        derivable=True,
        default="us-east-1",
        description="AWS region",
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
        description="Subgroup within the enterprise (e.g. EMEA, FIN, PRGL). Can be empty string.",
    ),
]

# ─── Glue DB Fields ──────────────────────────────────────────────────────────
# From: lakehouse-001/glue_db/*.yaml and compute-*/glue_db/*.yaml

GLUE_DB_FIELDS: list[FieldSpec] = [
    FieldSpec(
        name="intake_id",
        description="Request tracking ID (e.g. M0000934)",
    ),
    FieldSpec(
        name="database_name",
        description="Glue database name (e.g. lh_cdp_sap_tcd_raw_prd)",
    ),
    FieldSpec(
        name="database_s3_location",
        description="S3 location for the database (e.g. s3://prd-lh1-food-src/raw/cdp/prd/src/sap_tcd/)",
    ),
    FieldSpec(
        name="database_description",
        description="Human-readable description of the database",
    ),
    FieldSpec(
        name="aws_account_id",
        description="AWS account ID (12-digit)",
    ),
    FieldSpec(
        name="region",
        derivable=True,
        default="us-east-1",
        description="AWS region",
    ),
    FieldSpec(
        name="data_construct",
        description="Whether this is a Source or DataProduct database",
        options=["Source", "DataProduct"],
    ),
    FieldSpec(
        name="data_env",
        description="Environment",
        options=["dev", "prd"],
    ),
    FieldSpec(
        name="data_layer",
        description="Data layer in the lakehouse architecture",
        options=["raw", "raw_serving", "curated", "serving", "internal"],
    ),
    FieldSpec(
        name="source_name",
        description="Name of the source system (lowercase, e.g. sap_tcd, cdp)",
        depends_on={"data_construct": "Source"},
    ),
    FieldSpec(
        name="data_product_name",
        description="Name of the data product (lowercase)",
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
        description="Data privacy designation (e.g. None, PII)",
        default="None",
    ),
    FieldSpec(
        name="enterprise_or_func_name",
        description="Enterprise or functional area",
        options=["AGTR", "CORP", "FOOD", "SPEC"],
    ),
    FieldSpec(
        name="enterprise_or_func_subgrp_name",
        description="Subgroup within the enterprise (e.g. PRGL, ANH)",
    ),
    FieldSpec(
        name="data_owner_email",
        description="Email of the data owner",
    ),
    FieldSpec(
        name="data_owner_github_uname",
        description="GitHub username of the data owner (e.g. HarendraKanuru)",
    ),
    FieldSpec(
        name="data_leader",
        description="Data leader's name or ID (e.g. KatiePorter)",
    ),
]

# ─── IAM Fields ───────────────────────────────────────────────────────────────
# From: lakehouse-001/iam/*.yaml and compute-*/iam/*.yaml

IAM_FIELDS: list[FieldSpec] = [
    FieldSpec(
        name="intake_id",
        description="Request tracking ID (e.g. M0000485)",
    ),
    FieldSpec(
        name="role_name",
        description="IAM role name (e.g. food_prgl_prd_procdataengineer)",
    ),
    FieldSpec(
        name="role_description",
        description="Human-readable description of the role's purpose",
    ),
    FieldSpec(
        name="aws_account_id",
        description="AWS account ID where the role will be created",
    ),
    FieldSpec(
        name="enterprise_or_func_name",
        description="Enterprise or functional area",
        options=["AGTR", "CORP", "FOOD", "SPEC"],
    ),
    FieldSpec(
        name="enterprise_or_func_subgrp_name",
        description="Subgroup (e.g. PRGL, TDA_COCOA, APAC)",
    ),
    FieldSpec(
        name="role_owner",
        description="Email of the role owner (e.g. harendra_kanuru@cargill.com)",
    ),
    FieldSpec(
        name="data_env",
        description="Environment",
        options=["dev", "prd"],
    ),
    FieldSpec(
        name="usage_type",
        description="Role type",
        options=["DataEngineer", "DataScientist", "DataAnalyst", "IngestionEngineer", "TechAnalyst"],
    ),
    FieldSpec(
        name="data_leader",
        description="Data leader's name or ID",
    ),
    FieldSpec(
        name="principal_role_arn",
        description="ARN of the principal role (e.g. arn:aws:iam::155261241286:role/prod-mif-...)",
        required=False,
    ),
    FieldSpec(
        name="compute_size",
        description="Compute size for Glue sessions",
        options=["XSML", "SML", "MED", "LRG", "XLRG"],
        required=False,
    ),
    FieldSpec(
        name="max_session_duration",
        description="Max session duration in hours (e.g. 2)",
        required=False,
    ),
    FieldSpec(
        name="access_to_resources",
        description="Resources this role can access: glue_databases (read/write lists) and data_prefixes (S3 paths)",
    ),
    FieldSpec(
        name="enable_glue_interactive_session",
        description="Enable Glue interactive sessions (true/false)",
        options=["true", "false"],
        required=False,
        default="false",
    ),
    FieldSpec(
        name="snowflake_iceberg_support",
        description="Enable Snowflake Iceberg support (true/false)",
        options=["true", "false"],
        required=False,
        default="false",
    ),
]

# ─── Resource Policy Fields ───────────────────────────────────────────────────
# From: lakehouse-001/resource_policy/*.yaml

RESOURCE_POLICY_FIELDS: list[FieldSpec] = [
    FieldSpec(
        name="intake_id",
        description="Request tracking ID",
    ),
    FieldSpec(
        name="resource_policy_name",
        description="Policy name (e.g. minerva_cmt_food_prgl_prd_rp)",
    ),
    FieldSpec(
        name="resource_policy_description",
        description="Description of the resource policy's purpose",
    ),
    FieldSpec(
        name="aws_account_id",
        description="AWS account ID where the policy is applied",
    ),
    FieldSpec(
        name="cross_account_aws_id",
        description="Cross-account AWS ID that will be granted access (12-digit)",
    ),
    FieldSpec(
        name="enterprise_or_func_name",
        description="Enterprise or functional area",
        options=["AGTR", "CORP", "FOOD", "SPEC"],
    ),
    FieldSpec(
        name="enterprise_or_func_subgrp_name",
        description="Subgroup (e.g. PRGL, NA, APAC)",
    ),
    FieldSpec(
        name="data_leader",
        description="Data leader's name or ID",
    ),
    FieldSpec(
        name="principal_role_arn",
        description="ARN of the principal role being granted access",
    ),
    FieldSpec(
        name="access_to_resources",
        description="Resources: glue_databases (list of DB names) and s3_prefixes (list of S3 paths)",
    ),
]

# ─── SMUS Role Fields ─────────────────────────────────────────────────────────
# From: lakehouse-001/smus_roles/*.yaml

SMUS_ROLE_FIELDS: list[FieldSpec] = [
    FieldSpec(
        name="intake_id",
        description="Request tracking ID",
    ),
    FieldSpec(
        name="aad_group_name",
        description="AAD group name (e.g. minerva_food_prgl_dataengineer_prd)",
    ),
    FieldSpec(
        name="aws_account_id",
        description="AWS account ID",
    ),
    FieldSpec(
        name="purpose",
        description="Purpose description for this SMUS role group",
    ),
    FieldSpec(
        name="role_owner_ds_id",
        description="Role owner's DS ID (e.g. a290919)",
    ),
    FieldSpec(
        name="role_owner_email_id",
        description="Role owner's email (e.g. John_Doe@cargill.com)",
    ),
    FieldSpec(
        name="data_leader",
        description="Data leader's name or ID",
    ),
    FieldSpec(
        name="governance_and_access_lead",
        description="Governance and access lead's ID (e.g. k040619)",
    ),
    FieldSpec(
        name="enterprise_or_func_name",
        description="Enterprise or functional area",
        options=["AGTR", "CORP", "FOOD", "SPEC"],
    ),
    FieldSpec(
        name="enterprise_or_func_subgrp_name",
        description="Subgroup (e.g. PRGL, ANH)",
    ),
    FieldSpec(
        name="sub_function",
        description="Sub-function (e.g. NA if not applicable)",
        required=False,
        default="NA",
    ),
]

# ─── SMUS Project Fields ──────────────────────────────────────────────────────
# From: lakehouse-001/smus_project/*.yaml

SMUS_PROJECT_FIELDS: list[FieldSpec] = [
    FieldSpec(
        name="intake_id",
        description="Request tracking ID",
    ),
    FieldSpec(
        name="aws_account_id",
        description="AWS account ID",
    ),
    FieldSpec(
        name="smus_project_name",
        description="Project name (e.g. food_prgl_dataengineer_prd_prj)",
    ),
    FieldSpec(
        name="project_description",
        description="Description of the SMUS project's purpose",
    ),
    FieldSpec(
        name="enterprise_or_func_name",
        description="Enterprise or functional area",
        options=["AGTR", "CORP", "FOOD", "SPEC"],
    ),
    FieldSpec(
        name="enterprise_or_func_subgrp_name",
        description="Subgroup (e.g. PRGL, TDA_COCOA)",
    ),
    FieldSpec(
        name="parent_domain_unit",
        description="Parent domain unit (e.g. Minerva)",
        default="Minerva",
    ),
    FieldSpec(
        name="data_leader",
        description="Data leader's name or ID",
    ),
    FieldSpec(
        name="project_membership",
        description="List of SMUS role group names that belong to this project",
    ),
    FieldSpec(
        name="compute_size",
        description="Compute size",
        options=["XSML", "SML", "MED", "LRG", "XLRG"],
    ),
    FieldSpec(
        name="access_to_resources",
        description="List of glue_databases this project can access",
    ),
]

# ─── Registry ─────────────────────────────────────────────────────────────────

FIELD_SPECS: dict[str, list[FieldSpec]] = {
    "s3": S3_FIELDS,
    "glue_db": GLUE_DB_FIELDS,
    "iam": IAM_FIELDS,
    "resource_policy": RESOURCE_POLICY_FIELDS,
    "smus_role": SMUS_ROLE_FIELDS,
    "smus_project": SMUS_PROJECT_FIELDS,
}

SUPPORTED_RESOURCES = list(FIELD_SPECS.keys())
