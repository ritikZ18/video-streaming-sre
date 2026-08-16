from __future__ import annotations

import secrets
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth import require_admin
from app.config import get_settings
from app.models.schemas import (
    LiveEvent,
    LiveEventAdminList,
    LiveEventCreate,
    LiveEventList,
    LiveEventPublic,
    to_public,
)
from app.services import livecontrol, liveevents

router = APIRouter(prefix="/api/v1/live", tags=["live"])

# States a viewer cares about (idle drafts + ended channels are admin-only).
_PUBLIC_STATES = {"scheduled", "starting", "live"}


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _require_live_enabled() -> None:
    if not get_settings().live_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Live streaming is disabled on this server.",
        )


def _require_event(event_id: str) -> LiveEvent:
    event = liveevents.get(event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Live event not found"
        )
    return event


def _manifest_url(event_id: str) -> str:
    return f"{get_settings().origin_base_url}/live/{event_id}/master.m3u8"


def _ingest_url(protocol: str, stream_key: str) -> str:
    settings = get_settings()
    if protocol == "srt":
        # SRT carries the stream id (path) as a URL parameter.
        return f"srt://{settings.live_ingest_srt_host}?streamid=publish:live/{stream_key}"
    if protocol == "whip":
        return f"{settings.live_ingest_whip_base}/live/{stream_key}/whip"
    return f"rtmp://{settings.live_ingest_rtmp_host}/live/{stream_key}"


# --- Public reads ---------------------------------------------------------


@router.get("/events", response_model=LiveEventList)
def list_live_events() -> LiveEventList:
    """Public: live + upcoming channels, sanitized (no stream keys)."""
    events = [e for e in liveevents.list_all() if e.state in _PUBLIC_STATES]
    return LiveEventList(events=[to_public(e) for e in events])


@router.get("/events/{event_id}", response_model=LiveEventPublic)
def get_live_event(event_id: str) -> LiveEventPublic:
    """Public: one channel, sanitized. 404 for drafts/ended so links don't leak
    idle events."""
    event = _require_event(event_id)
    if event.state not in _PUBLIC_STATES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Live event not found"
        )
    return to_public(event)


# --- Admin ----------------------------------------------------------------


@router.get("/admin/events", response_model=LiveEventAdminList)
def admin_list_events(_admin: str = Depends(require_admin)) -> LiveEventAdminList:
    """Admin: every channel in every state, with stream keys + ingest URLs."""
    return LiveEventAdminList(events=liveevents.list_all())


@router.post(
    "/events", status_code=status.HTTP_201_CREATED, response_model=LiveEvent
)
def create_live_event(
    payload: LiveEventCreate, _admin: str = Depends(require_admin)
) -> LiveEvent:
    """Create a live channel (does not start it). For ingest channels this mints
    the publish key + push URL; for playout it records which title to re-stream."""
    _require_live_enabled()

    if payload.source_type == "playout":
        if not payload.playout_source_movie_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="playout_source_movie_id is required for a playout channel",
            )
    event_id = str(uuid4())

    stream_key: str | None = None
    ingest_url: str | None = None
    poster_url = payload.poster_url
    backdrop_url = payload.backdrop_url

    if payload.source_type == "ingest":
        stream_key = secrets.token_urlsafe(12)
        ingest_url = _ingest_url(payload.ingest_protocol, stream_key)
    else:
        # Inherit artwork from the source title so the browse card isn't blank.
        from app.services import catalog  # local import avoids a cycle at module load

        source = catalog.get(payload.playout_source_movie_id or "")
        if source is not None:
            poster_url = poster_url or source.poster_url or source.thumbnail_url
            backdrop_url = backdrop_url or source.backdrop_url

    initial_state = "scheduled" if payload.scheduled_start else "idle"

    event = LiveEvent(
        id=event_id,
        created_at=_now(),
        state=initial_state,
        stream_key=stream_key,
        ingest_url=ingest_url,
        manifest_url=_manifest_url(event_id),
        poster_url=poster_url,
        backdrop_url=backdrop_url,
        **payload.model_dump(exclude={"poster_url", "backdrop_url"}),
    )
    liveevents.save(event)
    return event


@router.post("/events/{event_id}/start", response_model=LiveEvent)
def start_live_event(
    event_id: str, _admin: str = Depends(require_admin)
) -> LiveEvent:
    """Go live now. Playout starts re-streaming the source title; ingest starts
    pulling from the encoder (409 if no encoder is connected — for ingest the
    scheduler also auto-goes-live the moment your encoder connects)."""
    _require_live_enabled()
    event = _require_event(event_id)
    try:
        livecontrol.start_channel(event)
    except livecontrol.LiveStartError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    liveevents.update_fields(
        event_id,
        {"state": "live", "started_at": _now(), "ended_at": None, "error_detail": None},
    )
    return _require_event(event_id)


@router.post("/events/{event_id}/stop", response_model=LiveEvent)
def stop_live_event(
    event_id: str, _admin: str = Depends(require_admin)
) -> LiveEvent:
    """End a channel. If it was recording, its segments are harvested into a
    replay VOD (no re-encode); otherwise it's just stopped."""
    _require_live_enabled()
    event = _require_event(event_id)
    livecontrol.end_channel(event)
    liveevents.update_fields(event_id, {"state": "ended", "ended_at": _now()})
    return _require_event(event_id)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_live_event(
    event_id: str, _admin: str = Depends(require_admin)
) -> Response:
    event = _require_event(event_id)
    if event.state in {"live", "starting"}:
        livecontrol.stop_channel(event_id)
    liveevents.delete_row(event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Ingest authorization (called by MediaMTX, not the browser) -----------


@router.post("/mediamtx-auth")
async def mediamtx_auth(request: Request) -> Response:
    """MediaMTX HTTP auth hook. Only publish actions reach here (reads/api/metrics
    are excluded in mediamtx.yml). Allow a push only if its path matches a known
    ingest event's stream key; deny everything else. 2xx = allow, 401 = deny."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad request")

    if body.get("action") != "publish":
        return Response(status_code=status.HTTP_200_OK)

    path = str(body.get("path", ""))
    # MediaMTX path is "live/<key>"; take the segment after the first slash.
    key = path.split("/", 1)[1] if "/" in path else path
    event = liveevents.find_by_stream_key(key)
    if event is not None and event.source_type == "ingest":
        return Response(status_code=status.HTTP_200_OK)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unknown stream key")
