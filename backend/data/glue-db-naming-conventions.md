# Glue Database Naming Conventions

> **Notation:** `[ ]` = mandatory, `< >` = optional

---

## Global Rule

- All **Lakehouse** databases MUST start with the prefix **`lh_`**
- **Compute** databases do NOT use any account prefix (no `lh_`, no `AWS_ACCT_ABBR`)

---

## 1. Lakehouse — Raw Layer

**Account:** Lakehouse  
**Data Layer:** `raw`

Two patterns depending on whether the database represents a **source system** or a **data product**:

### Pattern A — Source System
```
lh_<CDP>_[SRC_SYS_NAME]_<SRC_SYS_INSTANCE>_raw_[DATA_ENV]
```

| Example | CDP | SRC_SYS_NAME | SRC_SYS_INSTANCE | DATA_ENV |
|---|---|---|---|---|
| `lh_concur_raw_dev` | — | concur | — | dev |
| `lh_sap_tc1_raw_dev` | — | sap | tc1 | dev |
| `lh_cdp_sap_tc1_raw_dev` | cdp | sap | tc1 | dev |

### Pattern B — Data Product (with CDP)
```
lh_<CDP>_[OWNING_ENTITY]_[PRODUCT_NAME]_raw_[DATA_ENV]
```

| Example | CDP | OWNING_ENTITY | PRODUCT_NAME | DATA_ENV |
|---|---|---|---|---|
| `lh_cdp_fin_controls_raw_dev` | cdp | fin | controls | dev |

---

## 2. Lakehouse — Raw Serving Layer

**Account:** Lakehouse  
**Data Layer:** `raw_serving`

```
lh_<CDP>_[SRC_SYS_NAME]_<SRC_SYS_INSTANCE>_raw_serving_[DATA_ENV]
```

| Example | CDP | SRC_SYS_NAME | SRC_SYS_INSTANCE | DATA_ENV |
|---|---|---|---|---|
| `lh_sap_tc1_raw_serving_dev` | — | sap | tc1 | dev |

---

## 3. Compute — Curated Layer

**Account:** Compute  
**Data Layer:** `curated`

```
[OWNING_ENTITY]_[PRODUCT_NAME]_curated_[DATA_ENV]
```

| Example | OWNING_ENTITY | PRODUCT_NAME | DATA_ENV |
|---|---|---|---|
| `fin_general_ledger_curated_dev` | fin | general_ledger | dev |
| `wtg_seaborne_curated_dev` | wtg | seaborne | dev |

---

## 4. Compute — Serving Layer

**Account:** Compute  
**Data Layer:** `serving`

```
[OWNING_ENTITY]_[PRODUCT_NAME]_serving_[PURPOSE]_[DATA_ENV]
```

> **Note:** Serving layer **requires** a mandatory **PURPOSE** segment (e.g., `analytics`, `events`, `reporting`). This distinguishes why the serving DB exists.

| Example | OWNING_ENTITY | PRODUCT_NAME | PURPOSE | DATA_ENV |
|---|---|---|---|---|
| `fin_general_ledger_serving_analytics_dev` | fin | general_ledger | analytics | dev |
| `wtg_seaborne_serving_events_dev` | wtg | seaborne | events | dev |
| `hr_successfactors_serving_reporting_dev` | hr | successfactors | reporting | dev |

---

## 5. Compute — Internal Layer

**Account:** Compute  
**Data Layer:** `internal`

Two patterns:

### Pattern A — Source System (federated from Lakehouse)
```
lh_[SRC_SYS_NAME]_<SRC_SYS_INSTANCE>_internal_[DATA_ENV]
```

| Example | SRC_SYS_NAME | DATA_ENV |
|---|---|---|
| `lh_concur_internal_dev` | concur | dev |

### Pattern B — Data Product
```
[OWNING_ENTITY]_[PRODUCT_NAME]_internal_[DATA_ENV]
```

| Example | OWNING_ENTITY | PRODUCT_NAME | DATA_ENV |
|---|---|---|---|
| `fin_general_ledger_internal_dev` | fin | general_ledger | dev |

---

## Variable Reference

| Variable | Required | Description |
|---|---|---|
| `CDP` | Optional | Indicates data originates from CDP |
| `SRC_SYS_NAME` | Mandatory (source DBs) | Lowercase source system name (e.g., `concur`, `sap`) |
| `SRC_SYS_INSTANCE` | Optional | Sub-instance of source system (e.g., `tc1`, `tcf`) |
| `OWNING_ENTITY` | Mandatory (product DBs) | Smallest accountable group — enterprise, function, or subgroup (e.g., `fin`, `wtg`) |
| `PRODUCT_NAME` | Mandatory (product DBs) | Lowercase data product name (e.g., `general_ledger`, `controls`) |
| `DATA_LAYER` | Mandatory | One of: `raw`, `raw_serving`, `curated`, `serving`, `internal` |
| `PURPOSE` | Mandatory (serving only) | Why the serving DB exists (e.g., `analytics`, `events`) |
| `DATA_ENV` | Mandatory | Environment: `dev`, `prd`, `qa`, `stg` |

---

## Account Abbreviation Table

| Account Alias | Abbreviation |
|---|---|
| minerva-snd-lakehouse-001 | snd-lh1 |
| minerva-snd-compute-001 | snd-cmp1 |
| minerva-dev-lakehouse-001 | dev-lh1 |
| minerva-dev-compute-001 | dev-cmp1 |
| minerva-dev-compute-002 | dev-cmp2 |
| minerva-dev-compute-003 | dev-cmp3 |
| minerva-dev-compute-004 | dev-cmp4 |
| minerva-prod-lakehouse-001 | prd-lh1 |
| minerva-prod-compute-001 | prd-cmp1 |
| minerva-prod-compute-002 | prd-cmp2 |
| minerva-prod-compute-003 | prd-cmp3 |
| minerva-prod-compute-004 | prd-cmp4 |
