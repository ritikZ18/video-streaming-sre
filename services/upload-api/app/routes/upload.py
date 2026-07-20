from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, File, Form, UploadFile, status

from app.config import get_settings
from app.models.schemas import Movie, UploadResponse
from app.services import catalog, queue, s3
from app.utils.validators import validate_extension, validate_magic_bytes, validate_size


router = APIRouter(prefix="/api/v1", tags=["upload"])


@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadResponse,
)
async def upload_video(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    genre: str | None = Form(default=None),
    year: int | None = Form(default=None),
    rating: str | None = Form(default=None),
    duration: str | None = Form(default=None),
    tag: str | None = Form(default=None),
    description: str | None = Form(default=None),
) -> UploadResponse:
    """Validate and upload a video, enqueue transcoding, and register a
    catalog entry (status=processing) that the worker flips to ready."""
    settings = get_settings()

    validate_extension(file.filename)
    validate_magic_bytes(file)
    validate_size(file)

    job_id = str(uuid4())
    s3_key = f"{job_id}/{file.filename}"

    s3.upload_fileobj(settings.s3_video_bucket, s3_key, file.file)

    # Register the catalog entry (status=processing) BEFORE enqueuing, so the
    # row always exists before the worker can complete and flip it to ready.
    # The movie id IS the job id, so the worker can update by job_id.
    movie = Movie(
        id=job_id,
        created_at=datetime.now(tz=timezone.utc),
        status="processing",
        title=title or file.filename or "Untitled",
        genre=genre or "Uncategorized",
        year=year or datetime.now(tz=timezone.utc).year,
        rating=rating or "NR",
        duration=duration,
        tag=tag,
        description=description,
    )
    catalog.save(movie)

    queue.enqueue_transcode_job(job_id=job_id, s3_key=s3_key, filename=file.filename)

    return UploadResponse(job_id=job_id, status="queued")
