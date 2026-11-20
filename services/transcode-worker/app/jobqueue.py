"""Durable transcode job queue backed by DynamoDB (dynamodb-local).

Replaces the in-memory SQS emulator. Because dynamodb-local persists to the
``dynamo_data`` volume, queued jobs survive a restart — the loss that the
startup reconciler used to clean up after can no longer happen in the first
place. SQS semantics are reproduced with a per-item visibility lease:

- **enqueue**  -> put_item keyed by job_id (a re-enqueue overwrites, never dupes)
- **receive**  -> find items whose lease has expired (visible_at <= now) and
  claim ONE via a conditional update that bumps the lease + receive_count; the
  condition guarantees a single claimer even with concurrent workers
- **delete**   -> remove the item once the job succeeds/cancels
- a crashed worker's lease simply expires and the job becomes claimable again
"""

from __future__ import annotations

import json
import time
from typing import Any

import boto3
import structlog
from app.config import get_settings
from botocore.exceptions import ClientError

logger = structlog.get_logger()


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


def enqueue(job_id: str, body: dict[str, Any]) -> None:
    """Add (or reset) a job. Keyed by job_id, so re-enqueuing the same job just
    overwrites its entry and makes it immediately claimable — never a duplicate."""
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
        raise


def _claim_once() -> dict[str, Any] | None:
    """Try to lease one due job. Returns an SQS-message-shaped dict or None."""
    settings = get_settings()
    now = int(time.time())
    try:
        resp = _table().scan(
            FilterExpression="visible_at <= :now",
            ExpressionAttributeValues={":now": now},
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
            _ensure_table()
            return None
        raise
    # FIFO-ish: oldest enqueued first.
    items = sorted(resp.get("Items", []), key=lambda i: int(i.get("enqueued_at", 0)))
    lease = settings.queue_visibility_timeout_seconds
    for item in items:
        prev_visible = int(item["visible_at"])
        new_count = int(item.get("receive_count", 0)) + 1
        try:
            _table().update_item(
                Key={"job_id": item["job_id"]},
                UpdateExpression="SET visible_at = :new, receive_count = :c",
                ConditionExpression="visible_at = :prev AND attribute_exists(job_id)",
                ExpressionAttributeValues={
                    ":new": now + lease,
                    ":prev": prev_visible,
                    ":c": new_count,
                },
            )
        except ClientError as exc:
            # Lost the race (another claimer moved the lease) — try the next item.
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                continue
            raise
        return {
            "Body": item["body"],
            "ReceiptHandle": item["job_id"],
            "Attributes": {"ApproximateReceiveCount": str(new_count)},
        }
    return None


def receive(wait_seconds: int = 20, poll_interval: float = 1.0) -> dict[str, Any] | None:
    """Long-poll for one job for up to ``wait_seconds`` (mirrors SQS long polling)."""
    deadline = time.monotonic() + max(0, wait_seconds)
    while True:
        msg = _claim_once()
        if msg is not None:
            return msg
        if time.monotonic() >= deadline:
            return None
        time.sleep(poll_interval)


def delete(receipt_handle: str) -> None:
    """Remove a finished job (receipt_handle is the job_id)."""
    try:
        _table().delete_item(Key={"job_id": receipt_handle})
    except ClientError as exc:  # pragma: no cover - best effort
        logger.warning("jobqueue_delete_failed", job_id=receipt_handle, error=str(exc))


def depth() -> int:
    """Approximate number of jobs currently in the queue (for the QUEUE_DEPTH gauge)."""
    try:
        return int(_table().scan(Select="COUNT").get("Count", 0))
    except ClientError:
        return 0
