"""
Resource configuration — what this app supports.

Each resource type defines:
- label: display name for UI
- description: short explanation
- category: grouping (S3 / Glue DB)
- resource_type: base type key (s3 / glue_db)
- auto_fields: fields pre-filled from wizard choices
- account_type: fixed account or None (ask user)
- needs_account_ask: whether to ask account type in Q3
- conditional flags: needs_cdp_ask, needs_purpose_ask, needs_construct_ask
"""

ENVIRONMENTS = ["dev", "prd"]

ENTERPRISE_SUBGROUPS = {
    "AGTR": ["EMEA", "NA", "LATAM", "APAC", "WTG", "WTG_CDAS", "OT", "CRM", "TCM", "MET"],
    "CORP": ["GI_SUST", "EHS", "FIN", "GTC", "CPT", "HR", "AUDIT", "DTD", "LAW", "DTD_DPE", "RMG", "FSQR", "DTD_GIS"],
    "FOOD": ["FSGL", "FS_NA", "FS_LATAM", "FS_APAC", "FS_EMEA", "PRGL", "PR_LATAM", "PR_NA", "PR_APAC", "SALT", "CE", "RD"],
    "SPEC": ["ANH", "CBI", "DS"],
}

RESOURCE_OPTIONS = {
    # ─── S3 Buckets ───────────────────────────────────────────
    "s3_source": {
        "label": "Source Bucket",
        "description": "Data ingestion from source systems",
        "category": "S3",
        "resource_type": "s3",
        "auto_fields": {"usage_type": "Source"},
        "account_type": "lakehouse",
        "needs_account_ask": False,
    },
    "s3_dataproduct": {
        "label": "DataProduct Bucket",
        "description": "Transformed / processed data",
        "category": "S3",
        "resource_type": "s3",
        "auto_fields": {"usage_type": "DataProduct"},
        "account_type": "compute",
        "needs_account_ask": False,
    },
    "s3_scripts": {
        "label": "Scripts Bucket",
        "description": "ETL scripts and code",
        "category": "S3",
        "resource_type": "s3",
        "auto_fields": {"usage_type": "Scripts"},
        "account_type": None,
        "needs_account_ask": True,
    },
    "s3_engassets": {
        "label": "EngAssets Bucket",
        "description": "Engineering assets",
        "category": "S3",
        "resource_type": "s3",
        "auto_fields": {"usage_type": "EngAssets"},
        "account_type": None,
        "needs_account_ask": True,
    },
    # ─── Glue Databases ──────────────────────────────────────
    "glue_raw": {
        "label": "Raw Source DB",
        "description": "Raw data ingestion layer",
        "category": "Glue DB",
        "resource_type": "glue_db",
        "auto_fields": {"data_construct": "Source", "data_layer": "raw"},
        "account_type": "lakehouse",
        "needs_account_ask": False,
        "needs_cdp_ask": True,
    },
    "glue_curated": {
        "label": "Curated DB",
        "description": "Processed / curated data layer",
        "category": "Glue DB",
        "resource_type": "glue_db",
        "auto_fields": {"data_construct": "DataProduct", "data_layer": "curated"},
        "account_type": "compute",
        "needs_account_ask": False,
    },
    "glue_serving": {
        "label": "Serving DB",
        "description": "Analytics / serving layer",
        "category": "Glue DB",
        "resource_type": "glue_db",
        "auto_fields": {"data_construct": "DataProduct", "data_layer": "serving"},
        "account_type": "compute",
        "needs_account_ask": False,
        "needs_purpose_ask": True,
    },
    "glue_internal": {
        "label": "Internal DB",
        "description": "Internal processing / staging",
        "category": "Glue DB",
        "resource_type": "glue_db",
        "auto_fields": {"data_layer": "internal"},
        "account_type": None,
        "needs_account_ask": True,
        "needs_construct_ask": True,
    },
}
