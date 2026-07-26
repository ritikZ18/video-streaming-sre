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


class Movie(MovieBase):
    id: str
    created_at: datetime
    status: Literal["processing", "ready"] = "ready"
    manifest_url: str | None = None
    # HEVC master for HDR titles; the player uses it only where the browser can
    # decode HEVC, else it falls back to manifest_url (H.264).
    hdr_manifest_url: str | None = None
    dash_url: str | None = None
    thumbnail_url: str | None = None
    progress: int = 0
    stage: str | None = None
    audio_tracks: list[AudioTrack] = Field(default_factory=list)
    subtitle_tracks: list[SubtitleTrack] = Field(default_factory=list)
    media_info: dict[str, Any] | None = None


class MovieList(BaseModel):
    movies: list[Movie] = Field(default_factory=list)


