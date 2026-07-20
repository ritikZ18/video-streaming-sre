from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

import boto3
import structlog
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings
from app.metrics import (
    QUEUE_DEPTH,
    SEGMENTS_UPLOADED,
    TRANSCODE_JOBS_TOTAL,
    TRANSCODE_JOB_DURATION,
    start_metrics_server,
)
from app import catalog
from app.transcoder import transcode_to_cmaf


logger = structlog.get_logger("transcode-worker")


def _sqs() -> BaseClient:
    settings = get_settings()
    session = boto3.session.Session(region_name=settings.aws_region)
    return session.client("sqs", endpoint_url=settings.sqs_endpoint_url)


def _s3() -> BaseClient:
    settings = get_settings()
    session = boto3.session.Session(region_name=settings.aws_region)
    return session.client("s3", endpoint_url=settings.s3_endpoint_url)


def _poll_queue() -> Dict[str, Any] | None:
    settings = get_settings()
    if not settings.sqs_transcode_queue_url:
        logger.warning("sqs_transcode_queue_url_not_configured")
        time.sleep(5)
        return None

    client = _sqs()
    response = client.receive_message(
        QueueUrl=settings.sqs_transcode_queue_url,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=20,
    )
    messages = response.get("Messages", [])
    QUEUE_DEPTH.set(len(messages))
    if not messages:
        return None
    return messages[0]


def _delete_message(receipt_handle: str) -> None:
    settings = get_settings()
    client = _sqs()
    client.delete_message(
        QueueUrl=settings.sqs_transcode_queue_url,
        ReceiptHandle=receipt_handle,
    )


def _download_input(bucket: str, key: str, dest: Path) -> None:
    client = _s3()
    client.download_file(bucket, key, str(dest))


# Streaming MIME types boto3 won't infer on its own.
_CONTENT_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".mpd": "application/dash+xml",
    ".m4s": "video/iso.segment",
    ".mp4": "video/mp4",
}


def _upload_directory(bucket: str, prefix: str, directory: Path) -> int:
    client = _s3()
    count = 0
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(directory)
        key = f"{prefix}/{rel.as_posix()}"
        content_type = _CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
        client.upload_file(
            str(path),
            bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        count += 1
    return count


def process_message(message: Dict[str, Any]) -> None:
    """Process a single SQS message containing a transcode job."""
    settings = get_settings()
    body = json.loads(message["Body"])
    job_id = body["job_id"]
    s3_key = body["s3_key"]

    logger.info("job_start", job_id=job_id, s3_key=s3_key)

    started = time.monotonic()
    tmpdir = Path(tempfile.mkdtemp(prefix=f"streamsre-{job_id}-"))
    input_path = tmpdir / "input"
    output_dir = tmpdir / "output"

    try:
        _download_input(settings.s3_video_bucket, s3_key, input_path)
        manifests = transcode_to_cmaf(input_path, output_dir)
        uploaded = _upload_directory(settings.s3_segments_bucket, job_id, output_dir)
        SEGMENTS_UPLOADED.inc(uploaded)

        manifest_url = f"{settings.origin_base_url}/hls/{job_id}/{manifests['hls'].name}"
        dash_url = f"{settings.origin_base_url}/hls/{job_id}/{manifests['dash'].name}"
        catalog.mark_ready(job_id, manifest_url, dash_url)
        logger.info(
            "manifests_generated",
            job_id=job_id,
            hls=manifest_url,
            dash=dash_url,
        )
    except Exception as exc:  # noqa: BLE001
        TRANSCODE_JOBS_TOTAL.labels(status="failed").inc()
        logger.exception("job_failed", job_id=job_id, error=str(exc))
        raise
    else:
        TRANSCODE_JOBS_TOTAL.labels(status="success").inc()
        duration = time.monotonic() - started
        TRANSCODE_JOB_DURATION.observe(duration)
        logger.info("job_complete", job_id=job_id, duration_seconds=duration)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main() -> None:
    """Entry point: poll SQS and process jobs indefinitely."""
    start_metrics_server(9100)
    logger.info("worker_started", pid=os.getpid())

    while True:
        try:
            message = _poll_queue()
            if not message:
                continue
            receipt_handle = message["ReceiptHandle"]
            process_message(message)
            _delete_message(receipt_handle)
        except (BotoCoreError, ClientError) as exc:  # pragma: no cover - network
            logger.exception("aws_error", error=str(exc))
            time.sleep(5)
        except Exception as exc:  # noqa: BLE001
            logger.exception("worker_error", error=str(exc))
            time.sleep(2)


if __name__ == "__main__":  # pragma: no cover - manual run
    main()

