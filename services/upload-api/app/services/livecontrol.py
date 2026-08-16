from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.config import get_settings
from app.models.schemas import LiveEvent, Movie
from app.services import catalog, livepackager, s3

logger = logging.getLogger(__name__)


class LiveStartError(Exception):
    """A channel could not be started for a reason the caller should surface
    (missing source, etc.). Carries an HTTP status for the route layer."""

    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def start_channel(event: LiveEvent) -> None:
    """Start packaging for a channel. Playout resolves the uploaded source and
    re-streams it; ingest pulls the connected encoder. Shared by the admin
    'Go live' route and the scheduler's auto-start, so the behaviour is identical
    whether a human or the scheduler triggers it."""
    settings = get_settings()
    if event.source_type == "playout":
        if not event.playout_source_movie_id:
            raise LiveStartError("No playout source configured.", 400)
        source_key = s3.first_key(
            settings.s3_video_bucket, f"{event.playout_source_movie_id}/"
        )
        if not source_key:
            raise LiveStartError(
                "Playout source is no longer stored — re-upload the title."
            )
        livepackager.start_playout(event, settings.s3_video_bucket, source_key)
    else:
        # Raises HTTPException(409) if no encoder is connected yet.
        livepackager.start_ingest(event)


def stop_channel(event_id: str) -> None:
    """Best-effort stop of a channel's packager (never raises)."""
    try:
        livepackager.stop(event_id)
    except Exception:  # noqa: BLE001 - stop must not block a state transition
        pass


def _harvest_recording(event: LiveEvent) -> str | None:
    """Finalize a recorded channel into a permanent VOD catalog entry. The live
    segments are ALREADY a complete ABR HLS ladder, so no re-encode happens — the
    packager just writes #EXT-X-ENDLIST and copies them to the segments bucket, and
    we register a catalog row tagged as a replay of the live event."""
    vod_id = str(uuid4())
    try:
        result = livepackager.finalize_record(event.id, vod_id)
    except Exception as exc:  # noqa: BLE001 - never block ending on a harvest failure
        logger.warning("live: harvest failed for %s: %s", event.id, exc)
        return None
    if not result:
        return None

    settings = get_settings()
    now = datetime.now(tz=timezone.utc)
    started = event.started_at or now
    date_str = started.strftime("%b %d, %Y")
    movie = Movie(
        id=vod_id,
        created_at=now,
        status="ready",
        title=f"{event.title} — Live {date_str}",
        genre="Live",
        year=started.year,
        rating="NR",
        description=(
            f"Replay of a live event streamed on {started.strftime('%b %d, %Y at %H:%M UTC')}."
        ),
        tag=None,
        manifest_url=f"{settings.origin_base_url}/hls/{vod_id}/master.m3u8",
        poster_url=event.poster_url,
        backdrop_url=event.backdrop_url,
    )
    catalog.save(movie)
    logger.info("live: harvested %s -> replay VOD %s", event.id, vod_id)
    return vod_id


def end_channel(event: LiveEvent) -> str | None:
    """End a channel. If it was recording, harvest its segments into a replay VOD
    (finalize also stops ffmpeg); otherwise just stop it. Returns the new VOD id
    when a replay was created. Never raises — ending must always succeed."""
    if event.record_to_vod and event.state in {"live", "starting"}:
        return _harvest_recording(event)
    stop_channel(event.id)
    return None
