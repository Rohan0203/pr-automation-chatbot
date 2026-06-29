s3

template

```yaml
intake_id: I123456
bucket_name: prd-lh1-agtr-src
bucket_description: "Stores Source system specific data for Ag and Trading"
aws_account_id: 578647603827
aws_region: us-east-1
usage_type: Source
enterprise_or_func_name: AGTR
enterprise_or_func_subgrp_name: ""
# Default values
#versioning_enabled: false
#public_access_blocked: true
#encryption_enabled: true
#encryption_type: "SSE-S3"
#encryption_key_arn: "<arn>"
``` 

actually approved

```yaml
intake_id: M0000485
bucket_name: prd-lh1-agtr-scripts
bucket_description: "Stores Pyspark scripts for Ag & Trading "
aws_account_id: '578647603827'
aws_region: us-east-1
usage_type: DataProduct
enterprise_or_func_name: "AGTR"
enterprise_or_func_subgrp_name: "TDA"
``` 

gluedb

template

```yaml
intake_id: I123456
database_name: lh_cdp_sap_tc1_raw_prd
database_s3_location: "s3://prd-lh1-food-src/raw/cdp/prd/src/sap_tc1/"
database_description: "Store business historical data for SAP_TC1 from CDP system"
aws_account_id: 578647603827
region: us-east-1
data_construct: Source
data_env: prd
data_layer: raw
source_name: cdp
data_classification: "Confidential - General Use"
data_privacy: ""
enterprise_or_func_name:  FOOD
enterprise_or_func_subgrp_name: ""
data_owner_email: "abc_xyz@cargill.com"
data_owner_github_uname: AbcXyz
data_leader: a123456
``` 

actually approved

```yaml
intake_id: M0000934
database_name: lh_1c_manual_upload_raw_prd
database_s3_location: "s3://prd-lh1-spec-src/raw/current/prd/src/1c_manual_upload/"
database_description: "Store 1c data from manual file upload"
aws_account_id: '578647603827'
region: us-east-1
data_construct: Source
data_env: prd
data_layer: raw
source_name: 1c_manual_upload
data_classification: "Confidential - Restricted"
data_privacy: "None"
enterprise_or_func_name: "SPEC"
enterprise_or_func_subgrp_name: "ANH"
data_owner_email: "shawn_yeager@cargill.com"
data_owner_github_uname: ShawnYeager
data_leader: jawillho
``` 