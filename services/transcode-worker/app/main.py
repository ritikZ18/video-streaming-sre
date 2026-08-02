from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

import boto3
import structlog
from app import catalog, jobqueue
from app.config import get_settings
from app.metrics import (
    INTERP_DURATION,
    INTERP_JOBS_TOTAL,
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
    generate_storyboard,
    is_hdr,
    package_cmaf,
    probe_duration,
    probe_fps,
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


def _discover_extract_tasks(media: dict[str, Any]) -> list[dict[str, Any]]:
    """The audio + subtitle tracks found in the source, as a checklist the admin
    UI renders live (VLC-style). Audio always extracts; text subtitles convert to
    WebVTT; image-based subtitles (PGS/VobSub) can't be shown in-browser, so they
    start marked 'image' rather than sitting forever 'pending'. Order matches the
    probe (all audio first, then subtitles) so the worker can flip entries done by
    index as each track lands."""
    tasks: list[dict[str, Any]] = []
    for a in media.get("audio") or []:
        tasks.append({
            "kind": "audio",
            "label": a.get("label") or "Audio",
            "lang": a.get("language") or "und",
            "codec": a.get("codec"),
            "channels": a.get("channels"),
            "state": "pending",
        })
    for s in media.get("subtitles") or []:
        tasks.append({
            "kind": "subtitle",
            "label": s.get("label") or "Subtitle",
            "lang": s.get("language") or "und",
            "codec": s.get("codec"),
            "forced": bool(s.get("forced")),
            "state": "pending" if s.get("text") else "image",
        })
    return tasks


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
    upload, and any partially-written HLS/DASH segments.

    The source is deleted ONLY when it lives under this job's own prefix — a copy
    / smoothing job re-uses another title's source object, and deleting that would
    destroy the original."""
    settings = get_settings()
    catalog.delete_row(job_id)
    if s3_key.startswith(f"{job_id}/"):
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
        is_variant = bool(body.get("interp_variant"))
    except (ValueError, KeyError):
        job_id = None
        is_variant = False
    logger.error("poison_message_dropped", job_id=job_id, receives=receives, variant=is_variant)
    if job_id:
        if is_variant:
            # A smoothing variant shares the ORIGINAL's id — never delete that row;
            # just record the failure on its interp state.
            catalog.update_interp(job_id, "failed", detail="smoothing failed repeatedly")
        else:
            catalog.delete_row(job_id)
    _delete_message(receipt_handle)


def _interp_skip_reason(
    settings: Any, height: int, duration: float, src_fps: float, target: int, hdr: bool
) -> str | None:
    """Return why interpolation should be skipped for this source, or None to
    proceed. Mirrors the sidecar's guardrails (defence in depth)."""
    if hdr:
        return "HDR source (interpolation would drop HDR)"
    if height and height > settings.interp_max_height:
        return f"height {height} > {settings.interp_max_height}"
    if duration and duration > settings.interp_max_duration_seconds:
        return f"duration {duration:.0f}s > {settings.interp_max_duration_seconds}s"
    if src_fps and src_fps >= settings.interp_max_source_fps:
        return f"source already {src_fps:.0f}fps (>= {settings.interp_max_source_fps})"
    if src_fps and target <= src_fps:
        return f"target {target} <= source {src_fps:.0f}fps"
    if target > settings.interp_max_target_fps:
        return f"target {target} > {settings.interp_max_target_fps}"
    return None


def _call_io_framer(
    job_id: str, s3_key: str, target_fps: int, out_key: str, emit,
    interp_height: int | None = None,
) -> None:
    """POST to the I/O Framer sidecar and poll to completion. Raises on failure,
    timeout, or an unreachable sidecar so the caller can fall back to native fps.

    ``interp_height`` (optional) asks the sidecar to interpolate at that reduced
    height — used for the "downscaled copy" (e.g. a 4K source smoothed at 1080p)."""
    settings = get_settings()
    base = settings.interp_service_url.rstrip("/")
    body: dict[str, Any] = {
        "movie_id": job_id,
        "target_fps": target_fps,
        "source": {"s3_bucket": settings.s3_video_bucket, "s3_key": s3_key},
        "output": {"s3_bucket": settings.s3_video_bucket, "s3_key": out_key},
    }
    if interp_height:
        body["options"] = {"max_height": interp_height}
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base}/interpolate", data=payload,
        headers={"content-type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        interp_job = json.loads(resp.read().decode())["job_id"]

    deadline = time.monotonic() + settings.interp_timeout_seconds
    while time.monotonic() < deadline:
        with urllib.request.urlopen(f"{base}/interpolate/{interp_job}", timeout=30) as resp:
            st = json.loads(resp.read().decode())
        status = st.get("status")
        if status == "done":
            return
        if status == "failed":
            raise RuntimeError(f"io-framer: {st.get('detail') or 'failed'}")
        # Surface the sidecar's own 0-100 + stage on the row (for the live % / ETA
        # in the UI), and fold it into a small slice (5-18%) of the overall bar.
        prog = int(st.get("progress") or 0)
        catalog.update_interp_progress(job_id, prog, st.get("stage") or "interpolating")
        emit(min(18, 5 + int(0.13 * prog)), "interpolating")
        time.sleep(3)
    raise RuntimeError("io-framer timed out")


def _maybe_interpolate(
    job_id: str,
    body: dict[str, Any],
    input_path: Path,
    media: dict[str, Any],
    seconds: float,
    tmpdir: Path,
    emit,
) -> tuple[Path, dict[str, Any], bool]:
    """If interpolation was requested and passes the guardrails, produce a
    higher-fps mezzanine via the I/O Framer sidecar and return it as the VIDEO
    source (audio/subtitles/thumbnail stay sourced from the original, which the
    mezzanine does not carry). Never raises — records interp_status and falls back
    to the native source on any problem.

    Returns ``(video_input, video_media, interp_ok)``.
    """
    settings = get_settings()
    if not body.get("interp"):
        return input_path, media, False
    if not settings.interp_enabled:
        catalog.update_interp(job_id, "skipped", detail="interpolation disabled on worker")
        INTERP_JOBS_TOTAL.labels(result="skipped").inc()
        return input_path, media, False

    target = int(body.get("interp_target_fps") or settings.interp_max_target_fps)
    height = int((media.get("video") or {}).get("height") or 0)
    src_fps = probe_fps(input_path)
    reason = _interp_skip_reason(settings, height, seconds, src_fps, target, is_hdr(media))
    if reason:
        logger.info("interp_skipped", job_id=job_id, reason=reason, target_fps=target)
        catalog.update_interp(job_id, "skipped", detail=reason)
        INTERP_JOBS_TOTAL.labels(result="skipped").inc()
        return input_path, media, False

    catalog.update_interp(job_id, "processing")
    # Anchor the elapsed/ETA clock for the UI at the start of this pass.
    catalog.update_interp_progress(job_id, 0, "starting", started_at=time.time())
    logger.info("interp_start", job_id=job_id, target_fps=target, source_fps=round(src_fps, 2))
    mezz_key = f"{job_id}/interpolated.mp4"
    interp_height = body.get("interp_height")
    interp_started = time.monotonic()
    try:
        _call_io_framer(job_id, body["s3_key"], target, mezz_key, emit, interp_height=interp_height)
        mezz_path = tmpdir / "mezzanine.mp4"
        _download_input(settings.s3_video_bucket, mezz_key, mezz_path)
        video_media = probe_media(mezz_path)
        INTERP_JOBS_TOTAL.labels(result="done").inc()
        INTERP_DURATION.observe(time.monotonic() - interp_started)
        logger.info("interp_done", job_id=job_id, target_fps=target)
        return mezz_path, video_media, True
    except Exception as exc:  # noqa: BLE001 - fall back to the native source
        logger.warning("interp_failed_falling_back", job_id=job_id, error=str(exc)[:300])
        catalog.update_interp(job_id, "failed", detail=str(exc)[:200])
        INTERP_JOBS_TOTAL.labels(result="failed").inc()
        return input_path, media, False
    finally:
        # The S3 mezzanine is just transport between the sidecar and us; drop it
        # once local (a no-op if it was never produced).
        try:
            _s3().delete_object(Bucket=settings.s3_video_bucket, Key=mezz_key)
        except Exception:  # noqa: BLE001
            pass


def process_message(message: dict[str, Any]) -> None:
    """Process a single SQS message containing a transcode job."""
    settings = get_settings()
    body = json.loads(message["Body"])
    job_id = body["job_id"]
    s3_key = body["s3_key"]
    mode = body.get("mode", "transcode")
    # A smoothing VARIANT re-uses the title's own id but publishes a separate,
    # non-destructive interpolated ladder under {id}/interp/ (the original {id}/
    # ladder is left untouched); the player exposes it as a Smooth toggle.
    is_variant = bool(body.get("interp_variant"))
    out_prefix = f"{job_id}/interp" if is_variant else job_id

    logger.info("job_start", job_id=job_id, s3_key=s3_key, mode=mode, variant=is_variant)

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
        base = f"{settings.origin_base_url}/hls/{out_prefix}"

        # Publish the audio/subtitle extraction checklist up front (before the long
        # encode) so the admin panel shows a live 'todo list' of tracks for the whole
        # job, not just a flash at the end. Each entry flips to done as its track
        # lands. A smoothing variant adds no tracks, so it skips the checklist.
        extract_tasks = [] if is_variant else _discover_extract_tasks(media)
        if extract_tasks:
            catalog.set_extract_tasks(job_id, extract_tasks)

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

        # Frame interpolation (I/O Framer): if requested + guardrails pass, swap in
        # a higher-fps mezzanine as the VIDEO source. Audio, subtitles and the
        # thumbnail stay sourced from the original (the mezzanine carries neither).
        # Never raises — falls back to the native source and records interp_status.
        video_input, video_media, interp_ok = _maybe_interpolate(
            job_id, body, input_path, media, seconds, tmpdir, _emit
        )
        _ck()

        # A smoothing variant exists only to add an interpolated rendition. If the
        # guardrails skipped interpolation (already high-fps / too long / HDR …),
        # there is nothing to add — _maybe_interpolate already recorded the reason
        # on interp_status, so just stop instead of publishing a duplicate ladder.
        if is_variant and not interp_ok:
            logger.info("interp_variant_no_op", job_id=job_id)
            return

        # 1) All video renditions in a SINGLE decode pass (GPU: decode once ->
        # scale_cuda per rendition -> nvenc). The ladder is chosen by the source
        # height, so a 4K/60 source produces up to 2160p (nothing is upscaled).
        _v = video_media.get("video") or {}
        _w, _h = int(_v.get("width") or 0), int(_v.get("height") or 0)
        # Pick the ladder by the source's WIDTH-class so wide/letterboxed "4K"
        # trailers (e.g. 2560x1350, only 1350 tall) aren't capped at 1080p — a
        # 2560-wide source is 1440p-class. Renditions scale preserving aspect, so
        # nothing is upscaled or distorted.
        source_height = max(_h, round(_w * 9 / 16))
        hdr = is_hdr(video_media)
        gpu_decodable = can_nvdec_decode(video_media)
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
            video_input, renditions_dir, seconds,
            source_height=source_height, hdr=hdr, gpu_decodable=gpu_decodable,
            on_progress=_cb, should_cancel=should_cancel,
        )

        # Persist the encoded renditions so a later audio-attach can re-package
        # them WITHOUT re-encoding the video (the fast _remux_audio path). Skipped
        # for a smoothing variant — it shares the title's id, so persisting would
        # overwrite the ORIGINAL's renditions with the interpolated ones.
        if not is_variant:
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
                # Flip this audio track's checklist entry to done as it lands (audio
                # entries come first in extract_tasks, in probe order).
                if a["index"] < len(extract_tasks):
                    extract_tasks[a["index"]]["state"] = "done"
                    catalog.set_extract_tasks(job_id, extract_tasks)
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

        # A smoothing VARIANT publishes only the interpolated ladder (+ its audio)
        # under {id}/interp/ and links it onto the title via interp_manifest_url,
        # leaving the original manifest/status untouched. Thumbnail / subtitles /
        # storyboard all come from the original the player can toggle back to.
        if is_variant:
            _emit(95, "upload")
            uploaded = _upload_directory(settings.s3_segments_bucket, out_prefix, output_dir)
            SEGMENTS_UPLOADED.inc(uploaded)
            variant_fps = int(body.get("interp_target_fps") or 0)
            catalog.set_interp_variant(
                job_id,
                f"{base}/{manifests['hls'].name}",
                f"{base}/{manifests['dash'].name}",
                variant_fps,
            )
            logger.info("interp_variant_published", job_id=job_id, fps=variant_fps)
            return

        # 4) Text subtitles -> sidecar WebVTT, ALL in a single demux pass (image
        # subs are listed, not converted). One pass instead of one-per-track.
        _ck()
        _emit(89, "subtitles")
        subtitle_tracks = []
        extracted_sub_streams: set[int] = set()
        _audio_count = len(media["audio"])
        for s, vtt in extract_subtitles_batch(input_path, media["subtitles"], output_dir / "subs"):
            subtitle_tracks.append({
                "language": s["language"],
                "label": s["label"],
                "url": f"{base}/subs/{vtt.name}",
                "forced": s["forced"],
            })
            extracted_sub_streams.add(s["stream_index"])
            # Flip the matching checklist entry done (subtitles follow audio in order).
            _ti = _audio_count + s["index"]
            if _ti < len(extract_tasks):
                extract_tasks[_ti]["state"] = "done"
        if extract_tasks:
            catalog.set_extract_tasks(job_id, extract_tasks)

        _emit(92, "thumbnail")
        thumb_path = output_dir / "thumbnail.jpg"
        thumb_at = max(1.0, min(seconds * 0.1, 60.0)) if seconds else 3.0
        extract_thumbnail(input_path, thumb_path, thumb_at)

        # Hover-scrub storyboard: a sprite sheet + WebVTT beside the manifest, so
        # the player can preview the frame under the cursor on the seek bar.
        _emit(94, "storyboard")
        _sv = media.get("video") or {}
        storyboard_ok = generate_storyboard(
            input_path, output_dir, seconds,
            int(_sv.get("width") or 0), int(_sv.get("height") or 0),
        )
        storyboard_url = f"{base}/thumbnails.vtt" if storyboard_ok else None

        _emit(95, "upload")
        uploaded = _upload_directory(settings.s3_segments_bucket, out_prefix, output_dir)
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

        # Top-level audio_tracks stays the minimal {language,label} the player needs;
        # media_info carries the richer VLC-style detail (codec/channels/forced/etc.)
        # for the Tracks panel, listing every source track — including image-based
        # subtitles that aren't extractable in-browser.
        audio_meta = [{"language": a["language"], "label": a["label"]} for a in audio_tracks]
        audio_media = [
            {
                "language": a["language"],
                "label": a["label"],
                "codec": a.get("codec"),
                "channels": a.get("channels"),
                "default": bool(a.get("default")),
            }
            for a in media["audio"]
        ]
        if not audio_media and audio_tracks:
            # Source was silent; an admin-attached external track was muxed in.
            audio_media = [
                {"language": "und", "label": "Audio", "codec": "aac", "channels": 2, "external": True}
            ]
        subtitle_media = [
            {
                "language": s["language"],
                "label": s["label"],
                "codec": s.get("codec"),
                "forced": bool(s.get("forced")),
                "text": bool(s.get("text")),
                "extracted": s.get("stream_index") in extracted_sub_streams,
            }
            for s in media["subtitles"]
        ]
        media_info = {
            "video": media["video"],
            "audio": audio_media,
            "subtitles": subtitle_media,
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
            storyboard_url=storyboard_url,
        )
        # A higher-fps ladder is now published — close out the interpolation state.
        if interp_ok:
            catalog.update_interp(job_id, "done")
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
        logger.info("job_canceled", job_id=job_id, variant=is_variant)
        if is_variant:
            # Only the half-written interpolated ladder is disposable — the title
            # itself (row, source, original ladder) must survive.
            _delete_prefix(settings.s3_segments_bucket, out_prefix)
            catalog.update_interp(job_id, "skipped", detail="smoothing canceled")
        else:
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
