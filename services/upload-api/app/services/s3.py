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


def _ensure_bucket(client: BaseClient, bucket: str) -> None:
    """Create the bucket if it doesn't exist (local-dev parity with real AWS)."""
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in {"404", "NoSuchBucket", "NoSuchBucketPolicy"}:
            client.create_bucket(Bucket=bucket)
        else:
            raise


def upload_fileobj(bucket: str, key: str, fileobj: BinaryIO) -> None:
    client = _client()
    try:
        # Ensure the bucket exists BEFORE the (single) upload. The previous
        # create-on-error-and-retry left the file stream at EOF on the retry,
        # producing a 0-byte object.
        _ensure_bucket(client, bucket)
        try:
            fileobj.seek(0)
        except (OSError, ValueError):
            pass
        client.upload_fileobj(fileobj, bucket, key)
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover - network error
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


