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


class MovieBase(BaseModel):
    title: str
    description: str | None = None
    genre: str
    year: int
    rating: str
    duration: str | None = None
    tag: str | None = None


class MovieCreate(MovieBase):
    pass


class Movie(MovieBase):
    id: str
    created_at: datetime


class MovieList(BaseModel):
    movies: list[Movie] = Field(default_factory=list)


