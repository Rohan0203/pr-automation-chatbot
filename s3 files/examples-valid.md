SOME GOOD EXAMPLES YAML TEMPLETES FOR Reference

LAKEHOUSE BUCKETS
EXAMPLE 1:
intake_id: I-123456
bucket_name: dev-lh1-agtr-src
bucket_description: "Stores Source system specific data for Ag and Trading"
aws_account_id: 438465132548
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

EXAMPLE 2:
intake_id: I-123456
bucket_name: dev-lh1-corp-hr-eng-assets
bucket_description: "Stores Engineering asset artifacts like Logs and Temporary data for Corporate HR"
aws_account_id: 438465132548
aws_region: us-east-1
usage_type: EngAssets
enterprise_or_func_name: CORP
enterprise_or_func_subgrp_name: HR
# Default values
#versioning_enabled: false
#public_access_blocked: true
#encryption_enabled: true
#encryption_type: "SSE-S3"
#encryption_key_arn: "<arn>"

EXAMPLE 3:
intake_id: M0000440
bucket_name: dev-lh1-corp-hr-scripts
bucket_description: For storing PySpark scripts for CORP HR subgroup
aws_account_id: '438465132548'
aws_region: us-east-1
usage_type: Scripts
enterprise_or_func_name: CORP
enterprise_or_func_subgrp_name: HR
versioning_enabled: true
# Default values
#public_access_blocked: true
#encryption_enabled: true
#encryption_type: "SSE-S3"
#encryption_key_arn: "<arn>"

COMPUTE Account
EXAMPLE 1:
intake_id: I-123456
bucket_name: dev-cmp1-fin-eng-assets
bucket_description: "Stores Engineering asset artifacts like Logs and Temporary data for Corporate FIN"
aws_account_id: 068887784423
aws_region: us-east-1
usage_type: EngAssets
enterprise_or_func_name: CORP
enterprise_or_func_subgrp_name: FIN
# Default values
#versioning_enabled: false
#public_access_blocked: true
#encryption_enabled: true
#encryption_type: "SSE-S3"
#encryption_key_arn: "<arn>"

EXAMPLE 2:
intake_id: M0000440
bucket_name: dev-cmp1-fin-scripts
bucket_description: For storing PySpark scripts for CORP FIN subgroup
aws_account_id: '068887784423'
aws_region: us-east-1
usage_type: Scripts
enterprise_or_func_name: CORP
enterprise_or_func_subgrp_name: FIN
versioning_enabled: true
# Default values
#public_access_blocked: true
#encryption_enabled: true
#encryption_type: "SSE-S3"
#encryption_key_arn: "<arn>"


EXAMPLE 3:
intake_id: M-0000485
bucket_name: dev-cmp1-agtr-apac-dp
bucket_description: Stores data product for Ag & Trading
aws_account_id: '068887784423'
aws_region: us-east-1
usage_type: DataProduct
enterprise_or_func_name: AGTR
enterprise_or_func_subgrp_name: APAC
# Default values
#versioning_enabled: false
#public_access_blocked: true
#encryption_enabled: true
#encryption_type: "SSE-S3"
#encryption_key_arn: "<arn>"