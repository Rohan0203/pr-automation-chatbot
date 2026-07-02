"""Quick test for S3 bucket naming fix."""
from tools.derive_tools import _derive_s3_fields

tests = [
    ("CORP compute FIN dp", {"plat_env": "prd", "usage_type": "DataProduct", "enterprise_or_func_name": "CORP", "enterprise_or_func_subgrp_name": "FIN"}, "prd-cmp4-fin-dp"),
    ("CORP lakehouse FIN src", {"plat_env": "prd", "usage_type": "Source", "enterprise_or_func_name": "CORP", "enterprise_or_func_subgrp_name": "FIN"}, "prd-lh1-corp-fin-src"),
    ("AGTR compute APAC dp", {"plat_env": "dev", "usage_type": "DataProduct", "enterprise_or_func_name": "AGTR", "enterprise_or_func_subgrp_name": "APAC"}, "dev-cmp1-agtr-apac-dp"),
    ("AGTR lakehouse src", {"plat_env": "prd", "usage_type": "Source", "enterprise_or_func_name": "AGTR", "enterprise_or_func_subgrp_name": ""}, "prd-lh1-agtr-src"),
    ("CORP lakehouse HR scripts", {"plat_env": "dev", "usage_type": "Scripts", "enterprise_or_func_name": "CORP", "enterprise_or_func_subgrp_name": "HR"}, "dev-lh1-corp-hr-scripts"),
]

for name, fields, expected in tests:
    result = _derive_s3_fields(fields)
    actual = result["bucket_name"]
    status = "PASS" if actual == expected else "FAIL"
    print(f"  {status}: {name}")
    if actual != expected:
        print(f"        expected: {expected}")
        print(f"        actual:   {actual}")
