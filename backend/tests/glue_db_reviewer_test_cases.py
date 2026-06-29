# Glue DB Reviewer — Test Cases
#
# All 18 fields are now mandatory. Source cases use empty "" for
# DataProduct-specific fields and vice-versa.
# Every case includes data_classification and data_privacy.
#
# HOW TO USE:
#   1. Start a chat session and select resource type "glue_db"
#   2. Paste the YAML (or feed values so the generator produces it)
#   3. When the reviewer runs, compare its output to EXPECTED below
# ────────────────────────────────────────────────────────────────

# ══════════════════════════════════════════════════════════════
# CASE 1 — FULLY VALID: Lakehouse Source Raw
# EXPECTED: PASS — no violations
# ══════════════════════════════════════════════════════════════
# intake_id: M123456
# database_name: lh_concur_raw_dev
# database_s3_location: "s3://dev-lh1-corp-fin-src/raw/current/dev/src/concur/"
# database_description: "Store Concur raw data in Lakehouse"
# aws_account_id: '438465132548'
# region: us-east-1
# data_env: dev
# data_layer: raw
# data_construct: Source
# source_name: concur
# data_product_name: concur
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 2 — FULLY VALID: Compute Curated DataProduct
# EXPECTED: PASS — no violations
# ══════════════════════════════════════════════════════════════
# intake_id: M123457
# database_name: fin_controls_curated_dev
# database_s3_location: "s3://dev-cmp4-fin-dp/curated/dev/fin/controls/"
# database_description: "Store finance controls curated data"
# aws_account_id: '324612370323'
# region: us-east-1
# data_env: dev
# data_layer: curated
# data_construct: DataProduct
# source_name: controls
# data_product_name: controls
# data_owner_email: "abc_xyz@cargill.com"
# data_owner_github_uname: AbcXyz
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 3 — WRONG ACCOUNT FOR LAYER (ACC-001)
# raw layer in Compute account → ERROR
# EXPECTED: FAIL — "Raw databases must be in Lakehouse"
# ══════════════════════════════════════════════════════════════
# intake_id: M100001
# database_name: lh_sap_raw_dev
# database_s3_location: "s3://dev-lh1-agtr-src/raw/current/dev/src/sap/"
# database_description: "SAP raw data"
# aws_account_id: '068887784423'       ← WRONG: Compute account for raw layer
# region: us-east-1
# data_env: dev
# data_layer: raw
# data_construct: Source
# source_name: sap
# data_product_name: sap
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: AGTR
# enterprise_or_func_subgrp_name: EMEA
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 4 — WRONG ACCOUNT FOR LAYER (ACC-002)
# curated layer in Lakehouse account → ERROR
# EXPECTED: FAIL — "Curated databases must be in Compute"
# ══════════════════════════════════════════════════════════════
# intake_id: M100002
# database_name: fin_controls_curated_dev
# database_s3_location: "s3://dev-cmp4-fin-dp/curated/dev/fin/controls/"
# database_description: "Finance controls curated"
# aws_account_id: '438465132548'       ← WRONG: Lakehouse account for curated
# region: us-east-1
# data_env: dev
# data_layer: curated
# data_construct: DataProduct
# source_name: controls
# data_product_name: controls
# data_owner_email: "abc_xyz@cargill.com"
# data_owner_github_uname: AbcXyz
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 5 — BAD DATABASE NAME: uppercase (NAM-001)
# EXPECTED: FAIL — "database_name must be lowercase"
# ══════════════════════════════════════════════════════════════
# intake_id: M100003
# database_name: LH_Concur_Raw_Dev     ← WRONG: uppercase
# database_s3_location: "s3://dev-lh1-corp-fin-src/raw/current/dev/src/concur/"
# database_description: "Concur raw data"
# aws_account_id: '438465132548'
# region: us-east-1
# data_env: dev
# data_layer: raw
# data_construct: Source
# source_name: concur
# data_product_name: concur
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 6 — BAD DATABASE NAME: missing env suffix (NAM-002)
# EXPECTED: FAIL — "database_name must end with _dev or _prd"
# ══════════════════════════════════════════════════════════════
# intake_id: M100004
# database_name: lh_concur_raw         ← WRONG: no _dev or _prd suffix
# database_s3_location: "s3://dev-lh1-corp-fin-src/raw/current/dev/src/concur/"
# database_description: "Concur raw data"
# aws_account_id: '438465132548'
# region: us-east-1
# data_env: dev
# data_layer: raw
# data_construct: Source
# source_name: concur
# data_product_name: concur
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 7 — BAD DATABASE NAME: Lakehouse without lh_ prefix (NAM-003)
# EXPECTED: FAIL — "Lakehouse database names must start with lh_"
# ══════════════════════════════════════════════════════════════
# intake_id: M100005
# database_name: concur_raw_dev        ← WRONG: missing lh_ prefix
# database_s3_location: "s3://dev-lh1-corp-fin-src/raw/current/dev/src/concur/"
# database_description: "Concur raw data"
# aws_account_id: '438465132548'
# region: us-east-1
# data_env: dev
# data_layer: raw
# data_construct: Source
# source_name: concur
# data_product_name: concur
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 8 — BAD DATABASE NAME: Compute with lh_ prefix (NAM-004)
# EXPECTED: FAIL — "Compute database names must not use lh_ prefix"
# ══════════════════════════════════════════════════════════════
# intake_id: M100006
# database_name: lh_fin_controls_curated_dev  ← WRONG: lh_ on Compute
# database_s3_location: "s3://dev-cmp4-fin-dp/curated/dev/fin/controls/"
# database_description: "Finance controls curated"
# aws_account_id: '324612370323'
# region: us-east-1
# data_env: dev
# data_layer: curated
# data_construct: DataProduct
# source_name: controls
# data_product_name: controls
# data_owner_email: "abc_xyz@cargill.com"
# data_owner_github_uname: AbcXyz
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 9 — BAD S3 LOCATION: Source using dp bucket (S3-001/S3-002)
# EXPECTED: FAIL — "Source databases must use src buckets"
# ══════════════════════════════════════════════════════════════
# intake_id: M100007
# database_name: lh_concur_raw_dev
# database_s3_location: "s3://dev-cmp4-fin-dp/raw/current/dev/src/concur/"
# database_description: "Concur raw data"
# aws_account_id: '438465132548'
# region: us-east-1
# data_env: dev
# data_layer: raw
# data_construct: Source
# source_name: concur
# data_product_name: concur
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 10 — BAD S3 LOCATION: enterprise missing from bucket (S3-003)
# EXPECTED: FAIL — "Bucket name must include owning enterprise"
# ══════════════════════════════════════════════════════════════
# intake_id: M100008
# database_name: lh_concur_raw_dev
# database_s3_location: "s3://dev-lh1-src/raw/current/dev/src/concur/"
# database_description: "Concur raw data"
# aws_account_id: '438465132548'
# region: us-east-1
# data_env: dev
# data_layer: raw
# data_construct: Source
# source_name: concur
# data_product_name: concur
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 11 — CORP bucket missing subgroup (S3-004)
# EXPECTED: FAIL — "CORP buckets must include subgroup in bucket name"
# ══════════════════════════════════════════════════════════════
# intake_id: M100009
# database_name: lh_concur_raw_dev
# database_s3_location: "s3://dev-lh1-corp-src/raw/current/dev/src/concur/"  ← WRONG: corp without subgroup
# database_description: "Concur raw data"
# aws_account_id: '438465132548'
# region: us-east-1
# data_env: dev
# data_layer: raw
# data_construct: Source
# source_name: concur
# data_product_name: concur
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 12 — INVALID intake_id format (FLD-001)
# EXPECTED: FAIL — "intake_id must start with M followed by digits"
# ══════════════════════════════════════════════════════════════
# intake_id: 123456                    ← WRONG: no M prefix
# database_name: lh_concur_raw_dev
# database_s3_location: "s3://dev-lh1-corp-fin-src/raw/current/dev/src/concur/"
# database_description: "Concur raw data"
# aws_account_id: '438465132548'
# region: us-east-1
# data_env: dev
# data_layer: raw
# data_construct: Source
# source_name: concur
# data_product_name: concur
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 13 — UNREGISTERED account ID (FLD-002)
# EXPECTED: FAIL — "aws_account_id not in approved allow-list"
# ══════════════════════════════════════════════════════════════
# intake_id: M100010
# database_name: lh_concur_raw_dev
# database_s3_location: "s3://dev-lh1-corp-fin-src/raw/current/dev/src/concur/"
# database_description: "Concur raw data"
# aws_account_id: '999999999999'       ← WRONG: not a registered account
# region: us-east-1
# data_env: dev
# data_layer: raw
# data_construct: Source
# source_name: concur
# data_product_name: concur
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 14 — WRONG region (FLD-003)
# EXPECTED: FAIL — "region must be us-east-1"
# ══════════════════════════════════════════════════════════════
# intake_id: M100011
# database_name: lh_concur_raw_dev
# database_s3_location: "s3://dev-lh1-corp-fin-src/raw/current/dev/src/concur/"
# database_description: "Concur raw data"
# aws_account_id: '438465132548'
# region: eu-west-1                    ← WRONG: not us-east-1
# data_env: dev
# data_layer: raw
# data_construct: Source
# source_name: concur
# data_product_name: concur
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 15 — INVALID enterprise (FLD-007)
# EXPECTED: FAIL — "enterprise_or_func_name must be AGTR, CORP, FOOD, or SPEC"
# ══════════════════════════════════════════════════════════════
# intake_id: M100012
# database_name: lh_concur_raw_dev
# database_s3_location: "s3://dev-lh1-corp-fin-src/raw/current/dev/src/concur/"
# database_description: "Concur raw data"
# aws_account_id: '438465132548'
# region: us-east-1
# data_env: dev
# data_layer: raw
# data_construct: Source
# source_name: concur
# data_product_name: concur
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: TECH        ← WRONG: not in AGTR/CORP/FOOD/SPEC
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 16 — SUBGROUP MISMATCH (FLD-008)
# Subgroup does not belong to stated enterprise
# EXPECTED: FAIL — "FIN is not a valid subgroup for AGTR"
# ══════════════════════════════════════════════════════════════
# intake_id: M100013
# database_name: lh_concur_raw_dev
# database_s3_location: "s3://dev-lh1-agtr-src/raw/current/dev/src/concur/"
# database_description: "Concur raw data"
# aws_account_id: '438465132548'
# region: us-east-1
# data_env: dev
# data_layer: raw
# data_construct: Source
# source_name: concur
# data_product_name: concur
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: AGTR
# enterprise_or_func_subgrp_name: FIN  ← WRONG: FIN belongs to CORP, not AGTR
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 17 — MISSING DataProduct fields (FLD-009/010/011)
# data_construct = DataProduct but missing owner fields
# EXPECTED: FAIL — missing data_owner_email, data_owner_github_uname, data_leader
# ══════════════════════════════════════════════════════════════
# intake_id: M100014
# database_name: fin_controls_curated_dev
# database_s3_location: "s3://dev-cmp4-fin-dp/curated/dev/fin/controls/"
# database_description: "Finance controls curated"
# aws_account_id: '324612370323'
# region: us-east-1
# data_env: dev
# data_layer: curated
# data_construct: DataProduct
# source_name: controls
# data_product_name: controls
# data_owner_email: ""                 ← MISSING
# data_owner_github_uname: ""          ← MISSING
# data_leader: ""                      ← MISSING
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 18 — INVALID data_privacy value (FLD-006)
# EXPECTED: FAIL — "data_privacy must be PI, PCI, PHI, BCI, or NONE"
# ══════════════════════════════════════════════════════════════
# intake_id: M100015
# database_name: lh_concur_raw_dev
# database_s3_location: "s3://dev-lh1-corp-fin-src/raw/current/dev/src/concur/"
# database_description: "Concur raw data"
# aws_account_id: '438465132548'
# region: us-east-1
# data_env: dev
# data_layer: raw
# data_construct: Source
# source_name: concur
# data_product_name: concur
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: SENSITIVE              ← WRONG: not in PI/PCI/PHI/BCI/NONE


# ══════════════════════════════════════════════════════════════
# CASE 19 — MULTIPLE VIOLATIONS (compound)
# Wrong account + uppercase name + wrong region
# EXPECTED: FAIL — 3 errors (ACC-001, NAM-001, FLD-003)
# ══════════════════════════════════════════════════════════════
# intake_id: M100016
# database_name: LH_Concur_Raw_Dev     ← WRONG: uppercase
# database_s3_location: "s3://dev-lh1-corp-fin-src/raw/current/dev/src/concur/"
# database_description: "Concur raw data"
# aws_account_id: '068887784423'       ← WRONG: Compute account for raw
# region: eu-west-1                    ← WRONG: not us-east-1
# data_env: dev
# data_layer: raw
# data_construct: Source
# source_name: concur
# data_product_name: concur
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 20 — VALID: Lakehouse raw_serving
# EXPECTED: PASS — no violations
# ══════════════════════════════════════════════════════════════
# intake_id: M123459
# database_name: lh_sap_raw_serving_prd
# database_s3_location: "s3://prd-lh1-agtr-src/raw_serving/prd/src/sap/"
# database_description: "SAP raw serving data for Ag and Trading"
# aws_account_id: '578647603827'
# region: us-east-1
# data_env: prd
# data_layer: raw_serving
# data_construct: Source
# source_name: sap
# data_product_name: sap
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: AGTR
# enterprise_or_func_subgrp_name: EMEA
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 21 — VALID: Compute serving DataProduct
# EXPECTED: PASS — no violations
# ══════════════════════════════════════════════════════════════
# intake_id: M123458
# database_name: hr_successfactors_serving_analytics_dev
# database_s3_location: "s3://dev-cmp4-hr-dp/serving/dev/hr/successfactors/analytics/"
# database_description: "Store SuccessFactors serving data for analytics"
# aws_account_id: '324612370323'
# region: us-east-1
# data_env: dev
# data_layer: serving
# data_construct: DataProduct
# source_name: successfactors
# data_product_name: successfactors
# data_owner_email: "abc_xyz@cargill.com"
# data_owner_github_uname: AbcXyz
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: HR
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 22 — serving layer in Lakehouse account (ACC-002)
# EXPECTED: FAIL — "Serving databases must be in Compute"
# ══════════════════════════════════════════════════════════════
# intake_id: M100017
# database_name: hr_successfactors_serving_analytics_dev
# database_s3_location: "s3://dev-cmp4-hr-dp/serving/dev/hr/successfactors/analytics/"
# database_description: "SuccessFactors serving"
# aws_account_id: '438465132548'       ← WRONG: Lakehouse account for serving
# region: us-east-1
# data_env: dev
# data_layer: serving
# data_construct: DataProduct
# source_name: successfactors
# data_product_name: successfactors
# data_owner_email: "abc_xyz@cargill.com"
# data_owner_github_uname: AbcXyz
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: HR
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 23 — env mismatch: database_name says _dev but data_env is prd
# EXPECTED: FAIL — "database_name suffix _dev does not match data_env prd"
# ══════════════════════════════════════════════════════════════
# intake_id: M100018
# database_name: lh_concur_raw_dev     ← WRONG: says _dev
# database_s3_location: "s3://prd-lh1-corp-fin-src/raw/current/prd/src/concur/"
# database_description: "Concur raw data"
# aws_account_id: '578647603827'
# region: us-east-1
# data_env: prd                        ← MISMATCH: prd vs _dev in name
# data_layer: raw
# data_construct: Source
# source_name: concur
# data_product_name: concur
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 24 — S3 location layer mismatch: path says curated but data_layer is raw
# EXPECTED: FAIL — "S3 path layer segment does not match data_layer"
# ══════════════════════════════════════════════════════════════
# intake_id: M100019
# database_name: lh_concur_raw_dev
# database_s3_location: "s3://dev-lh1-corp-fin-src/curated/dev/src/concur/"  ← WRONG: curated in path for raw layer
# database_description: "Concur raw data"
# aws_account_id: '438465132548'
# region: us-east-1
# data_env: dev
# data_layer: raw
# data_construct: Source
# source_name: concur
# data_product_name: concur
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 25 — INVALID data_env (FLD-004)
# EXPECTED: FAIL — "data_env must be dev or prd"
# ══════════════════════════════════════════════════════════════
# intake_id: M100020
# database_name: lh_concur_raw_staging
# database_s3_location: "s3://dev-lh1-corp-fin-src/raw/current/dev/src/concur/"
# database_description: "Concur raw data"
# aws_account_id: '438465132548'
# region: us-east-1
# data_env: staging                    ← WRONG: not dev or prd
# data_layer: raw
# data_construct: Source
# source_name: concur
# data_product_name: concur
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Confidential - General Use
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 26 — INVALID data_classification value (FLD-005)
# EXPECTED: FAIL — "data_classification not in allowed enum"
# ══════════════════════════════════════════════════════════════
# intake_id: M100021
# database_name: lh_concur_raw_dev
# database_s3_location: "s3://dev-lh1-corp-fin-src/raw/current/dev/src/concur/"
# database_description: "Concur raw data"
# aws_account_id: '438465132548'
# region: us-east-1
# data_env: dev
# data_layer: raw
# data_construct: Source
# source_name: concur
# data_product_name: concur
# data_owner_email: "john_doe@cargill.com"
# data_owner_github_uname: JohnDoe
# data_leader: a123456
# enterprise_or_func_name: CORP
# enterprise_or_func_subgrp_name: FIN
# data_classification: Top Secret      ← WRONG: not in allowed enum
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 27 — VALID: FOOD enterprise with subgroup
# EXPECTED: PASS — no violations
# ══════════════════════════════════════════════════════════════
# intake_id: M123460
# database_name: lh_salesforce_raw_dev
# database_s3_location: "s3://dev-lh1-food-fs_na-src/raw/current/dev/src/salesforce/"
# database_description: "Salesforce raw data for Food Solutions NA"
# aws_account_id: '438465132548'
# region: us-east-1
# data_env: dev
# data_layer: raw
# data_construct: Source
# source_name: salesforce
# data_product_name: salesforce
# data_owner_email: "jane_smith@cargill.com"
# data_owner_github_uname: JaneSmith
# data_leader: b654321
# enterprise_or_func_name: FOOD
# enterprise_or_func_subgrp_name: FS_NA
# data_classification: Public
# data_privacy: NONE


# ══════════════════════════════════════════════════════════════
# CASE 28 — VALID: SPEC enterprise internal layer (either account OK)
# EXPECTED: PASS — no violations
# ══════════════════════════════════════════════════════════════
# intake_id: M123461
# database_name: lh_internal_tools_internal_dev
# database_s3_location: "s3://dev-lh1-spec-anh-src/internal/dev/src/internal_tools/"
# database_description: "Internal tools data for Spec ANH"
# aws_account_id: '438465132548'
# region: us-east-1
# data_env: dev
# data_layer: internal
# data_construct: Source
# source_name: internal_tools
# data_product_name: internal_tools
# data_owner_email: "mike_jones@cargill.com"
# data_owner_github_uname: MikeJones
# data_leader: c789012
# enterprise_or_func_name: SPEC
# enterprise_or_func_subgrp_name: ANH
# data_classification: Confidential - Limited
# data_privacy: BCI
