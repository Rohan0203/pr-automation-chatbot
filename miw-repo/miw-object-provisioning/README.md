# Minerva MIW Object Provisioning Guidelines

## Purpose

Welcome to the **Automated Object Provisioning Framework** managed by the **MIW Team** for the **Cargill Minerva Program**.

This repository enables **governance-controlled, auditable provisioning** of infrastructure and data objects across **Snowflake** and **AWS Lakehouse** using Pull Requests (PRs).

This README defines the **repository-level contract** for both requestors and reviewers. It explains the operating model, enforced validations, and submission hygiene required before raising a PR. The intent is to reduce review cycles, avoid preventable failures, and keep platform changes predictable, scoped, and safe.

For the overall process of raising a PR, refer to the official MIW guidance:
- [PR_Submission_Guide](https://cargillonline.sharepoint.com/sites/minervacentral/SitePages/PR-Submission-Guide.aspx)
  
---

## Repository-Level Principles

Every PR represents a governed change to shared platform infrastructure. A valid request must be:

- Correctly scoped
- Correctly grouped
- Correctly named
- Linked to a valid Intake
- Backed by ownership and approval evidence
- Created using approved templates
- Targeted to the correct platform and account

> **In one line:** A good PR is governance-ready, narrowly scoped, correctly grouped, precisely named, least-privileged, and easy to reason about.

---

## What This Repository Enforces

This repository manages provisioning requests for:

- Snowflake objects
- AWS Lakehouse objects
- Access and entitlement-related resources
- Governance-aligned metadata templates

Automation and review enforce checks for:

- Naming conventions and abbreviations
- Account IDs and repository folder placement
- Platform separation (Snowflake vs Lakehouse)
- Ownership metadata and approval readiness
- Object scope, grouping, and sequencing
- Read/write layer boundaries
- Immutable fields
- Platform-specific template rules

---

## Template Standards

All provisioning must use approved templates:

- **Snowflake**: Standard metadata **JSON** templates
- **Lakehouse**: Standard **YAML** templates - 

Rules:
- No custom fields or structure changes
- Templates define *intent*, not implementation
- Files must be stored in the correct repo folder
- Account ID and alias must match the target environment

Any template deviation breaks automation.

---

## PR Separation Rules

### Mandatory Separations

- Snowflake and Lakehouse requests must be raised as separate PRs
- SMUS PRs must be raised separately from other Lakehouse objects
- IAM access to a federated database can be requested **only after** federation exists in the target account

### Recommended Boundaries

- One logical intent per PR
- Avoid bundling unrelated objects
- Keep the blast radius small

---

## PR Hygiene Expectations

Before raising a PR:

- Ensure your fork is synced with the base branch
- Include only commits relevant to the change
- Target the correct base branch
- Complete all fields in the PR Intake Template
- Add required labels (wave, team, status, Enterprise/Function/Subgroup)
- Ensure the Intake ID is valid and in **Ready for Design** state

If a PR is marked **Pending User Action**, address all comments and update the status back to Review in Progress.

---

## Governance Readiness

A PR should not be raised until governance prerequisites are complete.

Verify before submission:
- Intake ID is valid and approved
- Intake status is correct
- Data owner, data leader, and role owner are finalized
- Ownership aligns with governance records
- Required approvals are already obtained

If governance is not ready, the PR will stall regardless of technical correctness.

---

## Ownership & Approvals

Ownership drives access decisions and approval workflows.

General expectations:
- Data owner approval must be obtained up front
- Cross-account access and federated databases require approval unless within the same subgroup
- Approval evidence must be included in the PR when applicable
- Refer the Governance repository to identify the owner or delegate for each source system and Enteprise/Function/Subgroup - [Ownership_Details](https://git.cglcloud.com/Minerva/minerva-governance/tree/dev/delegate%20access%20repo)
- Exceptions have been called out at - [Exception_Details](https://git.cglcloud.com/Minerva/minerva-governance/tree/dev/exceptions)

Mandatory ownership metadata (where required by template):
- `data_owner_email`
- `data_owner_github_uname`
- `data_leader`

The GitHub username must be valid and match governance records.

---

## Naming & Abbreviation Standards

- All object names must follow MIW naming conventions
- Only governance-approved abbreviations may be used
- File names must exactly match object names
- Lakehouse Naming: [Lakehouse naming standards](https://cargillonline.sharepoint.com/sites/minervacentral/SitePages/Multi-Account-Naming-Conventions.aspx)
- Snowflake Naming: [Snowflake naming standards](https://cargillonline.sharepoint.com/sites/minervacentral/SitePages/MIW.aspx?csf=1&web=1&e=2eYujQ&OR=Teams-HL&CT=1748258064817&CID=9ee7a1a1-303c-0000-b0d1-cb9f262be36f&cidOR=SPO#1.-snowflake-platform)
- Governance-approved abbreviations from the Minerva tags repository - [Minerva_Tags](https://git.cglcloud.com/Minerva/minerva-tags/tree/main/tags)

Naming violations are fast-fail conditions during review.

---

## Account & Folder Alignment

Templates must be placed in the correct repository folder and reference the correct AWS account ID.

Mismatch between folder, account alias, and account ID will fail validation.

---

## File Change Rules

- Add or modify files only
- Do not delete files in PRs
- Object deletion or destroy is not supported via standard PR flow
- Renaming provisioned objects is not supported

Deletion or rename requires an explicit MIW review via Minerva Central.

---

## Immutable Fields

The following fields must never be changed after object creation:

| Object type | Immutable fields |
|---|---|
| Glue Database | database_name, database_s3_location, aws_account_id, region |
| IAM Role | role_name, aws_account_id, role_description |
| Resource Policy | aws_account_id, cross_account_aws_id, principal_role_arn |
| S3 Bucket | bucket_name, aws_account_id, aws_region |
| Data Federation | aws_account_id |

Changing immutable fields is a hard stop.

---

## Region Policy

For Lakehouse provisioning, only **us-east-1** is supported. Requests targeting other regions require explicit MIW approval.

---

## Object Categories Covered

### AWS Lakehouse
- Glue Databases
- IAM Roles
- S3 Buckets
- Resource Policies
- Glue Crawlers
- Glue Connections
- Data Federation and Resource Links
- SMUS Roles and Projects
- Secrets Manager
- Security Groups

### Snowflake
- Databases and Schemas
- Roles and Personas
- Warehouses
- Storage and Catalog Integrations
- Data Shares
- OAuth / Process ID integrations

---

## Large PR Guidance

Large PRs (roughly more than 10 files or objects) significantly increase review risk and SLA impact.

Why large PRs are problematic:
- Single-reviewer bottlenecks
- Heavy manual validation
- Harder troubleshooting
- Risky rollback
- Larger blast radius

Best practice:
- Split work into logically grouped PRs
- Raise multiple focused PRs
- Call out time-critical PRs explicitly

---

## Quick Self-Check Before Submit

- Correct platform?
- Correct account and folder?
- Valid intake and governance readiness?
- Naming and abbreviations valid?
- Immutable fields untouched?
- Scope minimal and focused?

If yes to all, the PR is ready for review.

---

## Think Like an Auditor

Ask yourself:
- Is this governance-aligned?
- Is it least-privileged?
- Is it predictable and reversible?
- Can an external reviewer understand the intent easily?
- For more details refer: [Wear_Hat_of_an_Auditor](https://cargillonline.sharepoint.com/sites/minervacentral/SitePages/What-MIW-Admins-Review-in-Your-PR.aspx)

If the answer is yes, the PR is in good shape.

---

## Final Reminder

The best PRs are:
- Narrow in intent
- Correct in scope
- Accurate in metadata
- Supported by ownership evidence
- Easy to validate
- Safe to automate

That is the fastest path to a clean review.
