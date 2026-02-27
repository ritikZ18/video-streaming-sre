from __future__ import annotations

from typing import BinaryIO

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, status

from app.config import get_settings


def _client() -> BaseClient:
    settings = get_settings()
    session = boto3.session.Session(region_name=settings.aws_region)
    return session.client("s3", endpoint_url=settings.s3_endpoint_url)


def upload_fileobj(bucket: str, key: str, fileobj: BinaryIO) -> None:
    client = _client()
    try:
        client.upload_fileobj(fileobj, bucket, key)
    except ClientError as exc:  # pragma: no cover - network error
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"NoSuchBucket", "NoSuchBucketPolicy"}:
            # Lazily create bucket in local dev (e.g. LocalStack) and retry once.
            client.create_bucket(Bucket=bucket)
            client.upload_fileobj(fileobj, bucket, key)
            return
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to upload file to object storage",
        ) from exc
    except BotoCoreError as exc:  # pragma: no cover - network error
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to upload file to object storage",
        ) from exc


def object_exists(bucket: str, key: str) -> bool:
    client = _client()
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
            return False
        raise


