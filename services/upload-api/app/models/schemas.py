from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AudioTrack(BaseModel):
    language: str
    label: str


class SubtitleTrack(BaseModel):
    language: str
    label: str
    url: str
    forced: bool = False


class UploadResponse(BaseModel):
    job_id: str
    status: Literal["queued"]


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "complete"]
    stream_url: str | None = None
    progress: int = 0
    stage: str | None = None


class MovieBase(BaseModel):
    title: str
    description: str | None = None
    genre: str
    year: int
    rating: str
    duration: str | None = None
    tag: str | None = None


class MovieCreate(MovieBase):
    # Admins registering pre-existing HLS assets can supply the manifest URL.
    manifest_url: str | None = None


Visibility = Literal["draft", "published", "unlisted"]

# I/O Framer (frame interpolation) lifecycle for a title. None = never requested.
#   queued     -> an interpolation pass is enqueued
#   processing -> the I/O Framer sidecar is running
#   done       -> a higher-fps ladder is published
#   skipped    -> declined a guardrail (source already high-fps, too long/tall, …)
#   failed     -> the pass errored; the original ladder is untouched
InterpStatus = Literal["queued", "processing", "done", "skipped", "failed"]


class Movie(MovieBase):
    id: str
    created_at: datetime
    status: Literal["processing", "ready"] = "ready"
    # draft = hidden everywhere but admin; unlisted = playable by link, not in the
    # public catalog; published = shown to everyone. Legacy rows default published.
    visibility: Visibility = "published"
    manifest_url: str | None = None
    # HEVC master for HDR titles; the player uses it only where the browser can
    # decode HEVC, else it falls back to manifest_url (H.264).
    hdr_manifest_url: str | None = None
    dash_url: str | None = None
    # WebVTT storyboard (hover-scrub sprite map) served beside the manifest.
    storyboard_url: str | None = None
    # Auto-extracted poster frame (the worker sets this every transcode).
    thumbnail_url: str | None = None
    # Custom artwork uploaded by an admin; the worker never overwrites these, so
    # they survive a re-transcode. The player/cards prefer poster_url over
    # thumbnail_url, and backdrop_url for the 16:9 hero.
    poster_url: str | None = None
    backdrop_url: str | None = None
    progress: int = 0
    stage: str | None = None
    audio_tracks: list[AudioTrack] = Field(default_factory=list)
    subtitle_tracks: list[SubtitleTrack] = Field(default_factory=list)
    media_info: dict[str, Any] | None = None
    # Live audio/subtitle extraction checklist the worker writes during a transcode
    # ({kind, label, lang, codec, state}); the admin panel renders it as a 'todo
    # list'. Free-form dicts so the worker can evolve the shape without a migration.
    extract_tasks: list[dict[str, Any]] = Field(default_factory=list)
    # True once an admin attaches an external audio track to a silent title. The
    # worker muxes it only when the source has no embedded audio; survives
    # re-transcodes (stored beside the segments, like custom artwork).
    has_external_audio: bool = False
    # --- I/O Framer (frame interpolation) — Phase 0: fields only, no behaviour ---
    # Set when an admin asks to smooth a title to a higher frame rate. The worker
    # reads these in a later phase; for now they only persist intent + state.
    interp_requested: bool = False
    interp_target_fps: int | None = None
    interp_status: InterpStatus | None = None
    interp_detail: str | None = None  # human-readable reason for skipped/failed
    # A NON-destructive smoothed rendition published under {id}/interp/. When set,
    # the player offers a "Smooth {interp_fps}fps" toggle that swaps to this ladder
    # while the original manifest_url stays the default.
    interp_manifest_url: str | None = None
    interp_dash_url: str | None = None
    interp_fps: int | None = None
    # Live interpolation progress (I/O Framer's own 0-100 + stage) + the epoch it
    # started, so the UI can show a real percentage, elapsed time and ETA.
    interp_progress: int | None = None
    interp_stage: str | None = None
    interp_started_at: int | None = None


class MoviePatch(BaseModel):
    """Partial metadata edit from the admin studio — only provided fields change."""

    title: str | None = None
    description: str | None = None
    genre: str | None = None
    year: int | None = None
    rating: str | None = None
    tag: str | None = None
    visibility: Visibility | None = None
    # Poster source: the studio's poster dropdown sends "" to reset to the
    # auto-extracted frame, or a URL to pin a custom poster/backdrop. Empty
    # string is a real value (distinct from "field absent"), so it clears.
    poster_url: str | None = None
    backdrop_url: str | None = None


class InterpConfig(BaseModel):
    """Public read of the I/O Framer feature flag + guardrails, so the upload UI
    can show/hide the toggle and label the caps. No secrets."""

    enabled: bool
    default_target_fps: int
    max_target_fps: int
    max_height: int
    max_source_fps: int
    max_duration_seconds: int


class MovieList(BaseModel):
    movies: list[Movie] = Field(default_factory=list)


