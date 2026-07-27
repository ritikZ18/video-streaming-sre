from __future__ import annotations

from typing import BinaryIO

import boto3
from app.config import get_settings
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, status


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


def delete_prefix(bucket: str, prefix: str) -> int:
    """Delete every object under ``prefix`` (e.g. all of one job's segments or its
    raw source). Best-effort: returns the count removed and never raises, since the
    catalog row is the source of truth for what's visible."""
    client = _client()
    deleted = 0
    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objs:
                client.delete_objects(Bucket=bucket, Delete={"Objects": objs})
                deleted += len(objs)
    except (BotoCoreError, ClientError):
        pass
    return deleted


def upload_bytes(bucket: str, key: str, data: bytes, content_type: str) -> None:
    """Store raw bytes with an explicit Content-Type (used for custom artwork so
    the browser renders the poster/backdrop correctly)."""
    client = _client()
    try:
        _ensure_bucket(client, bucket)
        client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover - network error
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to store artwork in object storage",
        ) from exc


def first_key(bucket: str, prefix: str) -> str | None:
    """Return the first object key under a prefix (used to find a title's original
    source before re-transcoding), or None if nothing is there."""
    client = _client()
    try:
        resp = client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
        items = resp.get("Contents", [])
        return items[0]["Key"] if items else None
    except (BotoCoreError, ClientError):
        return None


