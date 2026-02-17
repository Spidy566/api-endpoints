"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
AWS Boto3 clients and executors          | 07-01-2026 | vishal
---------------------------------------------------------------------------
"""
import boto3
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from core.config import AWS_KEY, AWS_SECRET, REGION, logger

process_pool_executor = ProcessPoolExecutor()
thread_pool_executor = ThreadPoolExecutor()

try:
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=AWS_KEY,
        aws_secret_access_key=AWS_SECRET,
        region_name=REGION
    )

    textract_client = boto3.client(
        "textract",
        aws_access_key_id=AWS_KEY,
        aws_secret_access_key=AWS_SECRET,
        region_name=REGION
    )
except Exception as e:
    logger.error(f"Failed to initialize AWS clients: {e}")
    s3_client = None
    textract_client = None