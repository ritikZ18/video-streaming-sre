from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, File, UploadFile, status

from app.config import get_settings
from app.models.schemas import UploadResponse
from app.services import queue, s3
from app.utils.validators import validate_extension, validate_magic_bytes, validate_size


router = APIRouter(prefix="/api/v1", tags=["upload"])


@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadResponse,
)
async def upload_video(file: UploadFile = File(...)) -> UploadResponse:
    """Validate and upload an incoming video file, enqueueing a transcode job."""
    settings = get_settings()

    validate_extension(file.filename)
    validate_magic_bytes(file)
    validate_size(file)

    job_id = str(uuid4())
    s3_key = f"{job_id}/{file.filename}"

    s3.upload_fileobj(settings.s3_video_bucket, s3_key, file.file)
    queue.enqueue_transcode_job(job_id=job_id, s3_key=s3_key, filename=file.filename)

    return UploadResponse(job_id=job_id, status="queued")


