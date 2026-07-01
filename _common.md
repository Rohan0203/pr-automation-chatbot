# Common Reference — Minerva Lakehouse YAML Generation

> **Purpose.** Shared vocabulary, abbreviations, account map, and global allowed values
> used by every object-specific prompt in this folder. RAG retrievers should embed
> this file alongside the per-object prompts so the model always has the canonical
> lookup tables in context.
>
> **Source of truth.** Cargill Minerva *Multi-Account Naming Conventions* SharePoint page
> and `miw-object-provisioning/aws_lakehouse/README.md`. Examples are mined from
> `miw-object-provisioning/aws_lakehouse/lakehouse-001/`. Validation rules mirror
> `miw-admin-services/aws_lakehouse/validationFramework/src/validation_framework/validators/`.

---

## 1. Notation used in naming patterns

| Symbol | Meaning |
|---|---|
| `[ ... ]` | **Mandatory** segment |
| `< ... >` | **Optional** segment |
| `_` | Segment separator for Glue DBs, IAM roles, SMUS projects, security groups, federations |
| `-` | Segment separator for S3 bucket names (S3 disallows underscores) |
| `/` | Segment separator for S3 prefixes and AWS Secrets paths |

---

## 2. AWS account abbreviations (`AWS_ACCT_ABBR`)

| AWS account alias | Approved abbreviation | Account ID |
|---|---|---|
| minerva-snd-lakehouse-001 | `snd-lh1` | *(sandbox — confirm ID)* |
| minerva-snd-compute-001   | `snd-cmp1` | *(sandbox — confirm ID)* |
| minerva-dev-lakehouse-001 | `dev-lh1` | `438465132548` |
| minerva-dev-compute-001   | `dev-cmp1` | `068887784423` *(Ag & Trading)* |
| minerva-dev-compute-002   | `dev-cmp2` | `933999308564` *(Food)* |
| minerva-dev-compute-003   | `dev-cmp3` | `836901248866` *(Specialized Portfolio)* |
| minerva-dev-compute-004   | `dev-cmp4` | `324612370323` *(Corporate)* |
| minerva-prod-lakehouse-001| `prd-lh1` | `578647603827` |
| minerva-prod-compute-001  | `prd-cmp1` | `367241115350` |
| minerva-prod-compute-002  | `prd-cmp2` | `884308299029` |
| minerva-prod-compute-003  | `prd-cmp3` | `011379513867` |
| minerva-prod-compute-004  | `prd-cmp4` | `632247962242` |

**Folder ↔ account rule.** The git repo folder (`lakehouse-001`, `compute-001`…) MUST
match the `aws_account_id` in the YAML. Mismatch is an automatic fast-fail.

---

## 3. Environment variables

### `PLAT_ENV` — *where the resource is hosted*

| Value | Meaning |
|---|---|
| `snd` | Sandbox |
| `dev` | Non-production platform |
| `prd` | Production platform |

### `DATA_ENV` — *lifecycle stage of the data*

| Value | Meaning |
|---|---|
| `dev` | Dev data |
| `qa` | QA data |
| `stg` | Staging data |
| `prd` | Production data |

`PLAT_ENV` and `DATA_ENV` are independent. Both may differ on the same resource (e.g.
a `dev` Glue account holding `qa` data). Both are mandatory wherever the pattern
includes them.

---

## 4. Enterprise / Function and Subgroup abbreviations

`enterprise_or_func_name` is mandatory on **every** object.
`enterprise_or_func_subgrp_name` is **mandatory for CORP** and **forbidden for
AGTR / FOOD / SPEC** on S3 bucket names (it is allowed in the YAML field, just must
not appear inside the bucket name segment for those enterprises).

### Enterprise codes (`OWNING_ENTITY` first segment)

| Code | Enterprise / Function |
|---|---|
| `AGTR` | Ag & Trading |
| `CORP` | Corporate |
| `FOOD` | Food |
| `SPEC` | Specialized Portfolio |

> *(The authoritative source is
> `https://git.cglcloud.com/Minerva/minerva-tags/blob/main/meta/value_refs/abbreviations.yaml`.
> Non-approved abbreviations are automatic PR rejection.)*

### Common subgroups (observed in existing YAMLs)

| Enterprise | Subgroup codes |
|---|---|
| `AGTR` | `APAC`, `LATAM`, `NA`, `TDA`, `WTG` |
| `CORP` | `DTD`, `FIN`, `FSQR`, `GTC`, `CPT`, `EHS`, `DPE` *(findpe)* |
| `FOOD` | `PRGL`, `FSGL`, `PR_NA` |
| `SPEC` | `ANH`, `BIO` |

> Always verify against the abbreviations YAML before generating.

---

## 5. Region

**Only `us-east-1` is permitted.** Any other region is a fast-fail.

---

## 6. Data classification & privacy (governance tags)

| Field | Allowed values |
|---|---|
| `data_classification` | `Confidential - Restricted`, `Confidential - Limited`, `Internal`, `Public` |
| `data_privacy` | `PII`, `PI`, `SPI`, `None` (case-sensitive per existing YAMLs — observed `None`, `NONE`, `PII`, `PI`) |

> Authoritative source: `https://git.cglcloud.com/Minerva/minerva-tags/tree/main/tags`.

---

## 7. Data layers & data constructs (Glue DB)

| Field | Allowed values |
|---|---|
| `data_layer` | `raw`, `raw_serving`, `curated`, `serving`, `internal` |
| `data_construct` | `Source`, `DataProduct` |
| `source_name` | Governance-approved source-system token (e.g. `cdp`, `concur`, `sap_tc1`, `jdee1`, `axapta`). Lowercase, snake_case. |

---

## 8. S3 usage types

S3 `usage_type` field values (must match the trailing segment of the bucket name in
spirit; the bucket-name segment uses lowercase with hyphens):

| `usage_type` (YAML value) | Bucket-name segment |
|---|---|
| `Source` | `src` |
| `Scripts` | `scripts` |
| `EngAssets` | `eng-assets` |
| `DataProduct` | `dp` |
| `Ops` | `ops` |

---

## 9. Lakehouse vs Compute prefix rule

| Object | Prefix rule |
|---|---|
| Glue Database | Always `lh_…` when in Lakehouse account; compute-account DBs use no prefix |
| S3 Bucket (Lakehouse) | Always `…-lh1-…` |
| S3 Bucket (Compute)   | Always `…-cmp1…`/`…-cmp2…`/`…-cmp3…`/`…-cmp4…` |
| Resource Link | DB name + `_rl` suffix |
| Resource Policy | `minerva_cmt_…_rp` (Lakehouse only) |

---

## 10. T-shirt sizes (`compute_size`, T-SIZE)

| Value | Notes |
|---|---|
| `XSML` | default |
| `SML` | |
| `MED` | requires justification above this |
| `LRG` | requires explicit MIW approval |
| `XLRG` | requires explicit MIW approval |

---

## 11. SMUS personas (`PERSONA`)

| Persona | Notes |
|---|---|
| `dataengineer` | Standard data engineer |
| `dataengineerelevated` | Elevated rights (delete, etc.) |
| `techanalyst` | Tech analyst |
| `datareconcilercdp` | CDP reconciliation |

Different personas **must** live in different SMUS projects.

---

## 12. SMUS approved `parent_domain_unit` values

Use **only the Sub-Domain Unit** (never the Parent Domain).

| Parent Domain | Sub-Domain Unit (use this value) |
|---|---|
| Corporate | Digital Technology And Data |
| Corporate | Digital Technology and Data – Data Platforms and Engineering |
| Corporate | Finance |
| Corporate | Global Trade Compliance |
| Corporate | Global Impact – Sustainability |
| Corporate | Procurement and Transportation |
| Corporate | Human Resources |
| Corporate | Risk Management Group |
| Corporate | Environment Health and Safety |
| Corporate | Food Safety Quality and Regulatory |
| Ag and Trading | APAC |
| Ag and Trading | TDA |
| Ag and Trading | Trade and Capital Markets |
| Ag and Trading | World Trading Group |
| Ag and Trading | LATAM |
| Ag and Trading | Metals |
| Ag and Trading | WTG – CDAS |
| Ag and Trading | NA |
| Specialized Portfolio | Animal Nutrition |
| Specialized Portfolio | Bioindustrial |
| Food | Commercial Excellence |
| Food | Protein – NA |
| Food | Protein – Global |

> Legacy YAMLs sometimes use `"Minerva"` as a placeholder; prefer one of the above
> for new objects.

---

## 13. Immutable fields (never change after creation)

| Object | Immutable fields |
|---|---|
| Glue Database | `database_name`, `database_s3_location`, `aws_account_id`, `region` |
| IAM Role | `role_name`, `aws_account_id`, `role_description` |
| Resource Policy | `aws_account_id`, `cross_account_aws_id`, `principal_role_arn` |
| S3 Bucket | `bucket_name`, `aws_account_id`, `aws_region` |
| Data Federation | `aws_account_id` |

---

## 14. Mandatory ownership metadata

Where the template asks for it:

- `data_owner_email` — Cargill email, non-empty.
- `data_owner_github_uname` — must be a real GitHub username inside Cargill GHE.
- `data_leader` — Minerva governance lead (username or PSID).
- `intake_id` — must reference an Intake in **Ready for Design** state belonging to
  the same Enterprise/Function/Subgroup as the object.

---

## 15. Output contract for the LLM

When generating any object YAML, the assistant **must**:

1. Output a single YAML document inside one ```yaml fenced block — nothing else.
2. Preserve field order as shown in the per-object schema.
3. Quote strings only when the source examples quote them (account IDs are quoted,
   most other strings are unquoted).
4. Refuse to generate the file (and explain why) if the user request violates any
   hard rule listed in the per-object prompt.
5. Echo back a short **post-generation checklist** (validation steps the user should
   run before raising the PR) as a markdown list **after** the YAML block.
