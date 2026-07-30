from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

import boto3
from app.config import get_settings
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, status


def _resource():
    settings = get_settings()
    return boto3.resource(
        "dynamodb",
        region_name=settings.aws_region,
        endpoint_url=settings.dynamodb_endpoint_url,
    )


def _table():
    return _resource().Table(get_settings().queue_table)


def _ensure_table() -> None:
    """Create the queue table on demand (parity with the catalog's lazy create)."""
    settings = get_settings()
    resource = _resource()
    client = resource.meta.client
    try:
        client.describe_table(TableName=settings.queue_table)
        return
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
            raise
    resource.create_table(
        TableName=settings.queue_table,
        KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "job_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    client.get_waiter("table_exists").wait(TableName=settings.queue_table)


def enqueue_transcode_job(
    job_id: str, s3_key: str, filename: str, mode: str = "transcode"
) -> None:
    """Add a transcode job to the durable, DynamoDB-backed queue.

    The queue item is keyed by ``job_id`` so a re-enqueue (e.g. admin
    re-transcode) simply overwrites the entry and makes it immediately
    claimable — never a duplicate. ``visible_at`` is the lease clock the worker
    uses for at-least-once delivery; a fresh job is visible right away.

    ``mode`` selects the worker path: ``"transcode"`` (full encode) or
    ``"remux_audio"`` (re-package existing renditions with an attached audio
    track — no video re-encode).
    """
    body: dict[str, Any] = {
        "job_id": job_id,
        "s3_key": s3_key,
        "filename": filename,
        "mode": mode,
        "profiles": ["360p", "720p", "1080p"],
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    now = int(time.time())
    item = {
        "job_id": job_id,
        "body": json.dumps(body),
        "visible_at": now,
        "receive_count": 0,
        "enqueued_at": now,
    }
    try:
        _table().put_item(Item=item)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
            _ensure_table()
            _table().put_item(Item=item)
            return
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to enqueue transcode job",
        ) from exc
    except BotoCoreError as exc:  # pragma: no cover - network error
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to enqueue transcode job",
        ) from exc
