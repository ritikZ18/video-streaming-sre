from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, status

from app.config import get_settings


def _client() -> BaseClient:
    settings = get_settings()
    session = boto3.session.Session(region_name=settings.aws_region)
    return session.client("sqs", endpoint_url=settings.sqs_endpoint_url)


def enqueue_transcode_job(job_id: str, s3_key: str, filename: str) -> None:
    """Send a transcode job message to SQS."""
    settings = get_settings()
    if not settings.sqs_transcode_queue_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transcode queue URL is not configured",
        )

    payload: dict[str, Any] = {
        "job_id": job_id,
        "s3_key": s3_key,
        "filename": filename,
        "profiles": ["360p", "720p", "1080p"],
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    body = json.dumps(payload)
    client = _client()

    try:
        client.send_message(
            QueueUrl=settings.sqs_transcode_queue_url,
            MessageBody=body,
        )
    except ClientError as exc:  # pragma: no cover - network error
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"AWS.SimpleQueueService.NonExistentQueue"}:
            # Lazily create queue in local dev and retry once. A long
            # VisibilityTimeout keeps an in-flight transcode (minutes long) from
            # being redelivered to another worker while it is still processing.
            queue_name = settings.sqs_transcode_queue_url.rstrip("/").split("/")[-1]
            client.create_queue(
                QueueName=queue_name,
                Attributes={"VisibilityTimeout": "1800"},
            )
            client.send_message(
                QueueUrl=settings.sqs_transcode_queue_url,
                MessageBody=body,
            )
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


