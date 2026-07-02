# MIW S3 Bucket Validation Rules

This repository defines the authoritative validation rules enforced
by MIW for S3 bucket creation requests.

All validations are executed **before provisioning**, against the
user-submitted YAML template.

## Validation Objectives

- Enforce governance and ownership correctness
- Prevent unsafe or non-compliant S3 configurations
- Reduce manual review and human error
- Ensure predictable automation across Lakehouse and Compute accounts

## Validation Domains

The validation agent MUST evaluate rules across the following domains:

1. Schema and required fields
2. Account, environment, and region restrictions
3. Naming conventions
4. Ownership and enterprise alignment
5. Usage-type-specific constraints
6. Security and baseline controls
7. Governance and deprecation rules

Each domain is defined in a dedicated Markdown file.

## Blocking Rules

Any **ERROR-level violation** MUST block approval and merge.
Warnings MAY be surfaced but do not block provisioning.

