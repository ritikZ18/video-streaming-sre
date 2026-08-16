"""Live lifecycle reconciler.

A single background loop that drives the automatic state transitions the admin
shouldn't have to do by hand:

  * ingest: when an encoder connects to the ingest server, auto go-live; when it
    disconnects, end the channel after a short reconnect grace.
  * scheduled: at scheduled_start, auto-start (playout starts streaming; ingest
    moves to "starting" and waits for the encoder). At scheduled_end, auto-end.
  * playout: when the source finishes (a non-looping playout) or the encoder
    process exits, mark the channel ended.

The tick is fully synchronous (sync boto3 + sync httpx) and is run off the event
loop via asyncio.to_thread, so it never blocks request handling.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx

from app.config import get_settings
from app.models.schemas import LiveEvent
from app.services import livecontrol, liveevents

logger = logging.getLogger(__name__)

# Last wall-clock time (epoch secs) an ingest event's encoder was seen publishing.
# Used to time the reconnect grace before ending a dropped channel.
_last_seen: dict[str, float] = {}

_ACTIVE = {"live", "starting"}


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _mediamtx_publishers() -> set[str] | None:
    """Set of stream keys currently being published to the ingest server, or None
    if the ingest API can't be reached (so callers skip ingest reconciliation
    rather than falsely ending a live channel)."""
    settings = get_settings()
    url = f"http://{settings.live_ingest_api_host}/v3/paths/list"
    try:
        resp = httpx.get(url, timeout=3.0)
        resp.raise_for_status()
    except httpx.HTTPError:
        return None
    keys: set[str] = set()
    for item in resp.json().get("items", []):
        name = str(item.get("name", ""))
        if name.startswith("live/") and (item.get("ready") or item.get("source")):
            keys.add(name.split("/", 1)[1])
    return keys


def _packager_state(event_id: str) -> str:
    settings = get_settings()
    try:
        resp = httpx.get(f"{settings.live_packager_url}/status/{event_id}", timeout=3.0)
        resp.raise_for_status()
        return str(resp.json().get("state", ""))
    except httpx.HTTPError:
        return ""


def _go_live(event: LiveEvent) -> None:
    try:
        livecontrol.start_channel(event)
        liveevents.update_fields(
            event.id,
            {"state": "live", "started_at": _now(), "ended_at": None, "error_detail": None},
        )
        logger.info("live: auto-started channel %s (%s)", event.id, event.source_type)
    except Exception as exc:  # noqa: BLE001
        liveevents.update_fields(event.id, {"state": "error", "error_detail": str(exc)})
        logger.warning("live: auto-start failed for %s: %s", event.id, exc)


def _end(event: LiveEvent, reason: str) -> None:
    # Harvests a recorded channel into a replay VOD; otherwise just stops it.
    vod_id = livecontrol.end_channel(event)
    liveevents.update_fields(event.id, {"state": "ended", "ended_at": _now()})
    _last_seen.pop(event.id, None)
    if vod_id:
        logger.info("live: ended channel %s (%s) -> replay VOD %s", event.id, reason, vod_id)
    else:
        logger.info("live: ended channel %s (%s)", event.id, reason)


def _tick_ingest(event: LiveEvent, publishers: set[str], now: float) -> None:
    key = event.stream_key
    present = bool(key and key in publishers)
    if present:
        _last_seen[event.id] = now
        if event.state != "live":
            _go_live(event)  # auto go-live the moment the encoder connects
        return
    # No encoder publishing. Only a channel that WAS live gets the grace timer;
    # a "starting" (scheduled, waiting-for-encoder) channel just keeps waiting.
    if event.state == "live":
        last = _last_seen.setdefault(event.id, now)
        if now - last > get_settings().live_ingest_grace_seconds:
            _end(event, "encoder disconnected")


def _tick_playout(event: LiveEvent) -> None:
    if event.state == "live" and _packager_state(event.id) in {"stopped", "ended"}:
        # ffmpeg exited: a non-looping playout finished, or the process died.
        _end(event, "source finished")


def tick() -> None:
    now_dt = _now()
    now = now_dt.timestamp()
    events = liveevents.list_all()
    publishers = _mediamtx_publishers()

    for event in events:
        try:
            # 1. Scheduled -> start at scheduled_start.
            if event.state == "scheduled":
                start_at = _as_aware(event.scheduled_start)
                if start_at and start_at <= now_dt:
                    if event.source_type == "playout":
                        _go_live(event)
                    else:
                        # Open the ingest slot; the encoder-connect path goes live.
                        liveevents.update_fields(event.id, {"state": "starting"})
                        logger.info("live: schedule opened ingest slot %s", event.id)
                continue

            # 2. Scheduled end for any active channel.
            end_at = _as_aware(event.scheduled_end)
            if event.state in _ACTIVE and end_at and end_at <= now_dt:
                _end(event, "scheduled end reached")
                continue

            # 3. Liveness by source type.
            if event.source_type == "ingest":
                if publishers is not None:
                    _tick_ingest(event, publishers, now)
            else:
                _tick_playout(event)
        except Exception:  # noqa: BLE001 - one bad event must not stall the loop
            logger.exception("live: tick failed for %s", event.id)


async def run() -> None:
    settings = get_settings()
    interval = settings.live_poll_interval_seconds
    logger.info("live scheduler started (interval=%ss)", interval)
    while True:
        try:
            await asyncio.to_thread(tick)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("live scheduler tick crashed")
        await asyncio.sleep(interval)
