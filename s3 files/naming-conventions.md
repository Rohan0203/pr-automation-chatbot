# S3 Bucket Naming Conventions

All bucket names MUST follow:

[AWS_ACCT_ABBR]-[OWNING_ENTITY]-[BUCKET_PURPOSE]

## AWS_ACCT_ABBR

Valid values include:
- dev-lh1
- dev-cmp1 … dev-cmp4
- prd-lh1
- prd-cmp1 … prd-cmp4

---

## BUCKET_PURPOSE

Must be one of:
- src
- dp
- scripts
- eng-assets
- ops

---

## Global Constraints

- Lowercase only
- DNS-compliant
- Globally unique
``