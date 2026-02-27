from fastapi import APIRouter

from app.config import get_settings
from app.services import s3


router = APIRouter()


@router.get("/health", summary="Liveness probe")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
def ready() -> dict[str, str]:
    """Check connectivity to key dependencies."""
    settings = get_settings()
    # Minimal check: confirm we can talk to the segments bucket
    # by issuing a HEAD on a non-existent object; any response
    # other than connection error is considered acceptable here.
    try:
        _ = s3.object_exists(settings.s3_segments_bucket, "__streamsre_readycheck__")
    except Exception:  # noqa: BLE001
        return {"status": "degraded"}
    return {"status": "ready"}


