from __future__ import annotations

import httpx
from app.config import get_settings
from app.models.schemas import LiveEvent
from fastapi import HTTPException, status

# Thin control-plane client for the live packager (the service that owns the
# per-channel ffmpeg). The upload API never runs ffmpeg itself; it just tells the
# packager to start/stop a channel, mirroring how the worker drives io-framer.

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


def _post(path: str, payload: dict) -> dict:
    url = f"{get_settings().live_packager_url}{path}"
    try:
        resp = httpx.post(url, json=payload, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:  # packager down / unreachable
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Live packager is unreachable",
        ) from exc
    if resp.status_code >= 400:
        # Surface the packager's own reason (e.g. "no encoder connected yet",
        # "channel limit reached") straight through to the admin.
        detail = "Live packager rejected the request"
        try:
            detail = resp.json().get("detail", detail)
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(status_code=resp.status_code, detail=detail)
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return {}


def start_playout(event: LiveEvent, source_bucket: str, source_key: str) -> dict:
    """Re-stream an uploaded title as a live channel (ffmpeg -re from S3)."""
    return _post(
        "/playout/start",
        {
            "event_id": event.id,
            "source_bucket": source_bucket,
            "source_key": source_key,
            "loop": event.loop,
            "max_height": event.max_height,
            "audio_only": event.audio_only,
            "record": event.record_to_vod,
        },
    )


def start_ingest(event: LiveEvent) -> dict:
    """Pull a live encoder's feed from the ingest server and package it. The
    packager builds the internal pull URL from the stream key + protocol."""
    return _post(
        "/ingest/start",
        {
            "event_id": event.id,
            "stream_key": event.stream_key,
            "protocol": event.ingest_protocol,
            "max_height": event.max_height,
            "audio_only": event.audio_only,
            "record": event.record_to_vod,
        },
    )


def stop(event_id: str) -> dict:
    """Stop a channel (best-effort — a missing channel is not an error)."""
    return _post("/stop", {"event_id": event_id})


def finalize_record(event_id: str, vod_id: str) -> dict:
    """Harvest a recorded channel into a permanent VOD under the segments bucket.
    Returns {vod_id, files, master} on success."""
    return _post("/record/finalize", {"event_id": event_id, "vod_id": vod_id})
