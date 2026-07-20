from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    job_id: str
    status: Literal["queued"]


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "complete"]
    stream_url: str | None = None
    progress: int = 0


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
    dash_url: str | None = None
    thumbnail_url: str | None = None
    progress: int = 0


class MovieList(BaseModel):
    movies: list[Movie] = Field(default_factory=list)


