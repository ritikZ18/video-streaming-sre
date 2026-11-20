from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class S3Ref(BaseModel):
    s3_bucket: str
    s3_key: str


class InterpOptions(BaseModel):
    model: str | None = None
    max_height: int | None = None


class InterpolateRequest(BaseModel):
    movie_id: str
    target_fps: int = Field(gt=0)
    source: S3Ref
    output: S3Ref
    options: InterpOptions | None = None


class InterpolateAccepted(BaseModel):
    job_id: str
    status: Literal["queued", "processing"]


class OutputInfo(BaseModel):
    s3_bucket: str
    s3_key: str
    fps: int
    frames: int


class Metrics(BaseModel):
    gpu: bool
    elapsed_seconds: float


JobStatusValue = Literal["queued", "processing", "done", "failed"]


class JobStatus(BaseModel):
    job_id: str
    status: JobStatusValue
    stage: str | None = None
    progress: int = 0
    source_fps: float | None = None
    target_fps: int
    output: OutputInfo | None = None
    detail: str | None = None
    metrics: Metrics | None = None


class Health(BaseModel):
    status: str
    backend: str  # "vulkan" | "cpu" | "none"
    gpu: bool
    model: str
    devices: list[str] = []
