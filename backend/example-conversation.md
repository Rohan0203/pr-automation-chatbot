Q: Which account environment is this PR for?
A: Dev


You said: Q: What resources do you need in this PR?
Q: What resources do you need in this PR? Select all that apply: (Select all that apply)
A: Source (S3), Data Product (S3), Raw Source (Glue DB), Serving DataProduct (Glue DB)

Q: Which enterprise(s) are these for? (Select all that apply)
A: FOOD


You said: Q: Which FOOD subgroup?
Q: Which FOOD subgroup?
A: SALT

Q: Raw Source Glue DB — current or CDP data?
A: Current

Q: Data classification for Glue databases?
A: Confidential - General Use


Claude responded: Last details:
Last details:

Source name for the Raw Glue DB (e.g. sap, concur)?
Data product name for the Serving Glue DB (e.g. c360, controls)?
Serving purpose (e.g. analytics, reporting, consumption)?
Data privacy: PI, PCI, PHI, BCI, or NONE?
Intake IDs — 4 resources total. How many IDs and how do they map?
You said: SA3
SA3
saltProducts
analytics
PI
M0000789- source objects, M0000689- DP o
Claude responded: Here are all 4 YAMLs:
Here are all 4 YAMLs:

S3 Buckets:

1. Source — FOOD/SALT (M0000789)

yaml
intake_id: M0000789
bucket_name: dev-lh1-food-salt-src
bucket_description: Stores source data for FOOD SALT subgroup
aws_account_id: '438465132548'
aws_region: us-east-1
usage_type: Source
enterprise_or_func_name: FOOD
enterprise_or_func_subgrp_name: SALT
2. Data Product — FOOD/SALT (M0000689)

yaml
intake_id: M0000689
bucket_name: dev-cmp2-food-salt-dp
bucket_description: Stores data product for FOOD SALT subgroup
aws_account_id: '933999308564'
aws_region: us-east-1
usage_type: DataProduct
enterprise_or_func_name: FOOD
enterprise_or_func_subgrp_name: SALT
Glue Databases:

3. Raw Source (Current) — SA3, FOOD/SALT (M0000789)

yaml
intake_id: M0000789
database_name: lh_sa3_raw_dev
database_s3_location: "s3://dev-lh1-food-salt-src/raw/current/dev/src/sa3/"
database_description: "Database for SA3 to Lakehouse Ingestion Patterns"
aws_account_id: '438465132548'
region: us-east-1
data_construct: Source
data_env: dev
data_layer: raw
source_name: sa3
data_classification: "Confidential - General Use"
data_privacy: "PI"
enterprise_or_func_name: FOOD
enterprise_or_func_subgrp_name: SALT
data_owner_email: "kyle_britt@cargill.com"
data_owner_github_uname: KyleBritt
data_leader: KatiePorter
4. Serving DataProduct — saltProducts, FOOD/SALT (M0000689)

yaml
intake_id: M0000689
database_name: salt_saltproducts_serving_analytics_dev
database_s3_location: "s3://dev-cmp2-salt-dp/serving/dev/salt/saltproducts/"
database_description: "Stores SaltProducts Serving Data Product for FOOD SALT analytics"
aws_account_id: '933999308564'
region: us-east-1
data_construct: DataProduct
data_env: dev
data_layer: srv
data_product_name: saltproducts
data_classification: "Confidential - General Use"
data_privacy: "PI"
enterprise_or_func_name: FOOD
enterprise_or_func_subgrp_name: SALT
data_owner_email: "kyle_britt@cargill.com"
data_owner_github_uname: KyleBritt
data_leader: KatiePorter

 