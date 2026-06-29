# IAM Resource — Agent Guide

## Agent Rules
- On the first collection turn, present ALL remaining mandatory fields (that
  aren't auto-set) with their format, constraints, and allowed values
- Tell the user: "You can provide all of these in one message, or one at a time."
- On subsequent turns, extract ALL provided fields, then show remaining mandatory fields
- After all mandatory fields are collected, present optional fields with their defaults
- If user provides multiple fields in one message, extract all of them first,
  then only ask for what is still missing — never re-ask a field already provided
- Max 3 retries per field
  - Mandatory field fails 3 retries → abort session:
    "Cannot complete without valid <field>. Please restart."
  - Optional field fails 3 retries → skip and note it as unresolved in YAML comment
- Never ask for auto-generated or auto-set fields
- Normalize input before validation
- Validate every value against regex or enum before storing
- Show confirmation summary before generating YAML
- Reject unknown fields: "Field not recognized, will be excluded"
- Single-quote `aws_account_id` in YAML output — prevents integer parsing
- `access_to_resources` is a nested structure — collect each sub-field
  separately in the defined order
- When asking for list fields, accept comma-separated input and split into list items
- `enterprise_or_func_name` not in known list → warn and ask to confirm, do not reject
- `enable_glue_interactive_session: true` → warn about cost and ask to confirm
- `snowflake_iceberg_support: true` → warn and ask to confirm
- Never ask for optional nested fields (`athena_access_config`,
  `glue_job_access_config`, `stsExternalIds`) unless user mentions them

---

## Fields

| Field | Req | Default | Allowed / Validation |
|-------|-----|---------|----------------------|
| `intake_id` | ✅ | — | Format: `X-NNNNNN` e.g. `M-300003` |
| `role_name` | ✅ | — | `/^[a-z0-9][a-z0-9\-]{1,61}[a-z0-9]$/` + convention: `<env>-<func>-<purpose>-role` |
| `role_description` | ✅ | — | 1–256 chars — always double-quoted |
| `aws_account_id` | ✅ | — | Enum: `904233109241`, `650252464149` — always single-quoted |
| `enterprise_or_func_name` | ✅ | — | Known: `AGTR`, `CORP`, `FIN` — warn+confirm if unknown |
| `enterprise_or_func_subgrp_name` | ❌ | `""` | `/^[A-Z]{2,10}$|^$/` — always include even if empty |
| `role_owner` | ✅ | — | `/^[^@\s]+@[^@\s]+\.[^@\s]+$/` — email format — always double-quoted |
| `data_env` | ✅ | — | Enum: `snd`, `dev`, `prd` |
| `usage_type` | ✅ | — | Enum: `DataEngineer`, `DataScientist`, `DataAnalyst`, `MLEngineer` — always double-quoted |
| `principal_role_arn` | ✅ | — | `/^arn:aws:iam::\d{12}:role\/[a-zA-Z0-9+=,.@_\/-]+$/` — no quotes |
| `access_to_resources.glue_databases.write` | ✅ | `[]` | List of database name strings — can be empty list |
| `access_to_resources.glue_databases.read` | ✅ | `[]` | List of database name strings — can be empty list |
| `access_to_resources.data_prefixes` | ✅ | `[]` | List — each item must start with `s3://` — always double-quoted |
| `access_to_resources.execution_asset_prefixes` | ❌ | `[]` | List — each item must start with `s3://` — omit from YAML if empty |
| `access_to_resources.glue_crawler` | ❌ | `[]` | List of strings — omit from YAML if empty |
| `enable_glue_interactive_session` | ❌ | `false` | Bool — ask only if user raises it — omit from YAML if false |
| `snowflake_iceberg_support` | ❌ | `false` | Bool — ask only if user raises it — omit from YAML if false |
| `max_session_duration` | ❌ | `3600` | Integer seconds — omit from YAML if default |
| `stsExternalIds` | ❌ | — | List of strings — omit from YAML if not provided |
| `athena_access_config` | ❌ | — | Nested object — omit from YAML if not provided |
| `glue_job_access_config` | ❌ | — | Nested object — omit from YAML if not provided |

---

## Dependency Rules

| Condition | Action |
|-----------|--------|
| `data_prefixes` item missing `s3://` prefix | Error: "Each data prefix must start with s3://" |
| `execution_asset_prefixes` item missing `s3://` | Error: "Each execution asset prefix must start with s3://" |
| `execution_asset_prefixes` list is empty | Omit `execution_asset_prefixes` block from YAML entirely |
| `glue_crawler` list is empty | Omit `glue_crawler` block from YAML entirely |
| `enable_glue_interactive_session = true` | Warn: "Enables interactive sessions — additional cost. Confirm? (yes/no)" |
| `snowflake_iceberg_support = true` | Warn: "Enables Snowflake Iceberg support. Confirm? (yes/no)" |
| `stsExternalIds` not provided by user | Omit from YAML entirely |
| `max_session_duration` = 3600 | Omit from YAML (default value, not needed) |
| `enable_glue_interactive_session = false` | Omit from YAML |
| `snowflake_iceberg_support = false` | Omit from YAML |
| `athena_access_config` not provided | Omit from YAML |
| `glue_job_access_config` not provided | Omit from YAML |

---

## Normalization Rules
Apply before validation. Silently correct unless noted.

| Field | User Input Examples | Normalize To |
|-------|-------------------|--------------|
| `data_env` | `production`, `prod` | `prd` |
| `data_env` | `sandbox` | `snd` |
| `data_env` | `development` | `dev` |
| `usage_type` | `data engineer`, `dataengineer`, `engineer` | `DataEngineer` |
| `usage_type` | `data scientist`, `datascientist`, `scientist` | `DataScientist` |
| `usage_type` | `data analyst`, `dataanalyst`, `analyst` | `DataAnalyst` |
| `usage_type` | `ml engineer`, `mlengineer`, `ml` | `MLEngineer` |
| `enterprise_or_func_name` | `agtr`, `Agtr` | `AGTR` |
| `enterprise_or_func_name` | `corp`, `Corp` | `CORP` |
| `enterprise_or_func_name` | `fin`, `Fin` | `FIN` |
| `enterprise_or_func_subgrp_name` | `apac`, `cdl`, any lowercase | uppercase |
| `role_name` | uppercase letters or underscores | lowercase hyphens |
| Bool fields | `yes`, `YES`, `1`, `"true"` | `true` |
| Bool fields | `no`, `NO`, `0`, `"false"` | `false` |
| List fields | comma-separated string | split into list, trim whitespace |

---

## role_name Convention
Pattern: `<env>-<func>-<purpose>-role`

| Segment | Values |
|---------|--------|
| `<env>` | `prd`, `snd`, `dev` |
| `<func>` | lowercase of `enterprise_or_func_name` e.g. `agtr` |
| `<purpose>` | short descriptor e.g. `data`, `eng`, `analyst` |
| `role` | fixed suffix |

Example: `env=snd`, `func=agtr`, `purpose=data` → `snd-agtr-data-role`

Convention broken → suggest correction, ask user to confirm before using.
Regex broken → error, retry.

---

## Collection Flow

### PHASE 1 — Mandatory Fields (present upfront)
Present all of these to the user on the first turn with their constraints:
- `intake_id` — format: `X-NNNNNN` (e.g. `M-300003`)
- `role_name` — lowercase+hyphens, convention: `<env>-<func>-<purpose>-role`
- `role_description` — 1–256 chars
- `aws_account_id` — allowed: `904233109241`, `650252464149` (single-quoted in YAML)
- `enterprise_or_func_name` — known: `AGTR`, `CORP`, `FIN` (warn+confirm if unknown)
- `role_owner` — valid email address
- `data_env` — one of: `snd`, `dev`, `prd`
- `usage_type` — one of: `DataEngineer`, `DataScientist`, `DataAnalyst`, `MLEngineer`
- `principal_role_arn` — format: `arn:aws:iam::<account_id>:role/<role_name>`
- `access_to_resources.glue_databases.write` — list of Glue database names (comma-separated)
- `access_to_resources.glue_databases.read` — list of Glue database names (comma-separated)
- `access_to_resources.data_prefixes` — list of S3 prefixes (each must start with `s3://`)

No auto-set mandatory fields for IAM.

Tell user: "You can provide all of these in a single message, or we can go through them one at a time."

### PHASE 2 — Optional Fields (present after all mandatory done)
Present these with their defaults:
- `enterprise_or_func_subgrp_name` — default: `""` (short uppercase e.g. `APAC`)
- `enable_glue_interactive_session` — default: `false` (warn about cost if `true`)
- `snowflake_iceberg_support` — default: `false` (warn if `true`)
- `max_session_duration` — default: `3600` seconds
- `execution_asset_prefixes` — default: `[]` (each must start with `s3://`)
- `glue_crawler` — default: `[]`
- `stsExternalIds` — default: omitted
- `athena_access_config` — default: omitted (nested object)
- `glue_job_access_config` — default: omitted (nested object)

Ask: "Would you like to customize any of these, or proceed with defaults?"

### PHASE 3 — Confirmation summary → user approves → generate YAML

---

## YAML Generation Rules

1. Field order: `intake_id` → `role_name` → `role_description` → `aws_account_id` → `enterprise_or_func_name` → `enterprise_or_func_subgrp_name` → `role_owner` → `data_env` → `usage_type` → `access_to_resources` → `principal_role_arn` → optional fields (only if provided and non-default)
2. Always include `enterprise_or_func_subgrp_name` even if empty string
3. Omit optional fields at default value unless the guide says to always include them
4. **Quoting rules:**
   - `aws_account_id` → always single-quoted e.g. `'904233109241'`
   - `role_description` → always double-quoted e.g. `"Data access role for AGTR"`
   - `role_owner` → always double-quoted e.g. `"owner@company.com"`
   - `usage_type` → always double-quoted e.g. `"DataEngineer"`
   - `data_prefixes` items → always double-quoted e.g. `"s3://snd-lh1-agtr-src/raw"`
   - `principal_role_arn` → no quotes e.g. `arn:aws:iam::904233109241:role/snd-agtr-principal`
   - Plain strings → no quotes e.g. `snd-agtr-data-role`, `AGTR`
   - Booleans → no quotes e.g. `true`, `false`
5. **access_to_resources YAML indentation:**
   - Sub-keys (`glue_databases`, `data_prefixes`) indented 4 spaces
   - Keys under `glue_databases` (`write`, `read`) indented 8 spaces
   - List items under all sub-keys indented with 2 extra spaces + dash
   - Always include both `write` and `read` under `glue_databases` even if one list is empty

---

## Templates

### Minimal
```yaml
intake_id: M-300003
role_name: snd-agtr-data-role
role_description: "Data access role for AGTR"
aws_account_id: '904233109241'
enterprise_or_func_name: AGTR
enterprise_or_func_subgrp_name: APAC
role_owner: "owner@company.com"
data_env: snd
usage_type: "DataEngineer"
access_to_resources:
    glue_databases:
        write:
          - lh_agtr
        read:
          - lh_agtr_raw
    data_prefixes:
      - "s3://snd-lh1-agtr-src/raw"
principal_role_arn: arn:aws:iam::904233109241:role/snd-agtr-principal
```

### With Optional Fields
```yaml
intake_id: M-300004
role_name: snd-agtr-eng-role
role_description: "Engineering role for AGTR data pipeline"
aws_account_id: '904233109241'
enterprise_or_func_name: AGTR
enterprise_or_func_subgrp_name: ""
role_owner: "engineer@company.com"
data_env: snd
usage_type: "DataEngineer"
access_to_resources:
    glue_databases:
        write:
          - lh_agtr
          - lh_agtr_raw
        read:
          - lh_agtr_cln
    data_prefixes:
      - "s3://snd-lh1-agtr-src/raw"
      - "s3://snd-lh1-agtr-src/clean"
    execution_asset_prefixes:
      - "s3://snd-lh1-agtr-eng/assets"
principal_role_arn: arn:aws:iam::904233109241:role/snd-agtr-eng-principal
enable_glue_interactive_session: true
```

---

## Validation Errors & Warnings

| Field | Condition | Type | Message |
|:--|:--|:--|:--|
| `intake_id` | Regex fail | Error | "Must follow X-NNNNNN (e.g., M-300003)" |
| `role_name` | Regex fail | Error | "Must be lowercase with hyphens only. Suggested: `<fix>`" |
| `role_name` | Convention fail | Warn | "Doesn't follow `<env>-<func>-<purpose>-role`. Did you mean `<suggested>`? (yes/no)" |
| `aws_account_id` | Not in enum | Error | "Not registered. Allowed: 904233109241, 650252464149" |
| `role_owner` | Not valid email | Error | "Must be a valid email address e.g. user@company.com" |
| `data_env` | Not in enum | Error | "Must be one of: snd, dev, prd" |
| `usage_type` | Not in enum | Error | "Must be one of: DataEngineer, DataScientist, DataAnalyst, MLEngineer" |
| `principal_role_arn` | Regex fail | Error | "Must follow: arn:aws:iam::<account_id>:role/<role_name>" |
| `data_prefixes` item | Missing `s3://` | Error | "Each prefix must start with s3://" |
| `enterprise_or_func_name` | Unknown value | Warn | "Not in known list (AGTR, CORP, FIN). Is `<value>` correct? (yes/no)" |
| Mandatory field | 3 failed attempts | Abort | "Cannot complete without valid `<field>`. Please restart." |
| Optional field | 3 failed attempts | Flag | "Skipping `<field>`. Add comment: # UNRESOLVED — fix before submitting" |
