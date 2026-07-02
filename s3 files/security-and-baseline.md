# Security & Baseline Controls

## Public Access

- public_access_blocked MUST be true

---

## Encryption

- encryption_enabled MUST be true
- encryption_type MUST be SSE-S3

---

## Versioning

- MUST be false for all buckets
- EXCEPTION: Scripts buckets MUST enable versioning