# S3 Bucket Validation Rules

> Reviewer: evaluate the YAML against ONLY these RULE blocks.
> If a RULE block is not listed here, it does not exist — do NOT invent rules.
> If all rules pass, return passed=true with zero violations.

---

## REFERENCE: Account Table

| Account ID | Env | Type | Enterprise | Bucket Prefix |
|------------|-----|------|------------|---------------|
| 438465132548 | dev | Lakehouse | Common | dev-lh1- |
| 068887784423 | dev | Compute | AGTR | dev-cmp1- |
| 933999308564 | dev | Compute | FOOD | dev-cmp2- |
| 836901248866 | dev | Compute | SPEC | dev-cmp3- |
| 324612370323 | dev | Compute | CORP | dev-cmp4- |
| 578647603827 | prd | Lakehouse | Common | prd-lh1- |
| 367241115350 | prd | Compute | AGTR | prd-cmp1- |
| 884308299029 | prd | Compute | FOOD | prd-cmp2- |
| 011379513867 | prd | Compute | SPEC | prd-cmp3- |
| 632247962242 | prd | Compute | CORP | prd-cmp4- |

---

## RULE S3-FLD-001
- **SEVERITY:** ERROR
- **CHECK:** All 8 mandatory fields must be present: `intake_id`, `bucket_name`, `bucket_description`, `aws_account_id`, `aws_region`, `usage_type`, `enterprise_or_func_name`, `enterprise_or_func_subgrp_name`
- **EXPECTED:** All 8 fields exist and are non-empty (except `enterprise_or_func_subgrp_name` which may be `""`)

## RULE S3-FLD-002
- **SEVERITY:** ERROR
- **CHECK:** `intake_id` must not be a generic placeholder like `123456`, `000000`, `111111`
- **EXPECTED:** A real intake ID (e.g. `M0000452`, `I-123456`)

## RULE S3-FLD-003
- **SEVERITY:** WARNING
- **CHECK:** No unknown/extra fields should be present beyond the 8 mandatory fields
- **EXPECTED:** Only the 8 mandatory fields plus optionally `versioning_enabled` (for Scripts only). Fields like `public_access_blocked`, `encryption_enabled`, `encryption_type`, `encryption_key_arn` are NOT expected — ignore them if present but do NOT flag as error.

---

## RULE S3-ACC-001
- **SEVERITY:** ERROR
- **CHECK:** `aws_account_id` must be one of the 10 known accounts in the Account Table
- **EXPECTED:** Account ID exists in the table above

## RULE S3-ACC-002
- **SEVERITY:** ERROR
- **CHECK:** `aws_region` must be `us-east-1`
- **EXPECTED:** `us-east-1`

## RULE S3-ACC-003
- **SEVERITY:** ERROR
- **CHECK:** The environment in `bucket_name` prefix must match the account's environment
- **EXPECTED:** If account is dev → bucket starts with `dev-`. If account is prd → bucket starts with `prd-`. Look up account env from Account Table.

---

## RULE S3-NAM-001
- **SEVERITY:** ERROR
- **CHECK:** `bucket_name` must be lowercase, DNS-compliant (letters, numbers, hyphens only), 3–63 characters
- **EXPECTED:** No uppercase, no underscores, no spaces, no special characters

## RULE S3-NAM-002
- **SEVERITY:** ERROR
- **CHECK:** `bucket_name` must start with the correct prefix for the given `aws_account_id`
- **EXPECTED:** Look up the account in the Account Table and use the **Bucket Prefix** column. Example: account `367241115350` → prefix must be `prd-cmp1-`. Account `632247962242` → prefix must be `prd-cmp4-`.

## RULE S3-NAM-003
- **SEVERITY:** ERROR
- **CHECK:** `bucket_name` must end with a valid purpose suffix
- **EXPECTED:** One of: `-src`, `-dp`, `-scripts`, `-eng-assets`

## RULE S3-NAM-004
- **SEVERITY:** ERROR
- **CHECK:** The purpose suffix of `bucket_name` must match `usage_type`
- **EXPECTED:** `Source` → `-src`, `DataProduct` → `-dp`, `Scripts` → `-scripts`, `EngAssets` → `-eng-assets`

**IMPORTANT:** The middle segment of bucket_name (between prefix and suffix) is FREE-FORM. It can be an enterprise name, a subgroup, a team, or any descriptive text. Do NOT validate it. Examples of valid middle segments: `apac`, `agtr`, `corp-fin`, `food-emea`. All are acceptable.

---

## RULE S3-USE-001
- **SEVERITY:** ERROR
- **CHECK:** `usage_type` must be one of: `Source`, `DataProduct`, `Scripts`, `EngAssets`
- **EXPECTED:** Exact match (case-sensitive after normalization)

## RULE S3-USE-002
- **SEVERITY:** ERROR
- **CHECK:** `Source` usage_type is only allowed in Lakehouse accounts
- **EXPECTED:** If `usage_type` is `Source`, then `aws_account_id` must be `438465132548` or `578647603827`

## RULE S3-USE-003
- **SEVERITY:** ERROR
- **CHECK:** `DataProduct` usage_type is only allowed in Compute accounts
- **EXPECTED:** If `usage_type` is `DataProduct`, then `aws_account_id` must be one of the 8 compute accounts

## RULE S3-USE-004
- **SEVERITY:** WARNING
- **CHECK:** If `usage_type` is `Scripts`, `versioning_enabled` should be `true`
- **EXPECTED:** `versioning_enabled: true` present. If missing or false → warning only.

---

## RULE S3-OWN-001
- **SEVERITY:** ERROR
- **CHECK:** `enterprise_or_func_name` must be one of: `AGTR`, `CORP`, `FOOD`, `SPEC`
- **EXPECTED:** Exact match

## RULE S3-OWN-002
- **SEVERITY:** ERROR
- **CHECK:** For Compute accounts, `enterprise_or_func_name` must match the account's assigned enterprise
- **EXPECTED:** Look up enterprise from Account Table. Example: account `367241115350` → AGTR. If YAML says `FOOD` → violation. Lakehouse accounts are "Common" — any enterprise is allowed.

## RULE S3-OWN-003
- **SEVERITY:** WARNING
- **CHECK:** `enterprise_or_func_subgrp_name` should be a short uppercase string or empty `""`
- **EXPECTED:** Uppercase letters only, or empty. Lowercase → warning.

---

## VALID EXAMPLES (for reference only — do NOT derive rules from examples)

### Lakehouse Source (PASSES all rules)
```yaml
intake_id: M0000452
bucket_name: prd-lh1-agtr-src
bucket_description: Stores MIF to lakehouse Ingestion pattern SAP TCC objects
aws_account_id: '578647603827'
aws_region: us-east-1
usage_type: Source
enterprise_or_func_name: AGTR
enterprise_or_func_subgrp_name: APAC
```

### Compute DataProduct (PASSES all rules)
```yaml
intake_id: M0000449
bucket_name: prd-cmp4-corp-fin-dp
bucket_description: Stores data product for Corporate Finance
aws_account_id: '632247962242'
aws_region: us-east-1
usage_type: DataProduct
enterprise_or_func_name: CORP
enterprise_or_func_subgrp_name: FIN
```

### Compute Scripts with versioning (PASSES all rules)
```yaml
intake_id: M0000449
bucket_name: prd-cmp4-corp-fin-scripts
bucket_description: For storing PySpark scripts for CORP FIN subgroup
aws_account_id: '632247962242'
aws_region: us-east-1
usage_type: Scripts
enterprise_or_func_name: CORP
enterprise_or_func_subgrp_name: FIN
versioning_enabled: true
```
