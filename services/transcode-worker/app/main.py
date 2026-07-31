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
from app import catalog, jobqueue
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
    encode_external_audio,
    encode_ladder,
    extract_subtitles_batch,
    extract_thumbnail,
    is_hdr,
    package_cmaf,
    probe_duration,
    probe_media,
    reassemble_rendition,
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


def _s3() -> BaseClient:
    settings = get_settings()
    session = boto3.session.Session(region_name=settings.aws_region)
    return session.client("s3", endpoint_url=settings.s3_endpoint_url, config=_BOTO_CONFIG)


def _object_exists(bucket: str, key: str) -> bool:
    try:
        _s3().head_object(Bucket=bucket, Key=key)
        return True
    except (BotoCoreError, ClientError):
        return False


def _first_key(bucket: str, prefix: str) -> str | None:
    """First object key under a prefix (a job's stored source), or None."""
    try:
        resp = _s3().list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=1)
        items = resp.get("Contents", [])
        return items[0]["Key"] if items else None
    except (BotoCoreError, ClientError):
        return None


def _find_external_audio(job_id: str) -> str | None:
    """Admin-attached external audio for a silent title (stored beside its
    segments as ``{job_id}/external_audio.<ext>``), or None."""
    settings = get_settings()
    return _first_key(settings.s3_segments_bucket, f"{job_id}/external_audio")


def _enqueue_job(job_id: str, s3_key: str, filename: str) -> None:
    jobqueue.enqueue(
        job_id,
        {
            "job_id": job_id,
            "s3_key": s3_key,
            "filename": filename,
            "profiles": ["360p", "720p", "1080p"],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )


def _reconcile_orphans() -> None:
    """Startup self-heal for jobs left mid-flight by a crash/restart.

    The queue is now durable (DynamoDB), so jobs are no longer lost on restart —
    but a job that was in-flight when the worker died still shows status
    'processing' with a held lease that would only free after the visibility
    timeout. This sweep speeds recovery: for each 'processing' row, if its
    segments already finished, mark it ready; else, if the source is still
    stored, re-enqueue it immediately (overwriting any stale lease/entry).
    Best-effort — a failure here must never stop the worker's poll loop.
    """
    settings = get_settings()
    ids = catalog.list_processing_ids()
    if not ids:
        return
    logger.info("reconcile_start", processing=len(ids))
    recovered = requeued = skipped = 0
    for job_id in ids:
        try:
            base = f"{settings.origin_base_url}/hls/{job_id}"
            # Finished but never marked ready (worker died between upload + mark).
            if _object_exists(settings.s3_segments_bucket, f"{job_id}/master.m3u8"):
                hdr = (
                    f"{base}/master_hevc.m3u8"
                    if _object_exists(settings.s3_segments_bucket, f"{job_id}/master_hevc.m3u8")
                    else None
                )
                catalog.mark_ready(
                    job_id, f"{base}/master.m3u8", f"{base}/manifest.mpd",
                    hdr_manifest_url=hdr,
                )
                recovered += 1
                continue
            # Not finished — re-enqueue if the original source is still stored.
            src = _first_key(settings.s3_video_bucket, f"{job_id}/")
            if not src:
                skipped += 1
                logger.warning("reconcile_no_source", job_id=job_id)
                continue
            filename = src.split("/", 1)[1] if "/" in src else src
            # A re-enqueue is a fresh start: drop any stale cancel flag first, or the
            # worker would immediately cancel this job and delete its source.
            catalog.clear_cancel(job_id)
            _enqueue_job(job_id, src, filename)
            requeued += 1
            logger.info("reconcile_requeued", job_id=job_id)
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the sweep
            logger.warning("reconcile_row_failed", job_id=job_id, error=str(exc))
    logger.info("reconcile_done", recovered=recovered, requeued=requeued, skipped=skipped)


def _poll_queue() -> dict[str, Any] | None:
    """Long-poll the durable DynamoDB queue for one leased job (SQS-shaped dict)."""
    message = jobqueue.receive(wait_seconds=20)
    QUEUE_DEPTH.set(jobqueue.depth())
    return message


def _delete_message(receipt_handle: str) -> None:
    jobqueue.delete(receipt_handle)


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


def _download_prefix(bucket: str, prefix: str, dest: Path) -> int:
    """Download every object under ``prefix`` into ``dest``, preserving the key
    suffix. Returns the number of files fetched."""
    client = _s3()
    count = 0
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            rel = obj["Key"][len(prefix):].lstrip("/")
            if not rel:
                continue
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket, obj["Key"], str(out), Config=_DOWNLOAD_CFG)
            count += 1
    return count


def _persist_renditions(job_id: str, video_sets: list[tuple[str, list[Path]]]) -> None:
    """Store the encoded rendition MP4s beside the segments (``{job_id}/renditions/``)
    so a later audio-attach can re-package them WITHOUT re-encoding the video (the
    fast remux path). Best-effort — never fails the transcode."""
    settings = get_settings()
    try:
        client = _s3()
        for _codec, paths in video_sets:
            for p in paths:
                client.upload_file(
                    str(p), settings.s3_segments_bucket,
                    f"{job_id}/renditions/{p.name}",
                    ExtraArgs={"ContentType": "video/mp4"},
                )
    except (BotoCoreError, ClientError) as exc:
        logger.warning("persist_renditions_failed", job_id=job_id, error=str(exc))


def _load_persisted_renditions(job_id: str, tmpdir: Path) -> list[tuple[str, list[Path]]] | None:
    """Rendition MP4s persisted at ``{job_id}/renditions/`` (fastest, known-good),
    grouped by codec. None if none were stored (a pre-improvement title)."""
    settings = get_settings()
    rdir = tmpdir / "renditions"
    rdir.mkdir(parents=True, exist_ok=True)
    if not _download_prefix(settings.s3_segments_bucket, f"{job_id}/renditions/", rdir):
        return None
    by_codec: dict[str, list[Path]] = {}
    for p in sorted(rdir.glob("v_*.mp4")):
        parts = p.stem.split("_")  # v, {codec}, {name}
        codec = parts[1] if len(parts) >= 3 else "h264"
        by_codec.setdefault(codec, []).append(p)
    video_sets = [(c, by_codec[c]) for c in ("h264", "hevc") if c in by_codec]
    return video_sets or None


def _video_variants(master: Path) -> list[tuple[str, str]]:
    """Parse an HLS master playlist -> [(codec, media_playlist_name), ...] for the
    VIDEO variants (``#EXT-X-STREAM-INF``; audio ``#EXT-X-MEDIA`` is ignored)."""
    out: list[tuple[str, str]] = []
    lines = master.read_text(encoding="utf-8").splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("#EXT-X-STREAM-INF"):
            uri = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if uri and not uri.startswith("#"):
                codec = "hevc" if ("hvc1" in ln or "hev1" in ln) else "h264"
                out.append((codec, uri))
    return out


def _reassemble_from_segments(job_id: str, tmpdir: Path) -> list[tuple[str, list[Path]]] | None:
    """Rebuild the renditions from the ALREADY-PUBLISHED HLS segments via stream
    copy (no re-encode), so audio remux works even for titles encoded before
    renditions were persisted. Returns None if anything looks off, so the caller
    safely falls back to a full transcode."""
    settings = get_settings()
    dl = tmpdir / "published"
    dl.mkdir(parents=True, exist_ok=True)
    if not _download_prefix(settings.s3_segments_bucket, f"{job_id}/", dl):
        return None
    master = dl / "master.m3u8"
    if not master.exists():
        return None
    variants = _video_variants(master)
    hevc_master = dl / "master_hevc.m3u8"
    if hevc_master.exists():
        variants += _video_variants(hevc_master)
    if not variants:
        return None
    rdir = tmpdir / "reasm"
    rdir.mkdir(parents=True, exist_ok=True)
    by_codec: dict[str, list[Path]] = {}
    for i, (codec, name) in enumerate(variants):
        pl = dl / name
        if not pl.exists():
            return None
        out = rdir / f"v_{codec}_{i}.mp4"
        if not reassemble_rendition(pl, out):
            logger.warning("reassemble_failed", job_id=job_id, variant=name)
            return None
        by_codec.setdefault(codec, []).append(out)
    video_sets = [(c, by_codec[c]) for c in ("h264", "hevc") if c in by_codec]
    return video_sets or None


def _remux_audio(job_id: str, tmpdir: Path) -> bool:
    """Fast audio-attach — mux the attached audio into the EXISTING encoded video
    with NO re-encode. Uses persisted renditions when available, else rebuilds them
    from the published segments (stream copy). Returns False if neither the audio
    nor the renditions are available, so the caller falls back to a full transcode."""
    settings = get_settings()
    ext_key = _find_external_audio(job_id)
    if not ext_key:
        logger.info("remux_skip_no_external_audio", job_id=job_id)
        return False

    video_sets = _load_persisted_renditions(job_id, tmpdir)
    source = "persisted"
    if not video_sets:
        video_sets = _reassemble_from_segments(job_id, tmpdir)
        source = "reassembled"
    if not video_sets:
        logger.info("remux_skip_no_renditions", job_id=job_id)
        return False

    catalog.update_progress(job_id, 45, stage="audio")
    dur = probe_duration(video_sets[0][1][0]) or 0.0
    audio_src = tmpdir / "external_audio"
    _download_input(settings.s3_segments_bucket, ext_key, audio_src)
    ap = tmpdir / "a_ext.mp4"
    encode_external_audio(audio_src, ap, dur)
    audio_tracks = [{"path": ap, "language": "und", "label": "Audio"}]

    catalog.update_progress(job_id, 75, stage="package")
    output_dir = tmpdir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifests = package_cmaf(video_sets, audio_tracks, output_dir)

    catalog.update_progress(job_id, 92, stage="upload")
    uploaded = _upload_directory(settings.s3_segments_bucket, job_id, output_dir)
    SEGMENTS_UPLOADED.inc(uploaded)

    base = f"{settings.origin_base_url}/hls/{job_id}"
    hdr_url = f"{base}/{manifests['hls_hevc'].name}" if manifests.get("hls_hevc") else None
    catalog.mark_ready(
        job_id,
        f"{base}/{manifests['hls'].name}",
        f"{base}/{manifests['dash'].name}",
        hdr_manifest_url=hdr_url,
        audio_tracks=[{"language": "und", "label": "Audio"}],
    )
    logger.info("audio_remux_complete", job_id=job_id, source=source, video_sets=len(video_sets))
    return True


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
    mode = body.get("mode", "transcode")

    logger.info("job_start", job_id=job_id, s3_key=s3_key, mode=mode)

    started = time.monotonic()
    tmpdir = Path(tempfile.mkdtemp(prefix=f"streamsre-{job_id}-"))
    input_path = tmpdir / "input"
    output_dir = tmpdir / "output"

    try:
        # Fast path: attach-audio re-packages the persisted renditions with the
        # new audio (no video re-encode). ANY failure — or missing renditions —
        # falls through to a full transcode below, so it's always safe.
        if mode == "remux_audio":
            remuxed = False
            try:
                remuxed = _remux_audio(job_id, tmpdir)
            except JobCancelled:
                raise
            except Exception as exc:  # noqa: BLE001 - fall back to full transcode
                logger.warning("remux_failed_falling_back", job_id=job_id, error=str(exc)[:300])
            if remuxed:
                TRANSCODE_JOBS_TOTAL.labels(status="success").inc()
                TRANSCODE_JOB_DURATION.observe(time.monotonic() - started)
                logger.info(
                    "job_complete", job_id=job_id, mode="remux_audio",
                    duration_seconds=time.monotonic() - started,
                )
                return
            logger.info("remux_fallback_full_transcode", job_id=job_id)

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

        # Persist the encoded renditions so a later audio-attach can re-package
        # them WITHOUT re-encoding the video (the fast _remux_audio path).
        _persist_renditions(job_id, video_sets)

        # 2) Every audio track (per language) -> AAC. If the source is SILENT and
        # an admin attached an external track, mux that in instead.
        _ck()
        _emit(80, "audio")
        audio_tracks = []
        if media["audio"]:
            for a in media["audio"]:
                ap = renditions_dir / f"a_{a['index']}.mp4"
                encode_audio(input_path, ap, a["stream_index"])
                audio_tracks.append({"path": ap, "language": a["language"], "label": a["label"]})
        else:
            ext_key = _find_external_audio(job_id)
            if ext_key:
                ext_src = tmpdir / "external_audio"
                _download_input(settings.s3_segments_bucket, ext_key, ext_src)
                ap = renditions_dir / "a_ext.mp4"
                encode_external_audio(ext_src, ap, seconds)
                audio_tracks.append({"path": ap, "language": "und", "label": "Audio"})
                logger.info("external_audio_muxed", job_id=job_id, key=ext_key)

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
        # HDR videos also get a separate HEVC master; the player switches to it only
        # when the browser can actually decode HEVC. None for SDR.
        hdr_manifest_url = (
            f"{base}/{manifests['hls_hevc'].name}" if manifests.get("hls_hevc") else None
        )
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
            hdr_manifest_url=hdr_manifest_url,
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

    # Recover jobs orphaned by an ephemeral-queue restart before polling.
    try:
        _reconcile_orphans()
    except Exception as exc:  # noqa: BLE001 - reconcile must never block startup
        logger.warning("reconcile_failed", error=str(exc))

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
