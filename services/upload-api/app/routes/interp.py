from fastapi import APIRouter

from app.config import get_settings
from app.models.schemas import InterpConfig

router = APIRouter(prefix="/api/v1/interp", tags=["interp"])


@router.get("/config", response_model=InterpConfig, summary="I/O Framer guardrails")
def interp_config() -> InterpConfig:
    """Feature flag + caps for frame interpolation (I/O Framer), read by the
    upload UI. The toggle is shown only when ``enabled`` is true; the caps label
    the guardrails. Nothing here triggers GPU work.
    """
    s = get_settings()
    return InterpConfig(
        enabled=s.interp_enabled,
        default_target_fps=s.interp_default_target_fps,
        max_target_fps=s.interp_max_target_fps,
        max_height=s.interp_max_height,
        max_source_fps=s.interp_max_source_fps,
        max_duration_seconds=s.interp_max_duration_seconds,
    )
