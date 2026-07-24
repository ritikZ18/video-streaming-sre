from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_admin

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/check")
def check(admin: str = Depends(require_admin)) -> dict[str, str]:
    """Validate admin credentials (used by the admin login screen)."""
    return {"status": "ok", "user": admin}
