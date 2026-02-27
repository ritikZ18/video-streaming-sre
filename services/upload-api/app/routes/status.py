from fastapi import APIRouter

from app.config import get_settings
from app.models.schemas import JobStatusResponse
from app.services.s3 import object_exists


router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str) -> JobStatusResponse:
    settings = get_settings()
    master_key = f"{job_id}/master.m3u8"

    if object_exists(settings.s3_segments_bucket, master_key):
        stream_url = f"{settings.origin_base_url}/hls/{job_id}/master.m3u8"
        return JobStatusResponse(job_id=job_id, status="complete", stream_url=stream_url)

    # In this minimal implementation we cannot distinguish between queued
    # and actively processing without additional state, so we expose a
    # generic "processing" status for non-complete jobs.
    return JobStatusResponse(job_id=job_id, status="processing", stream_url=None)


