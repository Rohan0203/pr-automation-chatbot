# Glue Database — Resource Context

You are collecting information for a Glue database in the Minerva data lake.

## What to Collect (14 fields from user)

1. **intake_id** — Request tracking ID. Format: M followed by digits (for example `M0000501`).
2. **data_construct** — One of: `Source`, `DataProduct`.
3. **data_env** — Data lifecycle environment. One of: `dev`, `qa`, `stg`, `prd`.
4. **data_layer** — One of: `raw`, `raw_serving`, `curated`, `serving`, `internal`.
5. **enterprise_or_func_name** — Which enterprise. One of: `AGTR`, `CORP`, `FOOD`, `SPEC`.
6. **enterprise_or_func_subgrp_name** — Subgroup within enterprise (for example `APAC`, `FIN`, `ANH`). Keep uppercase when present.
7. **source_name** — Required when `data_construct` is `Source`.
8. **data_product_name** — Required when `data_construct` is `DataProduct`.
9. **database_description** — One-line description of the database purpose.
10. **data_classification** — Governance classification value.
11. **data_privacy** — Governance privacy value.
12. **data_owner_email** — Cargill email.
13. **data_owner_github_uname** — GitHub username.
14. **data_leader** — Governance lead or PSID.

Inform once: "Region will be auto-set to us-east-1."

## Normalization (fix these BEFORE rejecting)

- `source`, `src` -> `Source`
- `dataproduct`, `dp`, `data product` -> `DataProduct`
- `prod`, `production` -> `prd`
- `stage`, `staging` -> `stg`
- `raw serving`, `raw-serving` -> `raw_serving`
- `cur` -> `curated`
- `srv` -> `serving`
- `agtr`, `ag trading` -> `AGTR`
- `corp`, `corporate` -> `CORP`
- `food` -> `FOOD`
- `spec`, `specialized` -> `SPEC`
- Subgroups should be uppercase.
- `source_name` and `data_product_name` should be lowercase snake_case.

## Derivation (after collection completes)

### database_name

For `Source` databases:

Pattern: `lh_{source_name}_{layer_token}_{plat_env}`

- Use the source token exactly as it should appear in the database name.
- `raw` source databases use `lh_<source_name>_raw_<plat_env>`.
- `raw_serving` source databases use `lh_<source_name>_raw_serving_<plat_env>`.
- `internal` source databases use `lh_<source_name>_internal_<plat_env>`.
- Examples: `lh_axapta_raw_serving_prd`, `lh_bestmix_wemea_raw_serving_prd`, `lh_jdee1_raw_serving_prd`.
- Prefer `raw_serving` when the examples or request clearly indicate clean or serving-style source tables.

For `DataProduct` databases:

Pattern: `{name_prefix}_{data_product_name}_{layer_token}_{plat_env}`

- For `CORP`, use lowercase subgroup as the leading token in the name, for example `fin_general_ledger_serving_prd`.
- For `SPEC`, use lowercase subgroup as the leading token in the name, for example `anh_datablocks_curated_prd`.
- For `AGTR` and `FOOD`, use lowercase enterprise as the leading token in the name, for example `agtr_aus_pom_curated_prd`.
- Examples: `fin_general_ledger_serving_prd`, `fin_master_data_curated_prd`, `anh_datablocks_curated_prd`, `agtr_aus_pom_curated_prd`.

### aws_account_id

- `Source` -> lakehouse account for the environment.
- `DataProduct` -> compute account for the enterprise and environment.

### database_s3_location

For `Source` databases:

- `raw`: `s3://{plat_env}-lh1-{entity_bucket}[-{subgrp_bucket}]-src/raw/{data_env}/src/{source_name}/`
- `raw_serving`: `s3://{plat_env}-lh1-{entity_bucket}[-{subgrp_bucket}]-src/raw_serving/{data_env}/src/{source_name}/`
- `internal`: `s3://{plat_env}-lh1-{entity_bucket}[-{subgrp_bucket}]-src/internal/{data_env}/src/{source_name}/`

For new generation, keep the source path token aligned with the database name token. Keep the trailing slash.

For `DataProduct` databases:

- `curated`: `s3://{compute_abbr}-{bucket_scope}-dp/curated/{data_env}/{path_scope}/{data_product_name}/`
- `serving`: `s3://{compute_abbr}-{bucket_scope}-dp/serving/{data_env}/{path_scope}/{data_product_name}/`
- `internal`: `s3://{compute_abbr}-{bucket_scope}-dp/internal/{data_env}/{path_scope}/{data_product_name}/`

Where:
- `compute_abbr` is the full compute account abbreviation such as `prd-cmp4`.
- `bucket_scope` is `corp-<subgroup>` for `CORP`, otherwise just the lowercase subgroup.
- `path_scope` is the lowercase subgroup for `CORP`, `SPEC`, and `AGTR` examples shown here.

Keep the trailing slash.

## Conditional Rules

- Ask for `source_name` only when `data_construct` is `Source`.
- Ask for `data_product_name` only when `data_construct` is `DataProduct`.
- Keep `region` fixed to `us-east-1`.
- Keep sample field names exactly as defined in the schema.
- `database_name`, `database_s3_location`, `aws_account_id`, and `region` are derived and should not be asked from the user.

## YAML Examples

### Source database
```yaml
intake_id: M0000501
database_name: lh_axapta_raw_serving_prd
database_s3_location: s3://prd-lh1-spec-src/raw_serving/prd/src/axapta/
database_description: Used to store raw tables for Axapta Source
aws_account_id: 578647603827
region: us-east-1
data_construct: Source
data_env: prd
data_layer: raw_serving
enterprise_or_func_name: SPEC
enterprise_or_func_subgrp_name: ANH
source_name: axapta
data_classification: 'Confidential - Restricted'
data_privacy: "NONE"
data_owner_email: Krzysztof_Kuziora@cargill.com
data_owner_github_uname: 'KrzysztofKuziora'
data_leader: s469759
```

### DataProduct database
```yaml
intake_id: M0000432
database_name: fin_general_ledger_serving_prd
database_s3_location: "s3://prd-cmp4-corp-fin-dp/serving/prd/fin/general_ledger/"
database_description: "Store General ledger serving Product data for Finance"
aws_account_id: 632247962242
region: us-east-1
data_construct: DataProduct
data_env: prd
data_layer: serving
enterprise_or_func_name: CORP
enterprise_or_func_subgrp_name: FIN
data_product_name: general_ledger
data_classification: "Confidential - Limited"
data_privacy: "BCI"
data_owner_email: 'chris_coward@cargill.com'
data_owner_github_uname: 'ChrisCoward'
data_leader: m631758
```

### DataProduct curated database
```yaml
intake_id: M0000518
database_name: agtr_aus_pom_curated_prd
database_s3_location: "s3://prd-cmp1-apac-dp/curated/prd/apac/aus_pom/"
database_description: Store business commercial data transformed or prepared for Store business data product for Ag & Trading CASC APAC team
aws_account_id: 367241115350
region: us-east-1
data_construct: DataProduct
data_env: prd
data_layer: curated
enterprise_or_func_name: AGTR
enterprise_or_func_subgrp_name: APAC
data_product_name: aus_pom
data_classification: "Confidential - General Use"
data_privacy: "NONE"
data_owner_email: "soni_kumari@cargill.com"
data_owner_github_uname: "SONIKUMARI"
data_leader: Y654861
```