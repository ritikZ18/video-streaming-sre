from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import boto3
import structlog
from app import catalog
from app.config import get_settings
from app.metrics import (
    QUEUE_DEPTH,
    SEGMENTS_UPLOADED,
    TRANSCODE_JOB_DURATION,
    TRANSCODE_JOBS_TOTAL,
    start_metrics_server,
)
from app.profiles import PROFILES, ladder_for
from app.transcoder import (
    JobCancelled,
    can_nvdec_decode,
    encode_audio,
    encode_ladder,
    extract_subtitles_batch,
    extract_thumbnail,
    is_hdr,
    package_cmaf,
    probe_duration,
    probe_media,
)
from boto3.s3.transfer import TransferConfig
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = structlog.get_logger("transcode-worker")


def _format_duration(seconds: float) -> str:
    """Render seconds as a human label, e.g. 3720 -> '1h 2m'."""
    total = round(seconds)
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
    lo, hi = 5, 78
    weights = [i + 1 for i in range(n)]
    total = sum(weights) or 1
    ranges: list[tuple[int, int]] = []
    cur = float(lo)
    for w in weights:
        nxt = cur + (hi - lo) * w / total
        ranges.append((int(cur), int(nxt)))
        cur = nxt
    return ranges


# Fail fast + cap retries so a slow/unhealthy floci can't pile up long-running,
# retrying connections (that feedback loop is what let one bad job peg floci).
_BOTO_CONFIG = Config(
    connect_timeout=5,
    read_timeout=60,
    retries={"max_attempts": 2, "mode": "standard"},
    max_pool_connections=4,
)

# Bounded parallelism for the source download — the boto default of 10 concurrent
# part-downloads against a local emulator is what tipped floci over; 4 is a
# balance between throughput and not overwhelming it.
_DOWNLOAD_CFG = TransferConfig(max_concurrency=4)

# Drop a message after this many receives so a genuinely bad job (e.g. a source
# that never becomes readable) can't retry forever.
_MAX_RECEIVES = 4


def _sqs() -> BaseClient:
    settings = get_settings()
    session = boto3.session.Session(region_name=settings.aws_region)
    return session.client("sqs", endpoint_url=settings.sqs_endpoint_url, config=_BOTO_CONFIG)


def _s3() -> BaseClient:
    settings = get_settings()
    session = boto3.session.Session(region_name=settings.aws_region)
    return session.client("s3", endpoint_url=settings.s3_endpoint_url, config=_BOTO_CONFIG)


def _poll_queue() -> dict[str, Any] | None:
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
        AttributeNames=["ApproximateReceiveCount"],
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
    client.download_file(bucket, key, str(dest), Config=_DOWNLOAD_CFG)


# Streaming MIME types boto3 won't infer on its own.
_CONTENT_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".mpd": "application/dash+xml",
    ".m4s": "video/iso.segment",
    ".mp4": "video/mp4",
    ".jpg": "image/jpeg",
    ".vtt": "text/vtt",
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


def _make_cancel_checker(job_id: str):
    """A cheap should_cancel() the encoder can poll every progress line, while
    the underlying DynamoDB read happens at most once every few seconds."""
    state: dict[str, Any] = {"t": 0.0, "cancelled": False}

    def check() -> bool:
        if state["cancelled"]:
            return True
        now = time.monotonic()
        if now - state["t"] >= 3.0:
            state["t"] = now
            state["cancelled"] = catalog.is_canceled(job_id)
        return state["cancelled"]

    return check


def _delete_prefix(bucket: str, prefix: str) -> None:
    """Best-effort delete of every object under a prefix (partial segments)."""
    client = _s3()
    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/"):
            objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objs:
                client.delete_objects(Bucket=bucket, Delete={"Objects": objs})
    except (BotoCoreError, ClientError):
        pass


def _cleanup_canceled(job_id: str, s3_key: str) -> None:
    """Tear down everything a canceled job left behind: catalog row, source
    upload, and any partially-written HLS/DASH segments."""
    settings = get_settings()
    catalog.delete_row(job_id)
    try:
        _s3().delete_object(Bucket=settings.s3_video_bucket, Key=s3_key)
    except (BotoCoreError, ClientError):
        pass
    _delete_prefix(settings.s3_segments_bucket, job_id)


def _drop_poison_message(message: dict[str, Any], receipt_handle: str, receives: int) -> None:
    """A job that keeps failing (e.g. an unreadable source) is dropped: log it,
    remove its catalog row so it leaves the grid, and delete the SQS message so
    it stops re-driving the queue."""
    TRANSCODE_JOBS_TOTAL.labels(status="failed").inc()
    try:
        body = json.loads(message["Body"])
        job_id = body.get("job_id")
    except (ValueError, KeyError):
        job_id = None
    logger.error("poison_message_dropped", job_id=job_id, receives=receives)
    if job_id:
        catalog.delete_row(job_id)
    _delete_message(receipt_handle)


def process_message(message: dict[str, Any]) -> None:
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
        media = probe_media(input_path)
        base = f"{settings.origin_base_url}/hls/{job_id}"

        # Throttled catalog writer: overall progress % + current stage label.
        pstate: dict[str, Any] = {"t": 0.0, "pct": -1, "stage": None}

        def _emit(pct: int, stage: str) -> None:
            now = time.monotonic()
            changed = pct != pstate["pct"] or stage != pstate["stage"]
            if changed and (now - pstate["t"] >= 1.5 or pct >= 99 or stage != pstate["stage"]):
                pstate["pct"], pstate["stage"], pstate["t"] = pct, stage, now
                catalog.update_progress(job_id, pct, stage=stage)

        # Cooperative cancellation: encoders poll should_cancel() per progress
        # line; _ck() aborts the pipeline between stages if a cancel was flagged.
        should_cancel = _make_cancel_checker(job_id)

        def _ck() -> None:
            if should_cancel():
                raise JobCancelled()

        _emit(4, "download")
        _ck()

        # 1) All video renditions in a SINGLE decode pass (GPU: decode once ->
        # scale_cuda per rendition -> nvenc). The ladder is chosen by the source
        # height, so a 4K/60 source produces up to 2160p (nothing is upscaled).
        _v = media.get("video") or {}
        _w, _h = int(_v.get("width") or 0), int(_v.get("height") or 0)
        # Pick the ladder by the source's WIDTH-class so wide/letterboxed "4K"
        # trailers (e.g. 2560x1350, only 1350 tall) aren't capped at 1080p — a
        # 2560-wide source is 1440p-class. Renditions scale preserving aspect, so
        # nothing is upscaled or distorted.
        source_height = max(_h, round(_w * 9 / 16))
        hdr = is_hdr(media)
        gpu_decodable = can_nvdec_decode(media)
        names = [p.name for p in ladder_for(source_height)]
        lo, hi = 5, 78

        def _cb(p: int) -> None:
            # p is 0-100 of the encode; map onto the 5-78% overall band and pick
            # the checklist step by which fraction of the encode we're in.
            idx = min(len(names) - 1, p * len(names) // 100)
            _emit(int(lo + (hi - lo) * p / 100), names[idx])

        _emit(lo, names[0])
        logger.info(
            "encode_start", job_id=job_id, hdr=hdr,
            gpu_decodable=gpu_decodable, source_height=source_height,
            codec=(media.get("video") or {}).get("codec"),
        )
        # SDR -> one H.264 ladder; HDR -> HEVC(HDR) + H.264(tonemapped) ladders.
        # gpu_decodable=False (AV1 / 10-bit H.264) skips the doomed full-GPU pass.
        # Returns [(codec, [rung paths]), ...].
        video_sets = encode_ladder(
            input_path, renditions_dir, seconds,
            source_height=source_height, hdr=hdr, gpu_decodable=gpu_decodable,
            on_progress=_cb, should_cancel=should_cancel,
        )

        # 2) Every audio track (per language) -> AAC.
        _ck()
        _emit(80, "audio")
        audio_tracks = []
        for a in media["audio"]:
            ap = renditions_dir / f"a_{a['index']}.mp4"
            encode_audio(input_path, ap, a["stream_index"])
            audio_tracks.append({"path": ap, "language": a["language"], "label": a["label"]})

        # 3) Package video (one or two codecs) + all audio into one CMAF set.
        _ck()
        _emit(85, "package")
        manifests = package_cmaf(video_sets, audio_tracks, output_dir)

        # 4) Text subtitles -> sidecar WebVTT, ALL in a single demux pass (image
        # subs are listed, not converted). One pass instead of one-per-track.
        _ck()
        _emit(89, "subtitles")
        subtitle_tracks = []
        for s, vtt in extract_subtitles_batch(input_path, media["subtitles"], output_dir / "subs"):
            subtitle_tracks.append({
                "language": s["language"],
                "label": s["label"],
                "url": f"{base}/subs/{vtt.name}",
                "forced": s["forced"],
            })

        _emit(92, "thumbnail")
        thumb_path = output_dir / "thumbnail.jpg"
        thumb_at = max(1.0, min(seconds * 0.1, 60.0)) if seconds else 3.0
        extract_thumbnail(input_path, thumb_path, thumb_at)

        _emit(95, "upload")
        uploaded = _upload_directory(settings.s3_segments_bucket, job_id, output_dir)
        SEGMENTS_UPLOADED.inc(uploaded)

        manifest_url = f"{base}/{manifests['hls'].name}"
        dash_url = f"{base}/{manifests['dash'].name}"
        thumbnail_url = f"{base}/thumbnail.jpg" if thumb_path.exists() else None
        duration = _format_duration(seconds) if seconds else None

        audio_meta = [{"language": a["language"], "label": a["label"]} for a in audio_tracks]
        media_info = {
            "video": media["video"],
            "audio": audio_meta,
            "subtitles": [{"language": s["language"], "label": s["label"]} for s in subtitle_tracks],
        }
        catalog.mark_ready(
            job_id,
            manifest_url,
            dash_url,
            duration=duration,
            thumbnail_url=thumbnail_url,
            audio_tracks=audio_meta,
            subtitle_tracks=subtitle_tracks,
            media_info=media_info,
        )
        logger.info(
            "manifests_generated",
            job_id=job_id,
            audio=len(audio_meta),
            subs=len(subtitle_tracks),
        )
    except JobCancelled:
        # Cooperative cancel: tear down artifacts and return normally so the
        # SQS message is deleted (not retried). Not counted as a failure.
        TRANSCODE_JOBS_TOTAL.labels(status="canceled").inc()
        logger.info("job_canceled", job_id=job_id)
        _cleanup_canceled(job_id, s3_key)
        return
    except Exception as exc:
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
            receives = int(message.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
            if receives > _MAX_RECEIVES:
                _drop_poison_message(message, receipt_handle, receives)
                continue
            process_message(message)
            _delete_message(receipt_handle)
        except (BotoCoreError, ClientError) as exc:  # pragma: no cover - network
            logger.exception("aws_error", error=str(exc))
            time.sleep(5)
        except Exception as exc:
            logger.exception("worker_error", error=str(exc))
            time.sleep(2)


if __name__ == "__main__":  # pragma: no cover - manual run
    main()
