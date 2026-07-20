from fastapi import APIRouter

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
