from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.auth import require_admin
from app.config import get_settings
from app.models.schemas import Movie, MovieCreate, MovieList
from app.services import catalog, s3

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
