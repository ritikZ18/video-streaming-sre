from __future__ import annotations

import json
import os
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError


RAW_BUCKET = "streamsre-raw-uploads"
SEGMENTS_BUCKET = "streamsre-hls-segments"


def client():
    return boto3.client(
        "s3",
        endpoint_url="http://minio:9000",
        region_name="us-east-1",
        aws_access_key_id=os.environ["MINIO_ROOT_USER"],
        aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
    )


def wait_for_storage():
    last_error: Exception | None = None
    for _ in range(90):
        try:
            storage = client()
            storage.list_buckets()
            return storage
        except (BotoCoreError, ClientError, OSError) as error:
            last_error = error
            time.sleep(2)
    raise RuntimeError("S3-compatible storage did not become ready") from last_error


def ensure_bucket(storage, name: str) -> None:
    try:
        storage.head_bucket(Bucket=name)
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "")
        if code not in {"404", "NoSuchBucket", "NotFound"}:
            raise
        storage.create_bucket(Bucket=name)


def main() -> None:
    storage = wait_for_storage()
    ensure_bucket(storage, RAW_BUCKET)
    ensure_bucket(storage, SEGMENTS_BUCKET)
    storage.put_bucket_policy(
        Bucket=SEGMENTS_BUCKET,
        Policy=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "PublicReadSegments",
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": "s3:GetObject",
                        "Resource": f"arn:aws:s3:::{SEGMENTS_BUCKET}/*",
                    }
                ],
            }
        ),
    )
    print("storage-bootstrap complete", flush=True)


if __name__ == "__main__":
    main()
