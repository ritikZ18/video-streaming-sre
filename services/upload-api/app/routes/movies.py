from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import time

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

from app.auth import require_admin
from app.config import get_settings
from app.models.schemas import Movie, MovieCreate, MovieList, MoviePatch
from app.services import catalog, queue, s3

router = APIRouter(prefix="/api/v1/movies", tags=["movies"])


@router.get("/", response_model=MovieList)
def list_movies() -> MovieList:
    return MovieList(movies=catalog.list_all())


@router.get("/{movie_id}", response_model=Movie)
def get_movie(movie_id: str) -> Movie:
    movie = catalog.get(movie_id)
    if movie is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    return movie


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=Movie,
)
def create_movie(payload: MovieCreate, _admin: str = Depends(require_admin)) -> Movie:
    movie = Movie(
        id=str(uuid4()),
        created_at=datetime.now(tz=timezone.utc),
        status="ready",
        **payload.model_dump(),
    )
    catalog.save(movie)
    return movie


@router.delete("/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_movie(movie_id: str, _admin: str = Depends(require_admin)) -> Response:
    """Delete an uploaded movie: its HLS/DASH segments, its raw source upload,
    and its catalog row (admin only). The movie id is the job id, which is also
    the S3 key prefix for both buckets."""
    settings = get_settings()
    if catalog.get(movie_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    s3.delete_prefix(settings.s3_segments_bucket, f"{movie_id}/")
    s3.delete_prefix(settings.s3_video_bucket, f"{movie_id}/")
    catalog.delete_row(movie_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _require_movie(movie_id: str) -> Movie:
    movie = catalog.get(movie_id)
    if movie is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    return movie


@router.patch("/{movie_id}", response_model=Movie)
def patch_movie(
    movie_id: str, patch: MoviePatch, _admin: str = Depends(require_admin)
) -> Movie:
    """Edit a title's metadata / visibility (admin). Only provided fields change."""
    _require_movie(movie_id)
    catalog.update_fields(movie_id, patch.model_dump(exclude_unset=True))
    return _require_movie(movie_id)


_IMAGE_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/avif": "avif"}


@router.post("/{movie_id}/artwork", response_model=Movie)
def upload_artwork(
    movie_id: str,
    file: UploadFile = File(...),  # noqa: B008
    kind: str = "poster",
    _admin: str = Depends(require_admin),
) -> Movie:
    """Upload custom artwork. kind='poster' (2:3 → poster_url) or 'backdrop'
    (16:9 → backdrop_url). Stored beside the title's segments, served by origin,
    and preserved across re-transcodes. ``?v=`` busts the cache when replaced."""
    settings = get_settings()
    _require_movie(movie_id)
    ctype = (file.content_type or "").lower().split(";")[0]
    if ctype not in _IMAGE_EXT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Artwork must be a JPG, PNG, WebP or AVIF image",
        )
    data = file.file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    name = "backdrop" if kind == "backdrop" else "poster"
    key = f"{movie_id}/{name}.{_IMAGE_EXT[ctype]}"
    s3.upload_bytes(settings.s3_segments_bucket, key, data, ctype)
    url = f"{settings.origin_base_url}/hls/{key}?v={int(time.time())}"
    field = "backdrop_url" if kind == "backdrop" else "poster_url"
    catalog.update_fields(movie_id, {field: url})
    return _require_movie(movie_id)


@router.post("/{movie_id}/retranscode", status_code=status.HTTP_202_ACCEPTED)
def retranscode(movie_id: str, _admin: str = Depends(require_admin)) -> dict[str, str]:
    """Re-run the transcode from the original source (admin): flip the row back to
    processing and re-enqueue. The source must still be in S3. Custom artwork is
    kept (the worker never writes poster_url/backdrop_url); old segments are simply
    overwritten by the new run."""
    settings = get_settings()
    _require_movie(movie_id)
    key = s3.first_key(settings.s3_video_bucket, f"{movie_id}/")
    if not key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Original source is no longer stored — re-upload to re-transcode.",
        )
    filename = key.split("/", 1)[1] if "/" in key else key
    catalog.update_fields(movie_id, {"status": "processing", "progress": 0, "stage": "queued"})
    queue.enqueue_transcode_job(job_id=movie_id, s3_key=key, filename=filename)
    return {"job_id": movie_id, "status": "queued"}
