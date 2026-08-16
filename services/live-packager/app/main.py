"""Live packager control plane.

Endpoints the upload API drives:
  POST /playout/start   re-stream an uploaded title (or a built-in test source)
  POST /ingest/start    pull a live encoder feed from the ingest server
  POST /stop            stop a channel
  GET  /status/{id}     channel liveness + fps/speed
  GET  /healthz         service health
  GET  /metrics         Prometheus exposition
"""

from __future__ import annotations

import logging
import os
import shutil

import boto3
import httpx
from botocore.config import Config as BotoConfig
from fastapi import FastAPI, HTTPException, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from app.channels import ChannelLimitError, ChannelManager
from app.config import get_settings
from app.ladder import build_command, build_test_command, select_rungs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("live-packager")

app = FastAPI(title="Live Packager", version="0.1.0")
_cfg = get_settings()
_manager = ChannelManager(max_channels=_cfg.max_channels)


# --- request models -------------------------------------------------------
class PlayoutRequest(BaseModel):
    event_id: str
    source_bucket: str | None = None
    source_key: str | None = None
    loop: bool = False
    max_height: int = 720
    audio_only: bool = False
    test: bool = False
    record: bool = False


class IngestRequest(BaseModel):
    event_id: str
    stream_key: str
    protocol: str = "rtmp"
    max_height: int = 720
    audio_only: bool = False
    record: bool = False


class StopRequest(BaseModel):
    event_id: str


class FinalizeRequest(BaseModel):
    event_id: str
    vod_id: str


_CONTENT_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".ts": "video/mp2t",
    ".m4s": "video/iso.segment",
    ".mp4": "video/mp4",
}


# --- helpers --------------------------------------------------------------
def _out_dir(event_id: str) -> str:
    return os.path.join(_cfg.segments_dir, event_id)


def _s3_client():
    return boto3.client(
        "s3",
        region_name=_cfg.aws_region,
        endpoint_url=_cfg.s3_endpoint_url,
        config=BotoConfig(signature_version="s3v4"),
    )


def _presigned_source(bucket: str, key: str) -> str:
    """A time-limited GET URL ffmpeg can read directly (no multi-GB pre-download).
    The URL targets the in-cluster S3 endpoint, reachable from this container."""
    return _s3_client().generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=6 * 3600
    )


def _ingest_publisher_ready(stream_key: str) -> bool:
    """Ask the ingest server (MediaMTX API) whether a publisher is live on this
    path, so we only try to pull once an encoder is actually connected."""
    url = f"http://{_cfg.ingest_api_host}/v3/paths/list"
    want = f"live/{stream_key}"
    try:
        resp = httpx.get(url, timeout=3.0)
        resp.raise_for_status()
        for item in resp.json().get("items", []):
            if item.get("name") == want and item.get("ready"):
                return True
    except httpx.HTTPError:
        # API unreachable — don't hard-block; let ffmpeg try and fail loudly.
        return True
    return False


# --- routes ---------------------------------------------------------------
@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "active_channels": _manager.running_count()}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/playout/start", status_code=status.HTTP_202_ACCEPTED)
def playout_start(req: PlayoutRequest) -> dict:
    out_dir = _out_dir(req.event_id)
    if req.test:
        cmd = build_test_command(out_dir, _cfg)
        kind = "test"
    else:
        if not req.source_bucket or not req.source_key:
            raise HTTPException(status_code=400, detail="source_bucket/source_key required")
        source = _presigned_source(req.source_bucket, req.source_key)
        input_args = ["-re"]
        if req.loop:
            input_args += ["-stream_loop", "-1"]
        input_args += [
            "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "2",
            "-i", source,
        ]
        rungs = select_rungs(req.max_height, _cfg.max_height)
        cmd = build_command(input_args, out_dir, rungs, req.audio_only, _cfg, req.record)
        kind = "playout"
    try:
        _manager.start(req.event_id, cmd, out_dir, kind)
    except ChannelLimitError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"status": "started", "event_id": req.event_id, "kind": kind}


@app.post("/ingest/start", status_code=status.HTTP_202_ACCEPTED)
def ingest_start(req: IngestRequest) -> dict:
    if not _ingest_publisher_ready(req.stream_key):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No encoder is connected yet — start your encoder, then Go Live.",
        )
    # Whatever protocol the encoder used, MediaMTX republishes it as RTMP here.
    pull_url = f"rtmp://{_cfg.ingest_rtmp_host}/live/{req.stream_key}"
    input_args = ["-i", pull_url]
    out_dir = _out_dir(req.event_id)
    rungs = select_rungs(req.max_height, _cfg.max_height)
    cmd = build_command(input_args, out_dir, rungs, req.audio_only, _cfg, req.record)
    try:
        _manager.start(req.event_id, cmd, out_dir, "ingest")
    except ChannelLimitError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"status": "started", "event_id": req.event_id, "kind": "ingest"}


@app.post("/stop")
def stop(req: StopRequest) -> dict:
    stopped = _manager.stop(req.event_id)
    return {"status": "stopped" if stopped else "not_running", "event_id": req.event_id}


@app.post("/record/finalize")
def record_finalize(req: FinalizeRequest) -> dict:
    """Turn a recorded channel's kept segments into a permanent VOD: stop ffmpeg
    gracefully (writes #EXT-X-ENDLIST), then copy the whole segment dir to the
    segments bucket under <vod_id>/ so the origin serves it at /hls/<vod_id>/.
    No re-encode — the live segments are already a complete ABR ladder."""
    out_dir = _out_dir(req.event_id)
    # Graceful stop, KEEPING the files (ENDLIST is written on SIGINT).
    _manager.stop(req.event_id, clean=False)
    if not os.path.isdir(out_dir):
        raise HTTPException(status_code=404, detail="No recording found for this channel.")

    client = _s3_client()
    uploaded = 0
    has_master = False
    for fname in sorted(os.listdir(out_dir)):
        fpath = os.path.join(out_dir, fname)
        if not os.path.isfile(fpath):
            continue
        ext = os.path.splitext(fname)[1].lower()
        ctype = _CONTENT_TYPES.get(ext, "application/octet-stream")
        client.upload_file(
            fpath, _cfg.s3_segments_bucket, f"{req.vod_id}/{fname}",
            ExtraArgs={"ContentType": ctype},
        )
        uploaded += 1
        if fname == "master.m3u8":
            has_master = True

    shutil.rmtree(out_dir, ignore_errors=True)
    if not has_master or uploaded == 0:
        raise HTTPException(status_code=422, detail="Recording had no playable segments.")
    logger.info("harvested live channel %s -> vod %s (%s files)", req.event_id, req.vod_id, uploaded)
    return {"vod_id": req.vod_id, "files": uploaded, "master": f"{req.vod_id}/master.m3u8"}


@app.get("/status/{event_id}")
def channel_status(event_id: str) -> dict:
    channel = _manager.get(event_id)
    if channel is None:
        return {"event_id": event_id, "state": "stopped"}
    return {
        "event_id": event_id,
        "state": "live" if channel.alive else "ended",
        "kind": channel.kind,
        "uptime_seconds": channel.uptime,
        "fps": channel.fps,
        "speed": channel.speed,
    }
