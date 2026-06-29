# Glue Database Validation Rules

> Reviewer: evaluate the YAML against ONLY these RULE blocks.
> If a RULE block is not listed here, it does not exist — do NOT invent rules.
> If all rules pass, return passed=true with zero violations.

---

## REFERENCE: Account Table

| Account ID | Env | Type | Enterprise | Compute # | S3 Bucket Prefix |
|------------|-----|------|------------|-----------|------------------|
| 438465132548 | dev | Lakehouse | Common | — | dev-lh1- |
| 068887784423 | dev | Compute | AGTR | cmp1 | dev-cmp1- |
| 933999308564 | dev | Compute | FOOD | cmp2 | dev-cmp2- |
| 836901248866 | dev | Compute | SPEC | cmp3 | dev-cmp3- |
| 324612370323 | dev | Compute | CORP | cmp4 | dev-cmp4- |
| 578647603827 | prd | Lakehouse | Common | — | prd-lh1- |
| 367241115350 | prd | Compute | AGTR | cmp1 | prd-cmp1- |
| 884308299029 | prd | Compute | FOOD | cmp2 | prd-cmp2- |
| 011379513867 | prd | Compute | SPEC | cmp3 | prd-cmp3- |
| 632247962242 | prd | Compute | CORP | cmp4 | prd-cmp4- |

## REFERENCE: Enterprise → Compute Account Mapping

| Enterprise | Dev Account | Prod Account |
|---|---|---|
| AGTR | 068887784423 | 367241115350 |
| FOOD | 933999308564 | 884308299029 |
| SPEC | 836901248866 | 011379513867 |
| CORP | 324612370323 | 632247962242 |

## REFERENCE: Approved Subgroups per Enterprise

| Enterprise | Valid Subgroups |
|---|---|
| AGTR | EMEA, NA, LATAM, APAC, WTG, WTG_CDAS, OT, CRM, TCM, MET |
| CORP | GI_SUST, EHS, FIN, GTC, CPT, HR, AUDIT, DTD, LAW, DTD_DPE, RMG, FSQR, DTD_GIS |
| FOOD | FSGL, FS_NA, FS_LATAM, FS_APAC, FS_EMEA, PRGL, PR_LATAM, PR_NA, PR_APAC, SALT, CE, RD |
| SPEC | ANH, CBI, DS |

---

# FIELD PRESENCE RULES

## RULE GLUE-FLD-001
- **SEVERITY:** ERROR
- **CHECK:** All mandatory fields must be present and non-empty: `intake_id`, `database_name`, `database_s3_location`, `database_description`, `aws_account_id`, `region`, `data_env`, `data_layer`, `data_construct`, `enterprise_or_func_name`, `data_classification`, `data_owner_email`, `data_owner_github_uname`, `data_leader`
- **EXPECTED:** All 14 fields exist and are non-empty

## RULE GLUE-FLD-002
- **SEVERITY:** ERROR
- **CHECK:** When `data_construct = Source`, the field `source_name` must be present and non-empty, and `data_product_name` must NOT be present in the YAML
- **EXPECTED:** `source_name` is populated; `data_product_name` field is omitted entirely

## RULE GLUE-FLD-003
- **SEVERITY:** ERROR
- **CHECK:** When `data_construct = DataProduct`, the field `data_product_name` must be present and non-empty, and `source_name` must NOT be present in the YAML
- **EXPECTED:** `data_product_name` is populated; `source_name` field is omitted entirely

## RULE GLUE-FLD-004
- **SEVERITY:** ERROR
- **CHECK:** When `data_layer = srv` (serving), the `database_name` must include a PURPOSE segment between the product name and the environment suffix
- **EXPECTED:** Serving database names follow pattern: `[entity]_[product]_serving_[purpose]_[env]`

## RULE GLUE-FLD-005
- **SEVERITY:** ERROR
- **CHECK:** `enterprise_or_func_subgrp_name` must be present (can be empty string `""` for enterprise-level Source databases, but the field must exist)
- **EXPECTED:** Field is present in YAML

---

# ALLOWED VALUE RULES

## RULE GLUE-VAL-001
- **SEVERITY:** ERROR
- **CHECK:** `region` must be `us-east-1`
- **EXPECTED:** `us-east-1` (only supported region)

## RULE GLUE-VAL-002
- **SEVERITY:** ERROR
- **CHECK:** `data_env` must be one of: `snd`, `dev`, `stg`, `prd`
- **EXPECTED:** One of the four approved environments

## RULE GLUE-VAL-003
- **SEVERITY:** ERROR
- **CHECK:** `data_layer` must be one of: `raw`, `cur`, `srv`, `int`
- **EXPECTED:** One of the four abbreviated layer values

## RULE GLUE-VAL-004
- **SEVERITY:** ERROR
- **CHECK:** `data_construct` must be one of: `Source`, `DataProduct`
- **EXPECTED:** Exactly `Source` or `DataProduct` (case-sensitive)

## RULE GLUE-VAL-005
- **SEVERITY:** ERROR
- **CHECK:** `enterprise_or_func_name` must be one of: `AGTR`, `CORP`, `FOOD`, `SPEC`
- **EXPECTED:** One of the four approved enterprise abbreviations (uppercase)

## RULE GLUE-VAL-006
- **SEVERITY:** ERROR
- **CHECK:** If `enterprise_or_func_subgrp_name` is non-empty, it must be a valid subgroup for the stated `enterprise_or_func_name` (see Approved Subgroups table above)
- **EXPECTED:** Subgroup belongs to the parent enterprise

## RULE GLUE-VAL-007
- **SEVERITY:** ERROR
- **CHECK:** `data_classification` must be one of: `Public`, `Confidential - General Use`, `Confidential - Limited`, `Confidential - Restricted`, `Confidential - Highly Restricted`
- **EXPECTED:** One of the five approved classification levels

## RULE GLUE-VAL-008
- **SEVERITY:** ERROR
- **CHECK:** If `data_privacy` is present and non-empty, it must be one of: `PI`, `PCI`, `PHI`, `BCI`, `NONE`
- **EXPECTED:** One of the five approved privacy categories, or empty string

---

# ACCOUNT RULES

## RULE GLUE-ACC-001
- **SEVERITY:** ERROR
- **CHECK:** `aws_account_id` must be one of the 10 known account IDs in the Account Table
- **EXPECTED:** Account ID exists in the table above

## RULE GLUE-ACC-002
- **SEVERITY:** ERROR
- **CHECK:** When `data_layer` is `raw` — `aws_account_id` must be a Lakehouse account (`438465132548` or `578647603827`)
- **EXPECTED:** Raw layer databases live in Lakehouse

## RULE GLUE-ACC-003
- **SEVERITY:** ERROR
- **CHECK:** When `data_layer` is `cur` or `srv` — `aws_account_id` must be a Compute account (NOT Lakehouse)
- **EXPECTED:** Curated and serving layer databases live in Compute

## RULE GLUE-ACC-004
- **SEVERITY:** ERROR
- **CHECK:** When `data_layer` is `int` — `aws_account_id` can be either Lakehouse or Compute (both allowed)
- **EXPECTED:** Internal layer is valid in both account types

## RULE GLUE-ACC-005
- **SEVERITY:** ERROR
- **CHECK:** When using a Compute account, the `enterprise_or_func_name` must match the enterprise assigned to that account (see Enterprise → Compute Account Mapping table)
- **EXPECTED:** AGTR uses compute-001, FOOD uses compute-002, SPEC uses compute-003, CORP uses compute-004

---

# NAMING RULES

## RULE GLUE-NAM-001
- **SEVERITY:** ERROR
- **CHECK:** `database_name` must be all lowercase and underscore-separated. No uppercase, no hyphens, no spaces.
- **EXPECTED:** Pattern `^[a-z0-9][a-z0-9_]*$`

## RULE GLUE-NAM-002
- **SEVERITY:** ERROR
- **CHECK:** `database_name` must end with `_[data_env]` suffix matching the `data_env` field value
- **EXPECTED:** Name ends with `_dev`, `_prd`, `_stg`, or `_snd` matching `data_env`

## RULE GLUE-NAM-003
- **SEVERITY:** ERROR
- **CHECK:** When `aws_account_id` is a Lakehouse account AND `data_construct = Source`, `database_name` must start with `lh_`
- **EXPECTED:** Lakehouse Source databases always use `lh_` prefix

## RULE GLUE-NAM-004
- **SEVERITY:** ERROR
- **CHECK:** When `aws_account_id` is a Compute account, `database_name` must NOT start with `lh_`
- **EXPECTED:** Compute database names never use `lh_` prefix

## RULE GLUE-NAM-005
- **SEVERITY:** ERROR
- **CHECK:** `database_name` must contain the layer name in full form: `raw`, `raw_serving`, `curated`, `serving`, or `internal` — even though `data_layer` in YAML uses abbreviations (`cur`, `srv`, `int`)
- **EXPECTED:** The full layer name appears as a segment in `database_name`
- **MAPPING:** `cur` → `curated`, `srv` → `serving`, `int` → `internal`, `raw` → `raw` or `raw_serving`

## RULE GLUE-NAM-006
- **SEVERITY:** ERROR
- **CHECK:** For Lakehouse Source raw databases: name must match `lh_[<cdp>_][source_name][_<instance>]_raw_[data_env]`
- **EXPECTED:** Examples: `lh_concur_raw_dev`, `lh_cdp_sap_tc1_raw_dev`, `lh_1c_raw_prd`

## RULE GLUE-NAM-007
- **SEVERITY:** ERROR
- **CHECK:** For Lakehouse Source raw_serving databases: name must match `lh_[<cdp>_][source_name][_<instance>]_raw_serving_[data_env]`
- **EXPECTED:** Example: `lh_concur_raw_serving_dev`

## RULE GLUE-NAM-008
- **SEVERITY:** ERROR
- **CHECK:** For Lakehouse CDP DataProduct raw databases: name must match `lh_cdp_[owning_entity]_[product_name]_raw_[data_env]`
- **EXPECTED:** Example: `lh_cdp_fin_controls_raw_dev`

## RULE GLUE-NAM-009
- **SEVERITY:** ERROR
- **CHECK:** For Lakehouse Source internal databases: name must match `lh_[source_name][_<instance>]_internal_[data_env]`
- **EXPECTED:** Example: `lh_concur_internal_dev`

## RULE GLUE-NAM-010
- **SEVERITY:** ERROR
- **CHECK:** For Compute curated databases: name must match `[owning_entity]_[product_name]_curated_[data_env]`
- **EXPECTED:** Examples: `fin_controls_curated_dev`, `na_lynx_dm_curated_prd`

## RULE GLUE-NAM-011
- **SEVERITY:** ERROR
- **CHECK:** For Compute serving databases: name must match `[owning_entity]_[product_name]_serving_[purpose]_[data_env]`
- **EXPECTED:** Example: `hr_successfactors_serving_analytics_dev`. PURPOSE is mandatory for serving.

## RULE GLUE-NAM-012
- **SEVERITY:** ERROR
- **CHECK:** For Compute internal databases: name must match `[owning_entity]_[product_name]_internal_[data_env]`
- **EXPECTED:** Examples: `fin_controls_internal_dev`, `na_lynx_dm_stg_internal_prd`

---

# S3 LOCATION RULES

## RULE GLUE-S3-001
- **SEVERITY:** ERROR
- **CHECK:** `database_s3_location` must start with `s3://` and end with `/`
- **EXPECTED:** Valid S3 URI format

## RULE GLUE-S3-002
- **SEVERITY:** ERROR
- **CHECK:** For Source databases (`data_construct = Source`), the S3 bucket name must end with `-src`
- **EXPECTED:** Source databases write to source buckets (e.g., `dev-lh1-corp-fin-src`)

## RULE GLUE-S3-003
- **SEVERITY:** ERROR
- **CHECK:** For DataProduct databases in Compute (`data_construct = DataProduct`, Compute account), the S3 bucket name must end with `-dp`
- **EXPECTED:** Data product databases write to dp buckets (e.g., `dev-cmp1-apac-dp`)

## RULE GLUE-S3-004
- **SEVERITY:** ERROR
- **CHECK:** The S3 path must contain the `data_env` value
- **EXPECTED:** `data_env` appears as a path segment in `database_s3_location`

## RULE GLUE-S3-005
- **SEVERITY:** WARNING
- **CHECK:** The S3 bucket prefix should reflect the account type — Lakehouse buckets use `lh1`, Compute buckets use `cmp[N]`
- **EXPECTED:** Bucket prefix aligns with account type

---

# GOVERNANCE RULES

## RULE GLUE-GOV-001
- **SEVERITY:** ERROR
- **CHECK:** `data_owner_email` must be a valid email format (contains `@`)
- **EXPECTED:** Valid corporate email address

## RULE GLUE-GOV-002
- **SEVERITY:** ERROR
- **CHECK:** `data_owner_github_uname` must be alphanumeric (letters, numbers, underscores allowed)
- **EXPECTED:** Valid GitHub username format

## RULE GLUE-GOV-003
- **SEVERITY:** ERROR
- **CHECK:** `data_leader` must be non-empty and alphanumeric
- **EXPECTED:** Valid employee identifier

## RULE GLUE-GOV-004
- **SEVERITY:** ERROR
- **CHECK:** `intake_id` must be alphanumeric (may contain hyphens). Must not be a generic placeholder like `123456`, `000000`.
- **EXPECTED:** A real intake ID (e.g., `M0000452`, `M-0000792`)

---

# VALID EXAMPLES

## Example 1: Lakehouse Raw Source (SPEC/ANH)
```yaml
intake_id: M0000934
database_name: lh_1c_raw_prd
database_s3_location: "s3://dev-lh1-spec-src/raw/current/prd/src/1c/"
database_description: "Database for 1c to Lakehouse Ingestion Patterns"
aws_account_id: '438465132548'
region: us-east-1
data_construct: Source
data_env: prd
data_layer: raw
source_name: 1c
data_classification: "Confidential - Limited"
data_privacy: "NONE"
enterprise_or_func_name: SPEC
enterprise_or_func_subgrp_name: ANH
data_owner_email: "shawn_yeager@cargill.com"
data_owner_github_uname: ShawnYeager
data_leader: jawillho
```

## Example 2: Lakehouse Raw CDP Source (FOOD/RD)
```yaml
intake_id: M0000426
database_name: lh_cdp_cmmp_raw_prd
database_s3_location: "s3://dev-lh1-food-src/raw/cdp/prd/src/cmmp/"
database_description: "Used to store raw tables for CMMP Source"
aws_account_id: '438465132548'
region: us-east-1
data_construct: Source
data_env: prd
data_layer: raw
source_name: cdp
data_classification: "Confidential - Limited"
data_privacy: "PI"
enterprise_or_func_name: FOOD
enterprise_or_func_subgrp_name: RD
data_owner_email: "hitesh_mangtani@cargill.com"
data_owner_github_uname: HiteshMangtani
data_leader: KimeraAppanna
```

## Example 3: Compute Curated DataProduct (AGTR/NA)
```yaml
intake_id: M0000801
database_name: na_lynx_dm_curated_prd
database_s3_location: "s3://dev-cmp1-na-dp/curated/prd/na/lynx_dm/"
database_description: "Stores Curated Product data for the Lynx domain models"
aws_account_id: 068887784423
region: us-east-1
data_env: prd
data_layer: cur
data_construct: DataProduct
data_classification: "Confidential - Limited"
data_privacy: "PI"
enterprise_or_func_name: AGTR
enterprise_or_func_subgrp_name: NA
data_product_name: "lynx_dm"
data_owner_email: "Arun_Channaveerappa@cargill.com"
data_owner_github_uname: ArunChannaveerappa
data_leader: jcook
```

## Example 4: Compute Serving DataProduct (FOOD/CE)
```yaml
intake_id: M0000523
database_name: ce_c360_serving_dev
database_s3_location: "s3://dev-cmp2-ce-dp/serving/dev/ce/C360/"
database_description: "Store C360 Serving Data Product for FOOD CE"
aws_account_id: 933999308564
region: us-east-1
data_construct: DataProduct
data_env: dev
data_layer: srv
data_product_name: C360
data_classification: "Confidential - General Use"
data_privacy: "NONE"
enterprise_or_func_name: FOOD
enterprise_or_func_subgrp_name: CE
data_owner_email: "Kyle_Britt@cargill.com"
data_owner_github_uname: k603569
data_leader: k418671
```

## Example 5: Compute Internal DataProduct (AGTR/NA)
```yaml
intake_id: M0000801
database_name: na_lynx_dm_stg_internal_prd
database_s3_location: "s3://dev-cmp1-na-dp/internal/prd/na/lynx_dm_stg/"
database_description: "Stores internal staging data needed for building the Lynx domain models"
aws_account_id: 068887784423
region: us-east-1
data_env: prd
data_layer: int
data_construct: DataProduct
data_classification: "Confidential - Limited"
data_privacy: "PI"
enterprise_or_func_name: AGTR
enterprise_or_func_subgrp_name: NA
data_product_name: "lynx_dm_stg"
data_owner_email: "Arun_Channaveerappa@cargill.com"
data_owner_github_uname: ArunChannaveerappa
data_leader: jcook
```
