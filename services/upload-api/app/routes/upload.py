from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.auth import require_admin
from app.config import Settings, get_settings
from app.models.schemas import Movie, UploadResponse
from app.services import catalog, queue, s3
from app.utils.validators import validate_extension, validate_magic_bytes, validate_size

router = APIRouter(prefix="/api/v1", tags=["upload"])


def _resolve_interp(
    settings: Settings, requested: bool, target_fps: int | None
) -> tuple[bool, int | None, str | None, str | None]:
    """Validate a frame-interpolation (I/O Framer) request against the server
    guardrails at upload time.

    Returns ``(interp_requested, interp_target_fps, interp_status, interp_detail)``
    to persist on the catalog row. Only the flag + target-fps ceiling are checked
    here; the deep guardrails that need the decoded stream (height, duration,
    source fps) are evaluated by the worker in a later phase.
    """
    if not requested:
        return False, None, None, None
    target = target_fps or settings.interp_default_target_fps
    if not settings.interp_enabled:
        # Honour the intent on the row, but it will not be enqueued for a pass.
        return True, target, "skipped", "interpolation is disabled on this server"
    if target < 1 or target > settings.interp_max_target_fps:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "interp_target_fps must be between 1 and "
                f"{settings.interp_max_target_fps}"
            ),
        )
    return True, target, "queued", None


@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadResponse,
)
async def upload_video(
    file: UploadFile = File(...),  # noqa: B008
    title: str | None = Form(default=None),
    genre: str | None = Form(default=None),
    year: int | None = Form(default=None),
    rating: str | None = Form(default=None),
    duration: str | None = Form(default=None),
    tag: str | None = Form(default=None),
    description: str | None = Form(default=None),
    interp: bool = Form(default=False),
    interp_target_fps: int | None = Form(default=None),
    _admin: str = Depends(require_admin),
) -> UploadResponse:
    """Validate and upload a video, enqueue transcoding, and register a
    catalog entry (status=processing) that the worker flips to ready."""
    settings = get_settings()

    validate_extension(file.filename)
    validate_magic_bytes(file)
    validate_size(file)

    # Frame interpolation (I/O Framer): validate the request up front so a bad
    # target-fps is a 400 before we store the multi-GB upload.
    interp_requested, resolved_fps, interp_status, interp_detail = _resolve_interp(
        settings, interp, interp_target_fps
    )

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
        interp_requested=interp_requested,
        interp_target_fps=resolved_fps,
        interp_status=interp_status,
        interp_detail=interp_detail,
    )
    catalog.save(movie)

    # Only ask the worker to interpolate when the request actually passed the
    # guardrails (status "queued"); a "skipped" request is recorded but transcodes
    # normally.
    enqueue_interp = interp_status == "queued"
    queue.enqueue_transcode_job(
        job_id=job_id,
        s3_key=s3_key,
        filename=file.filename,
        interp=enqueue_interp,
        interp_target_fps=resolved_fps if enqueue_interp else None,
    )

    return UploadResponse(job_id=job_id, status="queued")
