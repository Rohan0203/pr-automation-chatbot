# Minerva Lakehouse – PR Guidance for Users

## Purpose

This document provides **practical, developer‑focused guidance** for raising **high‑quality Pull Requests** in the Minerva Lakehouse provisioning repository.

It explains *what to submit*, *how to structure it*, and *why certain guardrails exist*—covering scope, naming, ownership, approvals, object‑specific rules, and automated validations across **Lakehouse and Compute** provisioning.

The goal is to help you:
- Avoid preventable rework
- Reduce review back‑and‑forth
- Get your PR merged faster and more safely

---

## Who Should Use This Guide

This guide is intended for:
- Data Engineers
- Technical Analysts
- Project / Data Product Owners
- Any user submitting metadata templates for **Lakehouse or Compute** provisioning

---

## Core Expectations (Read First)

Every Lakehouse PR is treated as a **governed infrastructure change**.

A good PR is:
- Narrow in scope
- Correctly grouped
- Accurately named
- Backed by valid intake and ownership
- Least‑privileged
- Safe to automate

If any of the above is missing, the PR will likely be delayed or rejected.

---

## 1. PR Scope, Structure, and Hygiene

### Keep PRs Small and Purpose‑Driven

- Always sync your fork before raising a PR
- Keep changes focused to **one logical intent**
- Prefer **≤ 5 files per PR** (recommendation, not a hard stop)
- Avoid bundling unrelated objects
- Split logically distinct changes into separate PRs

Smaller PRs are easier to validate, safer to roll back, and reviewed faster.

---

### Separate SMUS PRs from Other Lakehouse Objects

Do **not** mix:
- `smus_roles`
- `smus_projects`

with:
- `iam`
- `s3`
- `glue_db`
- `resource_policy`

SMUS entities are **manually provisioned** today and require a **separate PR**.

---

### Separate PRs for Data Federation (Sequencing Matters)

Data Federation follows a **strict sequence**:

1. Provision the database in the **source AWS account**
2. Raise a **separate PR** to federate it into the target account (resource link)
3. After federation is merged, raise access PRs (IAM role or SMUS project)

> Steps **2 and 3 may be raised together**, but **step 1 must already exist**

---

### Object Provisioning Templates

Use only approved templates:

- **Development**:  
  https://git.cglcloud.com/Minerva/miw-object-provisioning/tree/dev/templates/aws_lakehouse
- **Production**:  
  https://git.cglcloud.com/Minerva/miw-object-provisioning/tree/main/templates/aws_lakehouse

Do not introduce custom fields or restructure templates.

---

### Renames, Deletions, and Access Changes

#### No renames after creation

Once created, names cannot change:
- S3 buckets
- Glue databases

To change names:
- Request a **new object**, or
- Raise an **explicit MIW drop request** (case‑by‑case decision)

#### Delete / Destroy is not a standard path

Deletion workflows are still under design (DR, backup considerations).

For exceptions, raise a request via **Minerva Central Issues**.  
MIW will act only after required approvals.

#### Access changes are supported

Grant/revoke access via:
- IAM
- Lake Formation  

This is preferred over recreating objects.

#### Never delete files in PRs

PRs must only **add or modify** files—never delete.

---

## 2. Immutable Attributes (Hard Stop Rules)

Changing immutable fields triggers **destroy/recreate**, which is **not allowed** in standard PR flows.

| Object Type | Immutable Fields |
|------------|------------------|
| Glue Database | database_name, database_s3_location, aws_account_id, region |
| IAM Role | role_name, aws_account_id |
| Resource Policy | aws_account_id, cross_account_aws_id |
| S3 Bucket | bucket_name, aws_account_id, aws_region |
| Data Federation | aws_account_id |

---

## 3. Naming Conventions & Abbreviations

### Naming Standards (Mandatory)

Use MIW‑approved Lakehouse naming:
- https://cargillonline.sharepoint.com/sites/minervacentral/SitePages/Multi-Account-Naming-Conventions.aspx

### Governance‑Approved Abbreviations (Mandatory)

Use only approved abbreviations for:
- `enterprise_or_func_name`
- `enterprise_or_func_subgrp_name`

Source of truth:
- https://git.cglcloud.com/Minerva/minerva-tags/blob/main/meta/value_refs/abbreviations.yaml

Non‑approved abbreviations are **automatic PR rejection**.

---

## 4. Account & Repo Folder Alignment

Templates **must** be placed under the correct repo folder and reference the correct AWS account.

### Dev account mapping

| Git repo folder | AWS account alias | AWS account ID | Enterprise/Function |
|---|---|---:|---|
| lakehouse-001 | minerva-dev-lakehouse-001 | 438465132548 | Not applicable |
| compute-001 | minerva-dev-compute-001 | 068887784423 | Ag & Trading |
| compute-002 | minerva-dev-compute-002 | 933999308564 | Food |
| compute-003 | minerva-dev-compute-003 | 836901248866 | Specialized Portfolio |
| compute-004 | minerva-dev-compute-004 | 324612370323 | Corporate |

### Prod account mapping

| Git repo folder | AWS account alias | AWS account ID | Enterprise/Function |
|---|---|---:|---|
| lakehouse-001 | minerva-prod-lakehouse-001 | 578647603827 | Not applicable |
| compute-001 | minerva-prod-compute-001 | 367241115350 | Ag & Trading |
| compute-002 | minerva-prod-compute-002 | 884308299029 | Food |
| compute-003 | minerva-prod-compute-003 | 011379513867 | Specialized Portfolio |
| compute-004 | minerva-prod-compute-004 | 632247962242 | Corporate |

**Mismatch between folder, account ID, and alias is a fast‑fail check.**

---

## 5. Region, Ownership, and Intake Readiness

### Supported Region

- **us-east-1 only**
- Any other region fails review unless explicitly approved

---

### Mandatory Ownership Metadata

Every DB template must include:
- `data_owner_email`
- `data_owner_github_uname`
- `data_leader`

The GitHub username is used for **explicit approval workflows** and must belong to **Cargill GitHub Enterprise**.

---

### Intake Validation (Before You Submit)

Always verify:
- Intake ID exists
- Intake status is correct
- Data Owner, Data Leader, Role Owner are aligned

If intake is not valid, the PR will stall regardless of correctness.

---


## 6. Object‑Specific Guidance (templates & validations)

### 6.1 Glue Databases (Lakehouse entities)
- `database_s3_location` is **mandatory**.  
- `aws_account_id` for Dev Lakehouse **must be `438465132548`**; ensure correct for your environment.  
- `region` must be **`us-east-1`**.  
- `data_construct` ∈ **`DataProduct` | `Source`**.  
- `data_env` ∈ **`snd` | `dev` | `stg` | `prd`**.  
- `data_layer` ∈ **`raw` | `cur` | `srv` | `int`**.  
- `source_name` must be **Governance‑approved** (`tags` repo):  
  [Governance Approved Tags](https://git.cglcloud.com/Minerva/minerva-tags/tree/main/tags)
- `data_owner_email` and `data_owner_github_uname` **must not be empty** and must match Intake/Data Contract.  
- Every `github_uname` in the template **must be a valid GitHub profile**.  
- `data_classification` and `data_privacy` **must** use values from the **tags repo**.  
- `enterprise_or_func_name` and `enterprise_or_func_subgrp_name` **must** use valid abbreviations from the **tags repo**.

---

### 6.2 IAM Roles

#### 6.2.1 Ingestion Engineer
- Request **no** access beyond the **TableFlow‑created DB** (e.g., `lkc-vzdk2j`).  
- Grant access **only** to the **equivalent enterprise/function source bucket** (specific prefixes) — **no bucket‑wide (`s3://bucket/*`)** grants.  
- Role exists **only** in **lakehouse‑001** (Dev/Prod), **not** in Compute.  
- **Grain:** Enterprise/Function (CORP may follow its bucket grain).  
- `usage_type` = **`IngestionEngineer`**.  
- `principal_role_arn` must be a **valid cross‑account role ARN** (source). Please raise this request **only when your role in source MIF account already exists**, otherwise the provisioning on Lakehouse will fail.
- **No read access** to any database.  
- **Support channel** if unsure about paths:  
  [Teams MIW Support Channel](https://teams.microsoft.com/l/channel/19%3A5a7600cbb5364d879827e49df32d45c5%40thread.tacv2/MIW%20-%20Object%20Provisioning%20Support?groupId=d6e0463c-4725-481f-94ac-5836bfad0e30&tenantId=57368c21-b8cf-42cf-bd0b-43ecd4bc62ae)

#### 6.2.2 Integrated Ingestion Engineer
- Role exists **only** in **lakehouse‑001** (Dev/Prod).  
- Glue DB access: **only `raw` DBs (R/W)**; **no** access to curated, serving, or internal DBs.  
- Access **only** to the **equivalent enterprise/function source bucket**.  
- **Grain:** Subgroup.  
- `usage_type` = **`IntegratedIngestionEngineer`**.  
- `principal_role_arn` must be **valid**. Please raise this request **only when your role in source MIF account already exists**, otherwise the provisioning on Lakehouse will fail. 
- **No read access** to any database.

#### 6.2.3 Proc Data Engineer
- **Grain (Lakehouse):** Subgroup (not Enterprise/Function).  
- `compute_size` ∈ **`XSML` | `SML` | `MED` | `LRG` | `XLRG`**; anything **above `MED`** needs justification.  
- **R/W** access **only** to **non‑CDP raw DBs** owned by the same enterprise/function/subgroup; **no R/W** on CDP DBs.  
- Access **only** to **`merged`** paths in source buckets of the same enterprise/function/subgroup (for historical + current stitching).  
- Access subgroup **eng‑assets** and **scripts** buckets only, e.g.:  
  - `s3://minerva-dev-eng-assets-corp-fin/dev/fin/glue/`  
  - `s3://minerva-dev-scripts-corp-fin/dev/fin/glue/`  
- Trigger **only** Glue crawlers belonging to the **same** Ent/Func/Subgroup.  
- Glue jobs must be limited by **name prefix** (`job_control_configs`).  
- **Athena workgroup naming:** `[ENT/FUNC]_[SUBGRP]_[DATA_ENV]_[WG_PURPOSE]_[T-SIZE]` (e.g., `agtr_apac_dev_eng_xsml`).  
- **Dynamic PR approval** will ensure DB owner approval for DB access.  
- `usage_type` = **`DataEngineer`**.  
- `max_session_duration` **> 2h** must be **justified**.  
- `execution_asset_prefixes` must be limited to **same** ent/function/subgroup paths.  
- Flags `enable_glue_interactive_session`, `enable_athena_access`, `enable_glue_jobs`, `snowflake_iceberg_support` are **boolean** only.  
- `principal_role_arn` must be a **valid ARN** generated from **Snowflake catalog integration**.

---

### 6.3 S3 Buckets

#### 6.3.1 Ent/Func Source System Buckets
- **Grain:** Enterprise/Function (except CORP specifics).  
- **Region:** `us-east-1` only (**non‑us‑east‑1** fails review).  
- `usage_type` = **`Source`**.  
- `enterprise_or_func_name` **mandatory**; for **CORP**, `enterprise_or_func_subgrp_name` also **mandatory**.  
- `public_access_blocked` must **never** be `false`.  
- `encryption_key_arn` is **not supported** (raise explicit request if needed).

#### 6.3.2 Source System Buckets (Deprecated)
- Requests for **source‑only** buckets should **fail** review (deprecated pattern).  
- If exception is discussed with MIW:  
  - `source_system` must be **populated**.  
  - **Region:** `us-east-1` (others → **soft failure**).  
  - `usage_type` = **`Source`**.  
  - `enterprise_or_func_name` and `enterprise_or_func_subgrp_name` should be **empty**.  
  - `public_access_blocked` must **never** be `false`.  
  - `encryption_key_arn` **not supported**.

#### 6.3.3 Ent/Func Scripts Buckets
- **Grain:** Enterprise/Function (except CORP specifics).  
- **Region:** `us-east-1`.  
- `usage_type` = **`Scripts`**.  
- `enterprise_or_func_name` **mandatory**; for **CORP**, `enterprise_or_func_subgrp_name` also **mandatory**.  
- `public_access_blocked` must **never** be `false`.  
- `encryption_key_arn` **not supported**.

#### 6.3.4 Ent/Func Engineering Assets Buckets
- **Grain:** Enterprise/Function (except CORP specifics).  
- **Region:** `us-east-1` (others → **soft failure**).  
- `usage_type` = **`EngAssets`**.  
- `enterprise_or_func_name` **mandatory**; for **CORP**, `enterprise_or_func_subgrp_name` also **mandatory**.  
- `public_access_blocked` must **never** be `false`.  
- `encryption_key_arn` **not supported**.

#### 6.3.5 Ent/Func Specific Data Product Buckets
- **Grain:** Enterprise/Function only.  
- **Region:** `us-east-1` (others → **soft failure**).  
- `usage_type` = **`DataProduct`**.  
- `enterprise_or_func_name` **mandatory**; for **CORP**, `enterprise_or_func_subgrp_name` also **mandatory**.  
- `public_access_blocked` must **never** be `false`.  
- Any value of `encryption_key_arn` should **fail** the pipeline (MIW will review).

---

### 6.4 Resource Policy
- **File name pattern:** `[MINERVA]_[ENT/FUNC]_[SRC_AWS_ACCNT]_[ENT/FUNC]_[SUBGRP]_[DATA_ENV]_rp`  
  - Example: `minerva_dev_cmt_agtr_apac_dev_rp`  
- `Intake_ID` must be **valid** and must belong to the relevant **Ent/Func** and **Subgroup**.  
- `aws_account_id` and `cross_account_aws_id` must be **valid AWS Account IDs**.  
- `principal_role_arn` must be **valid** for CMT‑based ingestion.  Please raise this request **only when your role in source MIF account already exists**, otherwise the provisioning on Lakehouse will fail.
- Grant access **only** to **CDP‑specific** DBs and S3 paths.  
- Restrict to DBs and S3 paths **within the same** Ent/Func/Subgroup—**nothing beyond**.

---

### 6.5 Glue Crawler
- **One crawler → one database:** The template must specify a **single** DB aligned to the **same** Ent/Func/Subgroup.  
- **Grain:**  
  - **Data Product** for **curated/serving** DBs.  
  - **Source System** (e.g., Concur, Archer, SAP_TC1) for **raw**.  
- **Naming:** Must include `data_env` and `data_layer`; for **serving**, also include `usage_type`.  
- **S3 paths:**  
  - **Raw** for Source crawlers.  
  - **Curated/Serving** for Data Product crawlers.  
  - Bucket must match the **same** Ent/Func/Subgroup.  
- **Storage type:** `iceberg`—otherwise call out soft warning/failure in pipeline summary and reach MIW.  
- **Governance:** `data_classification` and (if Source) `source_name` must match **pre‑approved** tags.  
- **Account & region:** `aws_account_id` must be a **Lakehouse ecosystem** account; `region` = **`us-east-1`**.  
- Ensure the crawler writes **only** within its **own** subgroup’s DB.  
- For **serving** layer crawlers, `usage_type` is **mandatory** and part of the crawler name.

---

### 6.6 Data Federation
- Can be at **Source System** or **Data Product** grain.  
- **Dynamic PR approval** applies (DBs shared across accounts require owner approvals).  
- `cross_account_aws_ids` must be from the **approved** Lakehouse list; otherwise **soft failure**.  
- `source_name` must be **governance‑valid**.  
- `data_env` must appear in DB names—**environments must match**.  
- All DBs listed must belong to the **same** Ent/Func/Subgroup as the template.

---

### 6.7 SMUS Roles
- `aad_group_name` must be a **valid SailPoint entitlement**.  
- **Role owner** details must match **Intake**.  
- **Data Leader** and **Governance Lead** must match **Intake**.  
- Enterprise/Function/Subgroup values must use **approved abbreviations**.  
- If the role is **Data Product level**, the Intake must belong to the **same Data Product**.

---

### 6.8 SMUS Project
- `parent_domain_unit` must be from the **maintained list** in automation backend.  
- `project_owner` must match **Intake**.  
- **Project membership** must align with `smus_project_name` (avoid analyst entitlement in an engineer’s project).  
- `compute_size` must be from valid **T‑shirt sizes**.  
- The project‑specific role should **tie to a Glue Usage Profile** (to govern compute).  
- The associated **Athena workgroup** should be controlled by **T‑shirt size**.  
- `usage_type` must be **valid** (tags repo).  
- Populating `data_product_team` triggers a **soft failure** → MIW manual scrutiny (is this truly a Data Product Team or subgroup‑level?).  
- If `cross_account_configs` = enabled: **raw** should be accessed via **Data Federation**, map the **resource link** (not the original DB).  
- **Dynamic PR approval** applies (cross‑account sharing).  
- **Database permissions:** **read‑only**.  



## 7. How Reviewers Evaluate PRs

### Review Focus Areas

- Correct intake and state
- Correct account & folder
- Platform separation
- Object grouping & sequencing
- Ownership metadata
- Approval evidence
- Governance‑approved abbreviations
- Layer and access boundaries

### Common Rejection Reasons

- Mixed SMUS and non‑SMUS objects
- Mixed Lakehouse and Snowflake changes
- Wrong account or region
- Missing ownership fields
- Immutable field changes
- Raw write access violations
- Missing owner approval for cross‑subgroup access

---

## 8. Operating Best Practices

- Keep PRs minimal
- Follow least‑privilege
- Respect account and subgroup boundaries
- Validate before submission
- Never delete files
- Never rename provisioned objects
- Follow federation sequencing carefully

---

## 9. Final Takeaway

A strong Lakehouse PR is:
- Correctly scoped
- Properly grouped
- Naming‑compliant
- Intake‑backed
- Ownership‑approved
- Region‑correct
- Automation‑safe

If any of these are missing, delays are expected.

---

## 10. Reference Links

References:
- [Lakehouse_Dev_YAML_Templates](https://git.cglcloud.com/Minerva/miw-object-provisioning/tree/dev/templates/aws_lakehouse)
- [Lakehouse_Prod_YAML_Templates](https://git.cglcloud.com/Minerva/miw-object-provisioning/tree/main/templates/aws_lakehouse)
- [Enterprise/Function/Subgroup Approved Abbreviations](https://git.cglcloud.com/Minerva/minerva-tags/blob/main/meta/value_refs/abbreviations.yaml)
- [Governance_Approved_Delegates](https://git.cglcloud.com/Minerva/minerva-governance/blob/dev/delegate%20access%20repo/source%20system%20delegates.md)
- [Lakehouse_Sharepoint_Documentation](https://cargillonline.sharepoint.com/sites/minervacentral/SitePages/MIW.aspx?csf=1&web=1&e=2eYujQ&OR=Teams-HL&CT=1748258064817&CID=9ee7a1a1-303c-0000-b0d1-cb9f262be36f&cidOR=SPO#2.-aws-lakehouse-platform)
- [Lakehouse_Approved_Naming_Conventions](https://cargillonline.sharepoint.com/sites/minervacentral/SitePages/Multi-Account-Naming-Conventions.aspx)
- [PR_Submission_Workflow_And_Review_Guidance](https://cargillonline.sharepoint.com/sites/minervacentral/SitePages/MIW.aspx?csf=1&web=1&e=2eYujQ&OR=Teams-HL&CT=1748258064817&CID=9ee7a1a1-303c-0000-b0d1-cb9f262be36f&cidOR=SPO#pull-request-workflow-submission%2C-review%2C-and-responsiveness)
- [Governance_Approved_Tags](https://git.cglcloud.com/Minerva/minerva-tags/tree/main/tags)
