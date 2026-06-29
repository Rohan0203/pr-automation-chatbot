# Glue DB Resource - Generator Context

## Overview

This document contains all information needed to generate a valid Glue DB YAML configuration for a PR. The resource type is `glue_db`.

---

## Field Classification

Fields are classified by dependency and input requirement. The agent uses this internally to decide what to ask and when.

### Class A — Core Identity (independent, ask first — these shape everything else)

| Field | Allowed Values |
|-------|---------------|
| `data_construct` | `Source` or `DataProduct` |
| `data_layer` | `raw`, `raw_serving`, `curated`, `serving`, `internal` |
| `data_env` | `dev` or `prd` |
| `enterprise_or_func_name` | `AGTR`, `CORP`, `FOOD`, `SPEC` |

### Class B — Conditional (depends on Class A, requires user input)

| Field | Condition | Notes |
|-------|-----------|-------|
| `source_name` | Only if `data_construct = Source` | Lowercase, underscores, no spaces (e.g. `concur`, `sap`) |
| `data_product_name` | Only if `data_construct = DataProduct` | Lowercase, underscores, no spaces (e.g. `controls`, `lynx_dm`) |
| `enterprise_or_func_subgrp_name` | Allowed values filtered by `enterprise_or_func_name` | See subgroup table below |
| `purpose` | Only if `data_layer = serving` | Mandatory for serving (e.g. `analytics`, `events`, `reporting`) |
| `cdp_flag` | Only if `data_construct = Source` | `yes` or `no`. Indicates data originates from CDP. Affects naming (`lh_cdp_...`) and S3 path. Default: `no`. Ask only if Source. |
| `source_system_instance` | Only if `data_construct = Source` | Optional sub-instance of source system (e.g. `tc1`, `tcf`). Appended after source_name in naming. Leave blank if none. |

> `source_name` and `data_product_name` are mutually exclusive. Ask for only the relevant one based on `data_construct`. In the final YAML, only include the relevant field — omit the other entirely.
> `cdp_flag` and `source_system_instance` are metadata fields used for naming/S3 derivation but are NOT included in the final YAML output.

### Class C — Ownership (independent, always required, user must provide)

| Field | Validation |
|-------|------------|
| `intake_id` | Starts with `M`, followed by digits, max 10 chars (e.g. `M123456`) |
| `data_owner_email` | Valid email, always double-quoted in YAML |
| `data_owner_github_uname` | Alphanumeric, max 30 chars |
| `data_leader` | Alphanumeric, max 10 chars (e.g. `a123456`) |

### Class D — Defaults (auto-set, user can override in confirmation)

| Field | Default Value | Notes |
|-------|--------------|-------|
| `region` | `us-east-1` | Always this value. Auto-set, inform once, never ask. |
| `data_classification` | `Confidential - General Use` | Pre-filled. User can change in confirmation. |
| `data_privacy` | `NONE` | Pre-filled. User can change in confirmation. |

### Class E — Fully Derived (auto-generated from A+B, shown for confirmation)

| Field | Derived From |
|-------|-------------|
| `database_name` | Naming convention rules using `data_construct`, `data_layer`, `source_name`/`data_product_name`, `enterprise_or_func_subgrp_name`, `data_env`, `purpose` |
| `database_s3_location` | S3 location patterns using all of the above + account type |
| `aws_account_id` | Account selection logic using `data_layer`, `data_construct`, `enterprise_or_func_name`, `data_env` |
| `database_description` | Auto-generate from current config. Pattern: "Store [data_layer] [source_name or data_product_name] data for [enterprise] [subgroup]". MUST be re-derived on every edit — never keep a stale description from a previous configuration. |

---

## Adaptive Collection Flow

**Rule: Extract first, ask only what's missing, never re-ask.**

On every turn:
1. Extract ALL recognizable fields from the user's message (apply normalization silently)
2. Check what's still missing
3. If nothing missing → apply Class D defaults, derive Class E fields, show YAML preview with "Confirm, edit, or cancel?"
4. If fields are missing → ask all remaining fields grouped meaningfully in ONE message (not one field at a time)
5. Never re-ask a field already provided or derived
6. Max 3 turns to reach YAML preview

**Opening behavior:** After confirming the user wants a Glue DB, ask ONE natural opening question:
> "Can you describe what this Glue DB is for? (e.g. 'Raw source database for Concur data in FOOD/RD, dev environment' — or just share all the details you have)"

Accept any format: technical field dump, natural language description, or partial info.

**Edit-Reset Rules (when user edits fields during confirmation):**
When the user edits fields after YAML preview, apply these cascade rules:
1. **If any Class A field changes** (data_construct, data_layer, data_env, enterprise_or_func_name):
   - Re-derive ALL Class E fields (database_name, database_s3_location, aws_account_id, database_description)
   - Re-evaluate which Class B fields are relevant (e.g. switching Source→DataProduct means drop source_name, cdp_flag, source_system_instance and ask for data_product_name)
   - Clear stale Class B fields that no longer apply
   - Re-validate enterprise_or_func_subgrp_name against new enterprise's allowed values — if invalid, clear and re-ask
2. **If any Class B field changes** (source_name, data_product_name, subgroup, purpose, cdp_flag, source_system_instance):
   - Re-derive ALL Class E fields
3. **Always re-derive `database_description`** to match the new configuration context (e.g. "Store [layer] data for [source/product] in [enterprise] [subgroup]")
4. **Never carry over stale values** — if a field no longer applies to the new configuration, remove it entirely

**Asking behavior when fields are missing:**
- Group remaining fields meaningfully — don't list all fields as a raw form dump
- Show allowed values inline (e.g. "enterprise: AGTR / CORP / FOOD / SPEC")
- Say "You can provide all of these in one message"

---

## Allowed Account IDs

### Dev Accounts

| Account ID | Alias | Type | Enterprise |
|------------|-------|------|------------|
| `438465132548` | minerva-dev-lakehouse-001 | Lakehouse | All |
| `068887784423` | minerva-dev-compute-001 | Compute | AGTR |
| `933999308564` | minerva-dev-compute-002 | Compute | FOOD |
| `836901248866` | minerva-dev-compute-003 | Compute | SPEC |
| `324612370323` | minerva-dev-compute-004 | Compute | CORP |

### Prod Accounts

| Account ID | Alias | Type | Enterprise |
|------------|-------|------|------------|
| `578647603827` | minerva-prod-lakehouse-001 | Lakehouse | All |
| `367241115350` | minerva-prod-compute-001 | Compute | AGTR |
| `884308299029` | minerva-prod-compute-002 | Compute | FOOD |
| `011379513867` | minerva-prod-compute-003 | Compute | SPEC |
| `632247962242` | minerva-prod-compute-004 | Compute | CORP |

### Account Selection Logic

Follow these steps IN ORDER to select the correct `aws_account_id`:

**Step 1 — Determine account TYPE (Lakehouse or Compute):**
- `data_layer` is `raw` or `raw_serving` → **Lakehouse**
- `data_construct = Source` AND `data_layer = internal` → **Lakehouse**
- `data_layer` is `curated` or `serving` → **Compute**
- `data_construct = DataProduct` AND `data_layer = internal` → **Compute**

**Step 2 — Determine account ENVIRONMENT from `data_env`:**
- `data_env = dev` → use **Dev Accounts** table above
- `data_env = prd` → use **Prod Accounts** table above

**Step 3 — Pick the specific account:**
- If Lakehouse → there is exactly ONE Lakehouse account per environment (serves All enterprises)
  - dev: `438465132548`, prd: `578647603827`
- If Compute → pick by `enterprise_or_func_name`:
  - AGTR → compute-001 (dev: `068887784423`, prd: `367241115350`)
  - FOOD → compute-002 (dev: `933999308564`, prd: `884308299029`)
  - SPEC → compute-003 (dev: `836901248866`, prd: `011379513867`)
  - CORP → compute-004 (dev: `324612370323`, prd: `632247962242`)

**Example:** data_layer=curated, data_env=prd, enterprise=SPEC → Compute + Prod + SPEC → `011379513867`
**Example:** data_layer=raw, data_env=dev → Lakehouse + Dev → `438465132548`
**Example:** data_layer=raw, data_env=prd → Lakehouse + Prod → `578647603827`

---

## Subgroup Allowed Values

| Enterprise | Allowed Subgroups |
|------------|-------------------|
| AGTR | EMEA, NA, LATAM, APAC, WTG, WTG_CDAS, OT, CRM, TCM, MET |
| CORP | GI_SUST, EHS, FIN, GTC, CPT, HR, AUDIT, DTD, LAW, DTD_DPE, RMG, FSQR, DTD_GIS |
| FOOD | FSGL, FS_NA, FS_LATAM, FS_APAC, FS_EMEA, PRGL, PR_LATAM, PR_NA, PR_APAC, SALT, CE, RD |
| SPEC | ANH, CBI, DS |

---

## Naming Conventions

### Database Name Patterns

**Lakehouse - Raw Source:**
`lh_[<cdp>_][source_name][_<instance>]_raw_[data_env]`
Examples: `lh_concur_raw_dev`, `lh_cdp_sap_tc1_raw_dev`, `lh_1c_raw_prd`

**Lakehouse - Raw Serving Source:**
`lh_[<cdp>_][source_name][_<instance>]_raw_serving_[data_env]`
Example: `lh_concur_raw_serving_dev`

**Lakehouse - Source Internal:**
`lh_[source_name][_<instance>]_internal_[data_env]`
Example: `lh_concur_internal_dev`

**Lakehouse - CDP DataProduct Raw:**
`lh_cdp_[owning_entity]_[product_name]_raw_[data_env]`
Example: `lh_cdp_fin_controls_raw_dev`

**Compute - Curated:**
`[owning_entity]_[product_name]_curated_[data_env]`
Examples: `fin_controls_curated_dev`, `na_lynx_dm_curated_prd`

**Compute - Serving (PURPOSE is mandatory):**
`[owning_entity]_[product_name]_serving_[purpose]_[data_env]`
Example: `hr_successfactors_serving_analytics_dev`

**Compute - Internal:**
`[owning_entity]_[product_name]_internal_[data_env]`
Example: `fin_controls_internal_dev`, `na_lynx_dm_stg_internal_prd`

### OWNING_ENTITY

- For **DataProduct**: `owning_entity` = lowercase of `enterprise_or_func_subgrp_name` (e.g. `FIN` -> `fin`, `NA` -> `na`)
- For **Source**: not used in naming (use `source_name` instead)

---

## S3 Location Patterns

**CRITICAL:** The `[env]` variable in ALL bucket names below is derived from `data_env`:
- `data_env = dev` → `[env]` = `dev`
- `data_env = prd` → `[env]` = `prd`

The S3 location is: `s3://[BUCKET]/[PREFIX]`

### Lakehouse Buckets

Bucket name format:
- With subgroup: `[env]-lh1-[enterprise_lower]-[subgrp_lower]-src`
- Without subgroup: `[env]-lh1-[enterprise_lower]-src`

Where:
- `[env]` = `data_env` (dev or prd)
- `[enterprise_lower]` = lowercase of `enterprise_or_func_name`
- `[subgrp_lower]` = lowercase of `enterprise_or_func_subgrp_name`

Prefix patterns (appended after bucket):
- Raw current: `raw/current/[data_env]/src/[source_name]/`
- Raw CDP source: `raw/cdp/[data_env]/src/[source_name][_instance]/`
- Raw CDP product: `raw/cdp/[data_env]/dp/[product_name]/`
- Raw serving: `raw_serving/[data_env]/src/[source_name]/`
- Internal: `internal/[data_env]/src/[source_name]/`

**Example:** data_env=prd, enterprise=AGTR, subgroup=NA, source=concur, layer=raw
→ Bucket: `prd-lh1-agtr-na-src`, Prefix: `raw/current/prd/src/concur/`
→ Full: `s3://prd-lh1-agtr-na-src/raw/current/prd/src/concur/`

### Compute Buckets

Bucket name format: `[env]-cmp[N]-[subgrp_lower]-dp`

Where:
- `[env]` = `data_env` (dev or prd)
- `[N]` = compute account number by enterprise (1=AGTR, 2=FOOD, 3=SPEC, 4=CORP)
- `[subgrp_lower]` = lowercase of `enterprise_or_func_subgrp_name`

Prefix patterns:
- Curated: `curated/[data_env]/[subgrp_lower]/[product_name]/`
- Serving: `serving/[data_env]/[subgrp_lower]/[product_name]/[purpose]/`
- Internal: `internal/[data_env]/[subgrp_lower]/[product_name]/`

**Example:** data_env=prd, enterprise=SPEC, subgroup=WTG, product=general_ledger, layer=curated
→ N=3 (SPEC), Bucket: `prd-cmp3-wtg-dp`, Prefix: `curated/prd/wtg/general_ledger/`
→ Full: `s3://prd-cmp3-wtg-dp/curated/prd/wtg/general_ledger/`

---

## Normalization Rules

Apply silently - never reject a value that can be normalized.

| Field | Input Examples | Normalize To |
|-------|---------------|--------------|
| `data_layer` | `cur`, `CUR`, `Cur` | `curated` |
| `data_layer` | `srv`, `SRV`, `Srv` | `serving` |
| `data_layer` | `int`, `INT`, `Internal` | `internal` |
| `data_layer` | `RAW`, `Raw` | `raw` |
| `data_layer` | `raw serving`, `RAW_SERVING` | `raw_serving` |
| `data_construct` | `source`, `SOURCE`, `src` | `Source` |
| `data_construct` | `dataproduct`, `data product`, `dp`, `DP` | `DataProduct` |
| `data_env` | `DEV`, `Dev` | `dev` |
| `data_env` | `PRD`, `Prd`, `prod`, `production` | `prd` |
| `enterprise_or_func_name` | `agtr`, `Agtr` | `AGTR` |
| `enterprise_or_func_name` | `corp`, `Corp` | `CORP` |
| `enterprise_or_func_name` | `food`, `Food` | `FOOD` |
| `enterprise_or_func_name` | `spec`, `Spec` | `SPEC` |
| `enterprise_or_func_subgrp_name` | `fin`, `Fin` | `FIN` |
| `enterprise_or_func_subgrp_name` | `hr`, `Hr` | `HR` |
| `source_name` | `Concur`, `SAP` | `concur`, `sap` (lowercase) |
| `data_product_name` | `Controls`, `Lynx DM` | `controls`, `lynx_dm` (lowercase, underscores) |

---

## YAML Generation Rules

1. **Field order:** `intake_id` -> `database_name` -> `database_s3_location` -> `database_description` -> `aws_account_id` -> `region` -> `data_env` -> `data_layer` -> `data_construct` -> `source_name` -> `data_product_name` -> `data_owner_email` -> `data_owner_github_uname` -> `data_leader` -> `enterprise_or_func_name` -> `enterprise_or_func_subgrp_name` -> `data_classification` -> `data_privacy`
2. Always include `enterprise_or_func_subgrp_name` even if empty string `""`
3. Always include all fields - they are all mandatory
4. **Quoting rules:**
   - `aws_account_id` -> always single-quoted (e.g. `'438465132548'`)
   - `database_s3_location` -> always double-quoted
   - `database_description` -> always double-quoted
   - `data_owner_email` -> always double-quoted
   - `data_classification` -> double-quoted if contains spaces
   - Plain strings (no spaces) -> no quotes
5. If `data_construct = Source` → include `source_name`, **do NOT include `data_product_name` at all**
6. If `data_construct = DataProduct` → include `data_product_name`, **do NOT include `source_name` at all**
7. Do NOT include fields not in the template
8. **`cdp_flag` and `source_system_instance` are NEVER included in the YAML output** — they are only used to derive `database_name` and `database_s3_location`

---

## Templates / Examples

### Lakehouse - Source Raw

intake_id: M0000934
database_name: lh_1c_raw_prd
database_s3_location: "s3://dev-lh1-spec-src/raw/current/prd/src/1c/"
database_description: "Database for 1c to Lakehouse Ingestion Patterns"
aws_account_id: '438465132548'
region: us-east-1
data_env: prd
data_layer: raw
data_construct: Source
source_name: 1c
data_owner_email: "shawn_yeager@cargill.com"
data_owner_github_uname: ShawnYeager
data_leader: jawillho
enterprise_or_func_name: SPEC
enterprise_or_func_subgrp_name: ANH
data_classification: "Confidential - Limited"
data_privacy: NONE

### Lakehouse - CDP Source Raw

intake_id: M0000426
database_name: lh_cdp_cmmp_raw_prd
database_s3_location: "s3://dev-lh1-food-src/raw/cdp/prd/src/cmmp/"
database_description: "Used to store raw tables for CMMP Source"
aws_account_id: '438465132548'
region: us-east-1
data_env: prd
data_layer: raw
data_construct: Source
source_name: cdp
data_owner_email: "hitesh_mangtani@cargill.com"
data_owner_github_uname: HiteshMangtani
data_leader: KimeraAppanna
enterprise_or_func_name: FOOD
enterprise_or_func_subgrp_name: RD
data_classification: "Confidential - Limited"
data_privacy: PI

### Compute - Curated DataProduct

intake_id: M0000801
database_name: na_lynx_dm_curated_prd
database_s3_location: "s3://dev-cmp1-na-dp/curated/prd/na/lynx_dm/"
database_description: "Stores Curated Product data for the Lynx domain models"
aws_account_id: '068887784423'
region: us-east-1
data_env: prd
data_layer: curated
data_construct: DataProduct
data_product_name: lynx_dm
data_owner_email: "Arun_Channaveerappa@cargill.com"
data_owner_github_uname: ArunChannaveerappa
data_leader: jcook
enterprise_or_func_name: AGTR
enterprise_or_func_subgrp_name: NA
data_classification: "Confidential - Limited"
data_privacy: PI

### Compute - Serving DataProduct

intake_id: M0000523
database_name: ce_c360_serving_dev
database_s3_location: "s3://dev-cmp2-ce-dp/serving/dev/ce/C360/"
database_description: "Store C360 Serving Data Product for FOOD CE"
aws_account_id: '933999308564'
region: us-east-1
data_env: dev
data_layer: serving
data_construct: DataProduct
data_product_name: C360
data_owner_email: "Kyle_Britt@cargill.com"
data_owner_github_uname: k603569
data_leader: k418671
enterprise_or_func_name: FOOD
enterprise_or_func_subgrp_name: CE
data_classification: "Confidential - General Use"
data_privacy: NONE

### Compute - Internal DataProduct

intake_id: M0000801
database_name: na_lynx_dm_stg_internal_prd
database_s3_location: "s3://dev-cmp1-na-dp/internal/prd/na/lynx_dm_stg/"
database_description: "Stores internal staging data needed for building the Lynx domain models"
aws_account_id: '068887784423'
region: us-east-1
data_env: prd
data_layer: internal
data_construct: DataProduct
data_product_name: lynx_dm_stg
data_owner_email: "Arun_Channaveerappa@cargill.com"
data_owner_github_uname: ArunChannaveerappa
data_leader: jcook
enterprise_or_func_name: AGTR
enterprise_or_func_subgrp_name: NA
data_classification: "Confidential - Limited"
data_privacy: PI
