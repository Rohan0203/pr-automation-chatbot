# Account, Environment & Region Rules

## Allowed AWS Regions

- Only `us-east-1` is allowed at this time.

Any other region → **ERROR**

---

## Allowed AWS Account IDs

### Dev Accounts
- 438465132548
- 068887784423
- 933999308564
- 836901248866
- 324612370323

### Prod Accounts
- 578647603827
- 632247962242
- 011379513867
- 884308299029
- 367241115350

---

## Environment Inference

- `dev-*` accounts → Dev
- `prd-*` accounts → Prod

Mismatch between bucket name and account environment → **ERROR**