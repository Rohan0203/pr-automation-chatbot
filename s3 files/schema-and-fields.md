# YAML Schema & Field Validation

## Mandatory Fields

The following fields MUST be present in every bucket YAML:

- intake_id
- bucket_name
- bucket_description
- aws_account_id
- aws_region
- usage_type
- enterprise_or_func_name
- enterprise_or_func_subgrp_name

Missing any mandatory field → **ERROR**

---

## intake_id Rules

- MUST be non-empty
- MUST NOT be generic (e.g. 123456, 987654, 111111)

---

## Allowed Optional / Default Fields

Only the following optional fields are allowed:

- versioning_enabled
- public_access_blocked
- encryption_enabled
- encryption_type
- encryption_key_arn

Any additional fields → **ERROR**