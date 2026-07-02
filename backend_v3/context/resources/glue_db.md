# Glue Database — Resource Context

You are collecting information for a Glue Database in the Minerva Lakehouse (or Compute) account.

## What to Collect (11 fields from user)

### Identity group
1. **plat_env** — Platform environment: dev, prd, or snd.
2. **intake_id** — Request tracking ID. Format: M or I followed by digits (e.g. M0000451).
3. **data_construct** — Source or DataProduct.
4. **data_layer** — One of: raw, raw_serving, curated, serving, internal.
5. **data_env** — Data environment: dev, prd, qa, stg, snd. Often same as plat_env.
6. **source_name** — Governance-approved source system name (e.g. cdp, concur, sap_tc1, jdee1, iiq). Lowercase.
7. **enterprise_or_func_name** — AGTR, CORP, FOOD, or SPEC.
8. **enterprise_or_func_subgrp_name** — Subgroup (e.g. FIN, DTD, APAC). **Required for CORP**, optional for others.

### Ownership group
9. **data_owner_email** — Must be a @cargill.com email.
10. **data_owner_github_uname** — Cargill GitHub Enterprise username.
11. **data_leader** — Name or PSID (e.g. k745239).

Inform once: "Region will be auto-set to us-east-1."

## Naming Convention

### Lakehouse — raw layer (Source databases)
```
lh_{cdp_}{source_name}_{instance}_{data_layer}_{plat_env}
```
- If source_name is `cdp`, include `cdp_` after `lh_`: `lh_cdp_sap_tcl_raw_prd`
- Otherwise: `lh_concur_raw_dev`, `lh_sap_tc1_raw_dev`

### Lakehouse — raw_serving
```
lh_{source_name}_{instance}_{data_layer}_{plat_env}
```
- Examples: `lh_sap_tc1_raw_serving_dev`, `lh_jdee1_raw_serving_prd`

### Compute — curated (DataProduct)
```
{owning_entity}_{product_name}_{data_layer}_{plat_env}
```
- Examples: `fin_general_ledger_curated_dev`, `wtg_seaborne_curated_dev`

### Compute — serving (DataProduct with purpose)
```
{owning_entity}_{product_name}_{data_layer}_{purpose}_{plat_env}
```
- Examples: `fin_general_ledger_serving_analytics_dev`

### Hard naming rules
- Lowercase snake_case only (`a-z0-9_`)
- Lakehouse DBs **must** start with `lh_`
- If source_name is `cdp`, the name **must** contain `cdp` after `lh_`
- source_name token must appear in database_name for raw/raw_serving
- Database name is **immutable** after creation

## S3 Location Derivation

### Raw (non-CDP)
```
s3://{plat_env}-lh1-{entity}[-{subgrp}]-src/raw/current/{data_env}/src/{source_name}/
```

### Raw (CDP)
```
s3://{plat_env}-lh1-{entity}[-{subgrp}]-src/raw/cdp/{data_env}/src/{source_name}/
```

### Raw Serving
```
s3://{plat_env}-lh1-{entity}[-{subgrp}]-src/raw_serving/{data_env}/src/{source_name}/
```

### Curated (Compute)
```
s3://{plat_env}-cmpN-{subgrp}-dp/curated/{data_env}/{entity}/{product}/
```

### Serving (Compute)
```
s3://{plat_env}-cmpN-{subgrp}-dp/serving/{data_env}/{entity}/{product}/{purpose}/
```

Rules:
- Bucket must match enterprise (and subgroup for CORP)
- Entity segment is lowercase enterprise
- Trailing `/` required

## Account Mapping
- Source (Lakehouse): dev → 438465132548, prd → 578647603827
- DataProduct (Compute): depends on enterprise + plat_env

## YAML Examples

### CDP raw DB (Lakehouse, prod, CORP FIN)
```yaml
intake_id: M0000449
database_name: lh_cdp_sap_tcl_raw_prd
database_s3_location: "s3://prd-lh1-corp-fin-src/raw/cdp/prd/src/sap_tcl/"
database_description: "Store data from SAP TCL source system copied from CDP"
aws_account_id: '578647603827'
region: us-east-1
data_construct: Source
data_env: prd
data_layer: raw
source_name: cdp
enterprise_or_func_name: CORP
enterprise_or_func_subgrp_name: FIN
data_owner_email: chris_coward@cargill.com
data_owner_github_uname: ChrisCoward
data_leader: k745239
```

### Raw serving DB (Lakehouse, prod, AGTR)
```yaml
intake_id: M0000444
database_name: lh_jdee1_raw_serving_prd
database_s3_location: "s3://prd-lh1-agtr-src/raw_serving/prd/src/jdee1/"
database_description: "Database for storing clean JDEE1 tables"
aws_account_id: '578647603827'
region: us-east-1
data_construct: Source
data_env: prd
data_layer: raw_serving
source_name: jdee1
enterprise_or_func_name: AGTR
enterprise_or_func_subgrp_name: ""
data_owner_email: elias_belmiro@cargill.com
data_owner_github_uname: Eliasda-Silva-Belmiro
data_leader: Jonathan Cook
```

### CDP raw DB with PII (Lakehouse, prod, CORP DTD)
```yaml
intake_id: M0000451
database_name: lh_cdp_iiq_raw_prd
database_s3_location: "s3://prd-lh1-corp-dtd-src/raw/cdp/prd/src/iiq/"
database_description: "Used to store raw tables for Identity IQ Source"
aws_account_id: '578647603827'
region: us-east-1
data_construct: Source
data_env: prd
data_layer: raw
source_name: cdp
enterprise_or_func_name: CORP
enterprise_or_func_subgrp_name: DTD
data_owner_email: stephen_washington@cargill.com
data_owner_github_uname: StephenWashington
data_leader: g365220
```

## Key Differences from S3

- More fields (11 collect vs 5 for S3)
- Has `data_env` separate from `plat_env` (they can differ)
- Has `data_layer` and `source_name` driving naming
- CDP source triggers special `lh_cdp_` prefix in name
- Subgroup is **required** for CORP (not optional like S3)
- Ownership fields collected directly (not derived)
- database_name and database_s3_location are **immutable** — cannot be changed after creation
