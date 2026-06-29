# Minerva MIW Object Provisioning Guidelines – Snowflake

## Purpose

This document provides **Snowflake‑specific guidance** for object provisioning through the **Minerva MIW** framework. It is intended to help requestors and reviewers reliably submit, review, and approve Snowflake provisioning PRs by clearly documenting:

- Governance and naming standards
- Automated validations enforced by MIW
- PR scoping and grouping expectations
- Object boundaries and least‑privilege rules
- Fields that can trigger **destroy‑and‑recreate** behavior in Snowflake

The goal is to reduce failed provisions, rework, and review delays while ensuring platform safety and governance compliance.

---

## Who This Guide Is For

- Data Engineers
- Analytics Engineers
- Platform Engineers
- Data Product Teams
- Reviewers validating Snowflake provisioning PRs

---

## Core Principles (Read First)

Every Snowflake PR is treated as a **governed change to shared analytics infrastructure**.

A high‑quality Snowflake PR is:
- Narrow in scope
- Correctly grouped
- Precisely named
- Aligned with governance and intake readiness
- Least‑privileged
- Safe to automate and easy to reason about

If any of these are missing, the PR is likely to be delayed or rejected.

---

## 1. Standards and Conventions

All Snowflake provisioning requests must follow MIW‑defined standards.

### Mandatory Requirements
- All object names must follow approved Snowflake naming standards
- Use Snowflake conventions as the single source of truth
- All requests must use the **standard Snowflake metadata JSON templates**
- Do not add custom fields or modify template structure

Any deviation from the standard template breaks automation.

### Reference Templates
- Snowflake Production Templates

---

## 2. MIW Rule Book Compliance

MIW enforces a layered rule‑book‑driven validation framework for Snowflake provisioning.

### Validation Layers
- Naming convention validation
- Technical validation
- PR‑specific checks
- Generic object checks
- Object‑type‑specific checks

These validations are designed to catch issues early, before unsafe or non‑compliant changes reach Snowflake.

---

## 3. Pull Request–Specific Checks

### Scope and Grouping
- Each PR must be limited to **a single Product Group**
- All files in a PR must belong to the same Product Group
- Do not mix unrelated Snowflake objects in a single PR

### Recommended PR Size
- Keep PRs to **5 or fewer object changes** where possible
- This typically means modifying or adding no more than 5 files

Smaller PRs reduce review time, blast radius, and rollback risk.

### Deletions
- File deletions are **not allowed** for objects already merged into `dev`, `stg`, or `prod`
- A separate deletion workflow will be introduced in a future phase

### Immutable‑Change Caution

When editing existing files, avoid modifying attributes that trigger **destroy‑and‑recreate** behavior in Snowflake.

---

## 4. Generic Validation Checks

The following checks apply to all Snowflake objects:

- PUBLIC roles must **never** be granted access to:
  - Databases
  - Schemas
  - Warehouses
- Validate whether the object already exists or is a new request
- All roles referenced in `access_roles` must already be **SCIM‑provisioned**
- Provisioning fails if referenced roles do not exist

---

## 5. Warehouse‑Specific Rules

### Supported Warehouse Sizes
Only the following sizes are supported:
- `XSMALL`
- `SMALL`
- `MEDIUM`
- `LARGE`
- `XLARGE`

### Credit and Usage Controls
- Default credit limit: **500 credits / month**
- Requests above this limit require justification and may require MIW approval
- Auto‑suspend must be **≤ 60 seconds** (higher requires justification)

### Supported Types and Policies
- Only `STANDARD` warehouse type is allowed
- Maximum cluster count: **10**
- Only `ECONOMY` scaling policy is supported

### Query Timeout
- Maximum query timeout: **1800 seconds**

### Alerts
- Alert subscriber list is mandatory
- All users must exist in Snowflake
- Email IDs must be specified in **ALL CAPITALS**

---

## 6. Schema‑Specific Rules

### Data Retention
- Retention > 1 day requires approval from the Data Product Manager

### Data Classification

Only the following classifications are allowed:
- https://git.cglcloud.com/Minerva/minerva-tags/blob/main/meta/value_refs/data_first_classification_levels.yaml

---

## 7. Storage Integration Rules

- Only the **Data Engineer** persona may request storage integrations
- AWS Role ARN must be valid and compliant with AWS standards

---

## 8. Naming Convention Validation

Snowflake naming conventions are strictly enforced to ensure:
- Governance compliance
- Cost control
- Long‑term scalability

### Common Convention Checks
- Separator checks (correct underscore count)
- Prefix checks (object‑specific prefixes)
- Suffix checks (object‑type suffix required for all except process users)

Naming mismatches are fast‑fail validations.

---

## 9. Attributes That Trigger Destroy and Recreate

The following attributes are **high‑risk** and must not be changed after creation:

| Snowflake Object | Attributes Likely to Trigger Destroy & Recreate |
|-----------------|-------------------------------------------------|
| Warehouse | `WAREHOUSE_NAME`, `WAREHOUSE_SIZE`, `MIN_CLUSTER_COUNT`, `MAX_CLUSTER_COUNT`, `WAREHOUSE_TYPE` |
| Database | `DATABASE_NAME` |
| Schema | `SCHEMA_NAME` |
| Storage Integration | `STORAGE_INTEGRATION_NAME`, `STORAGE_PROVIDER`, `STORAGE_AWS_ROLE_ARN` |
| Persona | `PERSONA_NAME` / `ROLE_NAME` |
| OAuth | `SUB-UUID` |

Treat these fields as immutable from a change‑management perspective.

---

## 10. PR Submission Quality Guidance

Submitting a PR in MIW is not just a request—it directly drives **automated, governance‑controlled infrastructure changes**.

A well‑prepared PR:
- Moves through review faster
- Reduces back‑and‑forth
- Minimizes rejection risk
- Lowers production impact
- Makes intent clear and auditable
- Enables safer rollback and troubleshooting

**One‑line rule:** A good MIW PR is governance‑ready, narrowly scoped, correctly grouped, precisely named, least‑privileged, and easy to reason about.

---

## 11. Governance Readiness (Before You Write JSON)

Confirm the following before raising a PR:
- Intake ID exists and is valid
- Intake is approved and in the correct state (e.g., **Ready for Design**)
- Data Owner, Data Leader, and ownership details are finalized
- Request is officially sanctioned

If governance is not ready, the PR will stall regardless of technical correctness.

---

## 12. Prerequisites Before Raising a PR

### Templates
- Use standard Snowflake JSON templates only
- No custom fields or deviations
- Place templates under the correct repo folder

### Roles and Entitlements
- Ensure all entitlements are created and visible
- Ensure all referenced roles are SCIM‑provisioned

---

## 13. Keep PRs Small and Purpose‑Driven

- Limit PRs to closely related changes
- Avoid bundling unrelated requests
- Keep blast radius minimal
- Follow one‑intent‑per‑PR discipline

---

## 14. Group Objects Correctly

- Do not mix automated and semi‑automated/manual objects
- Keep Snowflake and Lakehouse changes in separate PRs
- Respect object sequencing and dependencies

Incorrect grouping is a common rejection reason.

---

## 15. Naming and Abbreviation Discipline

- Use only governance‑approved abbreviations
- Strictly follow MIW naming standards for:
  - Snowflake databases
  - Schemas
  - Warehouses
  - Roles and personas
- Ensure file names, object names, and metadata match exactly

Naming mismatches are fast‑fail checks.

---

## 16. Least‑Privilege Access Enforcement

- Request only the minimum access required
- Respect read/write boundaries
- Attach explicit data owner approval for cross‑subgroup access

Least privilege is non‑negotiable.

---

## Final Takeaway

A strong Snowflake provisioning PR is:
- Governed and intake‑ready
- Small and logically scoped
- Correctly grouped
- Naming‑compliant
- Least‑privileged
- Safe to automate

This is the fastest path to a clean review and successful provisioning.

---

## Reference Links

References:
- [Snowflake_Dev_JSON_Templates](https://git.cglcloud.com/Minerva/miw-object-provisioning/tree/dev/templates/snowflake/naming_v2.0)
- [Snowflake_Prod_JSON_Templates](https://git.cglcloud.com/Minerva/miw-object-provisioning/tree/main/templates/snowflake/naming_v2.0)
- [Enterprise/Function/Subgroup Approved Abbreviations](https://git.cglcloud.com/Minerva/minerva-tags/blob/main/meta/value_refs/abbreviations.yaml)
- [Governance_Approved_Delegates](https://git.cglcloud.com/Minerva/minerva-governance/blob/dev/delegate%20access%20repo/source%20system%20delegates.md)
- [Snowflake_Sharepoint_Documentation](https://cargillonline.sharepoint.com/sites/minervacentral/SitePages/MIW.aspx?csf=1&web=1&e=2eYujQ&OR=Teams-HL&CT=1748258064817&CID=9ee7a1a1-303c-0000-b0d1-cb9f262be36f&cidOR=SPO#1.-snowflake-platform)
- [PR_Submission_Workflow_And_Review_Guidance](https://cargillonline.sharepoint.com/sites/minervacentral/SitePages/MIW.aspx?csf=1&web=1&e=2eYujQ&OR=Teams-HL&CT=1748258064817&CID=9ee7a1a1-303c-0000-b0d1-cb9f262be36f&cidOR=SPO#pull-request-workflow-submission%2C-review%2C-and-responsiveness)
- [Governance_Approved_Tags](https://git.cglcloud.com/Minerva/minerva-tags/tree/main/tags)
