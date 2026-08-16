from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

# Public, server-side TMDB proxy. The API key lives ONLY here (never in the
# browser); the frontend calls this via the resolved backend base, so the static
# viewer's browse catalog gets real posters through the tunnel gateway without
# ever exposing the key. Read-only metadata, so it's fine on the public surface.
router = APIRouter(prefix="/api/v1/tmdb", tags=["tmdb"])

_TMDB_BASE = "https://api.themoviedb.org/3"


@router.get("/{path:path}")
async def tmdb_proxy(path: str, request: Request) -> JSONResponse:
    key = os.getenv("TMDB_API_KEY", "")
    if not key:
        return JSONResponse({"error": "TMDB not configured"}, status_code=503)
    params = dict(request.query_params)
    params["api_key"] = key
    params.setdefault("language", "en-US")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{_TMDB_BASE}/{path}", params=params)
        return JSONResponse(resp.json(), status_code=resp.status_code)
    except httpx.HTTPError:
        return JSONResponse({"error": "TMDB fetch failed"}, status_code=502)
