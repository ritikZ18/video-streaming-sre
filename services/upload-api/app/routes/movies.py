from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List
from uuid import uuid4

from fastapi import APIRouter, status

from app.models.schemas import Movie, MovieCreate, MovieList


router = APIRouter(prefix="/api/v1/movies", tags=["movies"])

_MOVIES: Dict[str, Movie] = {}


@router.get("/", response_model=MovieList)
def list_movies() -> MovieList:
    return MovieList(movies=list(_MOVIES.values()))


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=Movie,
)
def create_movie(payload: MovieCreate) -> Movie:
    movie_id = str(uuid4())
    movie = Movie(
        id=movie_id,
        created_at=datetime.now(tz=timezone.utc),
        **payload.model_dump(),
    )
    _MOVIES[movie_id] = movie
    return movie


