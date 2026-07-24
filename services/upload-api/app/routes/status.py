from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import require_admin
from app.models.schemas import JobStatusResponse
from app.services import catalog

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str) -> JobStatusResponse:
    """Report transcode progress from the catalog (written by the worker)."""
    movie = catalog.get(job_id)
    if movie is None:
        return JobStatusResponse(
            job_id=job_id, status="queued", stream_url=None, progress=0, stage="queued"
        )
    if movie.status == "ready":
        return JobStatusResponse(
            job_id=job_id,
            status="complete",
            stream_url=movie.manifest_url,
            progress=100,
            stage="ready",
        )
    return JobStatusResponse(
        job_id=job_id,
        status="processing",
        stream_url=None,
        progress=movie.progress or 0,
        stage=movie.stage or "queued",
    )


@router.post("/{job_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
def cancel_job(job_id: str, _admin: str = Depends(require_admin)) -> dict[str, str]:
    """Flag a still-processing transcode for cancellation (admin only). The
    worker aborts ffmpeg, deletes the source + any partial segments, and removes
    the catalog row."""
    movie = catalog.get(job_id)
    if movie is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if movie.status == "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job already completed",
        )
    catalog.request_cancel(job_id)
    return {"job_id": job_id, "status": "canceling"}
