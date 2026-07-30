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
    # True once an admin attaches an external audio track to a silent title. The
    # worker muxes it only when the source has no embedded audio; survives
    # re-transcodes (stored beside the segments, like custom artwork).
    has_external_audio: bool = False


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


class MovieList(BaseModel):
    movies: list[Movie] = Field(default_factory=list)


