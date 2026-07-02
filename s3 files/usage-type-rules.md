# Usage-Type Specific Rules

## Allowed usage_type Values

- Source
- DataProduct
- Scripts
- EngAssets

---

## Source Buckets

- Allowed ONLY in:
  - Dev: 438465132548
  - Prod: 578647603827
- MUST align to Enterprise / Function
- Non-aligned source systems → **ERROR**

---

## DataProduct Buckets

- Allowed ONLY in Compute accounts:
  - Dev: 068887784423, 933999308564, 836901248866, 324612370323
  - Prod: 632247962242, 011379513867, 884308299029, 367241115350

---

## Scripts Buckets

- versioning_enabled MUST be true
- Allowed in both Lakehouse and Compute
- Ownership depth depends on account type

---

## EngAssets Buckets

- versioning_enabled MUST be false
- Non-authoritative storage