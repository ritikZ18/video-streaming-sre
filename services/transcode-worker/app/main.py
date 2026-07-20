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
from app.profiles import PROFILES
from app.transcoder import (
    encode_rendition,
    extract_thumbnail,
    has_audio_stream,
    package_cmaf,
    probe_duration,
)


logger = structlog.get_logger("transcode-worker")


def _format_duration(seconds: float) -> str:
    """Render seconds as a human label, e.g. 3720 -> '1h 2m'."""
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _rendition_ranges(n: int) -> list[tuple[int, int]]:
    """Overall-% window for each rendition (renditions occupy 5-85%; later,
    larger renditions get a bigger slice)."""
    lo, hi = 5, 85
    weights = [i + 1 for i in range(n)]
    total = sum(weights) or 1
    ranges: list[tuple[int, int]] = []
    cur = float(lo)
    for w in weights:
        nxt = cur + (hi - lo) * w / total
        ranges.append((int(cur), int(nxt)))
        cur = nxt
    return ranges


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
    ".jpg": "image/jpeg",
}


def _upload_directory(bucket: str, prefix: str, directory: Path) -> int:
    client = _s3()
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)
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

        renditions_dir = tmpdir / "renditions"
        renditions_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        seconds = probe_duration(input_path) or 0.0
        audio = has_audio_stream(input_path)

        # Throttled catalog writer: overall progress % + current stage label.
        pstate: Dict[str, Any] = {"t": 0.0, "pct": -1, "stage": None}

        def _emit(pct: int, stage: str) -> None:
            now = time.monotonic()
            changed = pct != pstate["pct"] or stage != pstate["stage"]
            if changed and (now - pstate["t"] >= 1.5 or pct >= 99 or stage != pstate["stage"]):
                pstate["pct"], pstate["stage"], pstate["t"] = pct, stage, now
                catalog.update_progress(job_id, pct, stage=stage)

        _emit(4, "download")

        # Encode each rendition one-by-one; each reports its own stage + progress.
        ranges = _rendition_ranges(len(PROFILES))
        rendition_paths = []
        for i, profile in enumerate(PROFILES):
            lo, hi = ranges[i]
            out = renditions_dir / f"rendition_{profile.name}.mp4"
            _emit(lo, profile.name)

            def _cb(p: int, lo=lo, hi=hi, name=profile.name) -> None:
                _emit(int(lo + (hi - lo) * p / 100), name)

            encode_rendition(input_path, out, profile, audio and i == 0, seconds, on_progress=_cb)
            rendition_paths.append(out)

        # Package the renditions into one CMAF set (HLS + DASH), stream-copy.
        _emit(87, "package")
        manifests = package_cmaf(rendition_paths, output_dir, audio)

        _emit(91, "thumbnail")
        thumb_path = output_dir / "thumbnail.jpg"
        thumb_at = max(1.0, min(seconds * 0.1, 60.0)) if seconds else 3.0
        extract_thumbnail(input_path, thumb_path, thumb_at)

        _emit(94, "upload")
        uploaded = _upload_directory(settings.s3_segments_bucket, job_id, output_dir)
        SEGMENTS_UPLOADED.inc(uploaded)

        base = f"{settings.origin_base_url}/hls/{job_id}"
        manifest_url = f"{base}/{manifests['hls'].name}"
        dash_url = f"{base}/{manifests['dash'].name}"
        thumbnail_url = f"{base}/thumbnail.jpg" if thumb_path.exists() else None
        duration = _format_duration(seconds) if seconds else None
        catalog.mark_ready(
            job_id,
            manifest_url,
            dash_url,
            duration=duration,
            thumbnail_url=thumbnail_url,
        )
        logger.info("manifests_generated", job_id=job_id, hls=manifest_url, dash=dash_url)
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

