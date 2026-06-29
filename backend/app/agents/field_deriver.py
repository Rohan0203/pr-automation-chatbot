"""
Field Deriver — Pure Python deterministic field derivation.

Called after the collecting phase gathers source fields.
No LLM involvement — all logic is based on org rules from validation docs.

S3 derived fields:
  - bucket_name       ← aws_account_id + enterprise_or_func_name + enterprise_or_func_subgrp_name + usage_type
  - versioning_enabled ← usage_type

Glue DB derived fields:
  - aws_account_id        ← data_layer + enterprise_or_func_name + data_env
  - database_name        ← data_construct + data_layer + data_env + source_name/data_product_name + entity/subgroup
  - database_s3_location ← aws_account_id + data_layer + data_env + entity + subgroup + source/product name
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ─── S3 Account → Abbreviation map ────────────────────────────────────────────
_S3_ACCOUNT_ABBR: dict[str, str] = {
    "438465132548": "dev-lh1",
    "068887784423": "dev-cmp1",
    "933999308564": "dev-cmp2",
    "836901248866": "dev-cmp3",
    "324612370323": "dev-cmp4",
    "578647603827": "prd-lh1",
    "367241115350": "prd-cmp1",
    "884308299029": "prd-cmp2",
    "011379513867": "prd-cmp3",
    "632247962242": "prd-cmp4",
}

_S3_LAKEHOUSE_ACCOUNTS = {"438465132548", "578647603827"}

# ─── S3 Account derivation tables ─────────────────────────────────────────────
_S3_SOURCE_ACCOUNT: dict[str, str] = {
    "dev": "438465132548",  # Lakehouse dev
    "prd": "578647603827",  # Lakehouse prd
}

_S3_DATAPRODUCT_ACCOUNT: dict[str, dict[str, str]] = {
    "agtr": {"dev": "068887784423", "prd": "367241115350"},
    "food": {"dev": "933999308564", "prd": "884308299029"},
    "spec": {"dev": "836901248866", "prd": "011379513867"},
    "corp": {"dev": "324612370323", "prd": "632247962242"},
}

# usage_type → bucket purpose segment
_S3_PURPOSE_MAP: dict[str, str] = {
    "source": "src",
    "dataproduct": "dp",
    "scripts": "scripts",
    "engassets": "eng-assets",
}

# ─── Glue DB Account maps ──────────────────────────────────────────────────────
# Lakehouse accounts (raw, raw_serving, internal can go here)
_GLUE_LAKEHOUSE_DEV = "438465132548"
_GLUE_LAKEHOUSE_PRD = "578647603827"

# Compute accounts per enterprise
_GLUE_COMPUTE: dict[str, dict[str, str]] = {
    # enterprise → {dev: id, prd: id}
    "agtr": {"dev": "068887784423", "prd": "367241115350"},
    "food": {"dev": "933999308564", "prd": "884308299029"},
    "spec": {"dev": "836901248866", "prd": "011379513867"},
    "corp": {"dev": "324612370323", "prd": "632247962242"},
}

# Layers that must live in Lakehouse
_GLUE_LAKEHOUSE_LAYERS = {"raw", "raw_serving", "cdp"}
# Layers that must live in Compute
_GLUE_COMPUTE_LAYERS = {"curated", "serving"}
# Internal can be either
_GLUE_EITHER_LAYERS = {"internal"}

# Glue DB account abbr map (reuses same IDs as S3 — same org accounts)
_GLUE_ACCOUNT_ABBR: dict[str, str] = _S3_ACCOUNT_ABBR


# ═══════════════════════════════════════════════════════════════
# S3 DERIVATION
# ═══════════════════════════════════════════════════════════════

def derive_s3_fields(fields: dict) -> dict[str, str]:
    """
    Derive bucket_name and versioning_enabled from collected S3 fields.

    Returns a dict of {field_name: derived_value} for fields that could be derived.
    Returns an empty dict (or partial) if source fields are missing/invalid.
    """
    derived: dict[str, str] = {}

    enterprise = str(fields.get("enterprise_or_func_name", "")).strip().lower()
    subgroup = str(fields.get("enterprise_or_func_subgrp_name", "")).strip().lower()
    usage_type = str(fields.get("usage_type", "")).strip().lower()
    environment = str(fields.get("environment", "")).strip().lower()

    # ── versioning_enabled (depends only on usage_type) ──
    if usage_type:
        derived["versioning_enabled"] = "true" if usage_type == "scripts" else "false"

    # ── aws_account_id (derived for Source and DataProduct) ──
    account_id = str(fields.get("aws_account_id", "")).strip()
    if not account_id and usage_type and environment:
        if usage_type == "source":
            account_id = _S3_SOURCE_ACCOUNT.get(environment, "")
            if account_id:
                derived["aws_account_id"] = account_id
            else:
                logger.warning(f"S3 derivation: unknown environment '{environment}' for Source account")
        elif usage_type == "dataproduct":
            ent_map = _S3_DATAPRODUCT_ACCOUNT.get(enterprise)
            if ent_map:
                account_id = ent_map.get(environment, "")
                if account_id:
                    derived["aws_account_id"] = account_id
                else:
                    logger.warning(f"S3 derivation: unknown environment '{environment}' for DataProduct account")
            else:
                logger.warning(f"S3 derivation: unknown enterprise '{enterprise}' for DataProduct account")
        # Scripts/EngAssets: aws_account_id must be provided by user — no derivation

    # ── bucket_name (needs account_id + enterprise + usage_type) ──
    if account_id and enterprise and usage_type:
        acct_abbr = _S3_ACCOUNT_ABBR.get(account_id)
        if not acct_abbr:
            logger.warning(f"S3 derivation: unknown account_id '{account_id}'")
        else:
            purpose = _S3_PURPOSE_MAP.get(usage_type)
            if not purpose:
                logger.warning(f"S3 derivation: unknown usage_type '{usage_type}'")
            else:
                is_lakehouse = account_id in _S3_LAKEHOUSE_ACCOUNTS
                if is_lakehouse:
                    # Lakehouse: acct_abbr-enterprise[-subgroup]-purpose
                    # CORP in Lakehouse can include subgroup
                    if subgroup and enterprise == "corp":
                        entity_part = f"corp-{subgroup}"
                    else:
                        entity_part = enterprise
                else:
                    # Compute: acct_abbr-[enterprise-]subgroup-purpose
                    # If subgroup provided use it; else just enterprise
                    if subgroup:
                        entity_part = f"{enterprise}-{subgroup}"
                    else:
                        entity_part = enterprise

                derived["bucket_name"] = f"{acct_abbr}-{entity_part}-{purpose}"

    return derived


# ═══════════════════════════════════════════════════════════════
# GLUE DB DERIVATION
# ═══════════════════════════════════════════════════════════════

def derive_glue_db_fields(fields: dict) -> dict[str, str]:
    """
    Derive aws_account_id, database_name, and database_s3_location
    from collected Glue DB fields.

    Returns a dict of {field_name: derived_value} for each derivable field.
    """
    derived: dict[str, str] = {}

    data_layer = str(fields.get("data_layer", "")).strip().lower()
    enterprise = str(fields.get("enterprise_or_func_name", "")).strip().lower()
    subgroup = str(fields.get("enterprise_or_func_subgrp_name", "")).strip().lower()
    data_env = str(fields.get("data_env", "")).strip().lower()
    data_construct = str(fields.get("data_construct", "")).strip().lower()
    source_name = str(fields.get("source_name", "")).strip().lower()
    product_name = str(fields.get("data_product_name", "")).strip().lower()
    enterprise_upper = enterprise.upper()

    # ── aws_account_id ──────────────────────────────────────────
    account_id: Optional[str] = None
    if data_layer and data_env in ("dev", "prd"):
        if data_layer in _GLUE_LAKEHOUSE_LAYERS:
            account_id = _GLUE_LAKEHOUSE_DEV if data_env == "dev" else _GLUE_LAKEHOUSE_PRD
        elif data_layer in _GLUE_COMPUTE_LAYERS:
            ent_map = _GLUE_COMPUTE.get(enterprise)
            if ent_map:
                account_id = ent_map.get(data_env)
            else:
                logger.warning(f"Glue DB derivation: unknown enterprise '{enterprise}' for compute layer")
        elif data_layer in _GLUE_EITHER_LAYERS:
            # Internal: default to Lakehouse unless enterprise has a compute account
            account_id = _GLUE_LAKEHOUSE_DEV if data_env == "dev" else _GLUE_LAKEHOUSE_PRD

    if account_id:
        derived["aws_account_id"] = account_id

    # ── database_name ───────────────────────────────────────────
    db_name: Optional[str] = None

    if data_layer and data_env:
        if data_layer in _GLUE_LAKEHOUSE_LAYERS:
            # Lakehouse patterns: lh_<src>_<layer>_<env>
            if data_layer == "raw" and source_name:
                db_name = f"lh_{source_name}_raw_{data_env}"
            elif data_layer == "raw_serving" and source_name:
                db_name = f"lh_{source_name}_raw_serving_{data_env}"
            elif data_layer == "cdp" and source_name:
                db_name = f"lh_cdp_{enterprise}_{source_name}_raw_{data_env}"

        elif data_layer == "curated":
            # <owning_entity>_<product_name>_curated_<env>
            name_part = product_name or source_name
            if name_part and enterprise:
                entity_part = f"{enterprise}_{subgroup}" if subgroup else enterprise
                db_name = f"{entity_part}_{name_part}_curated_{data_env}"

        elif data_layer == "serving":
            # <owning_entity>_<product_name>_serving_<purpose>_<env>
            # purpose not always known at derivation time; use product_name if available
            name_part = product_name or source_name
            if name_part and enterprise:
                entity_part = f"{enterprise}_{subgroup}" if subgroup else enterprise
                db_name = f"{entity_part}_{name_part}_serving_{data_env}"

        elif data_layer == "internal":
            # lh_<src>_internal_<env> for source, or <entity>_<product>_internal_<env>
            if source_name:
                db_name = f"lh_{source_name}_internal_{data_env}"
            elif product_name and enterprise:
                entity_part = f"{enterprise}_{subgroup}" if subgroup else enterprise
                db_name = f"{entity_part}_{product_name}_internal_{data_env}"

    if db_name:
        derived["database_name"] = db_name

    # ── database_s3_location ─────────────────────────────────────
    acct = account_id or str(fields.get("aws_account_id", "")).strip()
    if acct and data_layer and data_env:
        acct_abbr = _GLUE_ACCOUNT_ABBR.get(acct, acct)
        s3_loc: Optional[str] = None

        if data_layer == "raw":
            # s3://<acct_abbr>-<enterprise>-src/raw/current/<env>/src/<source>/
            if enterprise and source_name:
                bucket = f"{acct_abbr}-{enterprise}-src"
                s3_loc = f"s3://{bucket}/raw/current/{data_env}/src/{source_name}/"
            elif enterprise:
                bucket = f"{acct_abbr}-{enterprise}-src"
                s3_loc = f"s3://{bucket}/raw/current/{data_env}/src/"

        elif data_layer == "raw_serving":
            if enterprise and source_name:
                bucket = f"{acct_abbr}-{enterprise}-src"
                s3_loc = f"s3://{bucket}/raw_serving/{data_env}/src/{source_name}/"

        elif data_layer == "curated":
            name_part = product_name or source_name
            entity_part = f"{enterprise}-{subgroup}" if subgroup else enterprise
            if name_part:
                bucket = f"{acct_abbr}-{entity_part}-dp"
                s3_loc = f"s3://{bucket}/curated/{data_env}/{name_part}/"
            elif enterprise:
                bucket = f"{acct_abbr}-{entity_part}-dp"
                s3_loc = f"s3://{bucket}/curated/{data_env}/"

        elif data_layer == "serving":
            name_part = product_name or source_name
            entity_part = f"{enterprise}-{subgroup}" if subgroup else enterprise
            if name_part:
                bucket = f"{acct_abbr}-{entity_part}-dp"
                s3_loc = f"s3://{bucket}/serving/{data_env}/{name_part}/"

        elif data_layer == "internal":
            if source_name:
                bucket = f"{acct_abbr}-{enterprise}-src"
                s3_loc = f"s3://{bucket}/internal/{data_env}/src/{source_name}/"
            elif product_name and enterprise:
                entity_part = f"{enterprise}-{subgroup}" if subgroup else enterprise
                bucket = f"{acct_abbr}-{entity_part}-dp"
                s3_loc = f"s3://{bucket}/internal/{data_env}/{product_name}/"

        if s3_loc:
            derived["database_s3_location"] = s3_loc

    return derived


# ═══════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def derive_fields(resource_type: str, collected_fields: dict) -> dict[str, str]:
    """
    Derive all auto-derivable fields for the given resource type.
    Returns a dict of newly derived {field_name: value}.
    Only returns fields that could actually be computed.
    """
    rtype = resource_type.lower().replace("-", "_").replace(" ", "_")
    if rtype == "s3":
        return derive_s3_fields(collected_fields)
    elif rtype in ("glue_db", "glue-db", "gluedb"):
        return derive_glue_db_fields(collected_fields)
    return {}


# Source fields required before derivation can run per resource type
_S3_SOURCE_FIELDS = {"environment", "enterprise_or_func_name", "usage_type"}
_GLUE_SOURCE_FIELDS = {"data_layer", "enterprise_or_func_name", "data_env", "data_construct"}


def has_enough_to_derive(resource_type: str, collected_fields: dict) -> bool:
    """Return True if we have the minimum source fields needed to attempt derivation."""
    rtype = resource_type.lower().replace("-", "_").replace(" ", "_")
    keys = set(collected_fields.keys())
    if rtype == "s3":
        usage_type = str(collected_fields.get("usage_type", "")).strip().lower()
        base_fields = {"enterprise_or_func_name", "usage_type"}
        if usage_type in ("scripts", "engassets"):
            # Scripts/EngAssets: user provides aws_account_id directly
            return bool((base_fields | {"aws_account_id"}).issubset(keys))
        else:
            # Source/DataProduct: environment is needed to derive aws_account_id
            return bool((base_fields | {"environment"}).issubset(keys))
    elif rtype in ("glue_db", "glue-db", "gluedb"):
        return bool(_GLUE_SOURCE_FIELDS.issubset(keys))
    return False
