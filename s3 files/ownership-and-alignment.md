# Ownership & Alignment Rules

## enterprise_or_func_name

Allowed values:
- AGTR
- CORP
- FOOD
- SPEC

Any other value → **ERROR**

---

## enterprise_or_func_subgrp_name

Allowed subgroups are restricted per enterprise.

(Enumerate exactly as in your source file.)

---

## Account-Based Ownership Rules

### Lakehouse Accounts
- OWNING_ENTITY MUST be Enterprise / Function
- Subgroup allowed only for CORP contexts

### Compute Accounts
- OWNING_ENTITY MUST be Subgroup
- Enterprise-level ownership is NOT allowed
``