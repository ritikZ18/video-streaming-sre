from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import time

from fastapi import APIRouter, Body, Depends, File, HTTPException, Response, UploadFile, status

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


# Audio containers accepted for an attached external track (content-type → ext).
_AUDIO_EXT = {
    "audio/mpeg": "mp3", "audio/mp3": "mp3",
    "audio/mp4": "m4a", "audio/x-m4a": "m4a", "audio/m4a": "m4a",
    "audio/aac": "aac", "audio/aacp": "aac",
    "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav",
    "audio/ogg": "ogg", "audio/opus": "opus", "audio/x-opus+ogg": "opus",
    "audio/flac": "flac", "audio/x-flac": "flac",
}
_AUDIO_EXTS = ("mp3", "m4a", "aac", "wav", "ogg", "opus", "flac")


@router.post("/{movie_id}/audio", status_code=status.HTTP_202_ACCEPTED)
def attach_audio(
    movie_id: str,
    file: UploadFile = File(...),  # noqa: B008
    _admin: str = Depends(require_admin),
) -> dict[str, str]:
    """Attach an external audio track to a (silent) title and re-transcode so the
    new segments carry it. The file is stored beside the title's segments so it
    survives re-transcodes; the worker muxes it only when the source has no
    embedded audio. Requires the original video source to still be in S3."""
    settings = get_settings()
    _require_movie(movie_id)
    src = s3.first_key(settings.s3_video_bucket, f"{movie_id}/")
    if not src:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Original source is no longer stored — re-upload to add audio.",
        )
    ctype = (file.content_type or "").lower().split(";")[0]
    ext = _AUDIO_EXT.get(ctype)
    if ext is None:  # fall back to the filename extension
        fname = (file.filename or "").lower()
        ext = next((e for e in _AUDIO_EXTS if fname.endswith(f".{e}")), None)
    if ext is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio must be mp3, m4a, aac, wav, ogg, opus or flac",
        )
    data = file.file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    # Keep exactly one attached track: drop any prior external_audio.* first.
    s3.delete_prefix(settings.s3_segments_bucket, f"{movie_id}/external_audio.")
    s3.upload_bytes(
        settings.s3_segments_bucket,
        f"{movie_id}/external_audio.{ext}",
        data,
        ctype or "application/octet-stream",
    )
    catalog.update_fields(
        movie_id,
        {"has_external_audio": True, "status": "processing", "progress": 0, "stage": "queued"},
    )
    filename = src.split("/", 1)[1] if "/" in src else src
    # Fast path: re-package the existing renditions with the new audio (no video
    # re-encode). The worker falls back to a full transcode if the persisted
    # renditions aren't available (e.g. a title encoded before this existed).
    queue.enqueue_transcode_job(
        job_id=movie_id, s3_key=src, filename=filename, mode="remux_audio"
    )
    return {"job_id": movie_id, "status": "queued"}


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


@router.post("/{movie_id}/interpolate", status_code=status.HTTP_202_ACCEPTED)
def interpolate_movie(
    movie_id: str,
    target_fps: int | None = Body(default=None, embed=True),
    _admin: str = Depends(require_admin),
) -> dict[str, str]:
    """Add a NON-destructive smoothed (frame-interpolated) rendition to a title.

    The interpolated ladder is published to a separate ``{id}/interp/`` prefix and
    linked onto the title via ``interp_manifest_url``; the original manifest and the
    title's ``ready`` status are left untouched, so it stays watchable throughout and
    the player exposes the result as a "Smooth" toggle. Requires the source still in
    S3. The worker re-checks the guardrails and skips (recording a reason) if the
    source is already high-fps / too tall / too long / HDR."""
    settings = get_settings()
    if not settings.interp_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Frame interpolation is disabled on this server.",
        )
    _require_movie(movie_id)
    key = s3.first_key(settings.s3_video_bucket, f"{movie_id}/")
    if not key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Original source is no longer stored — re-upload to smooth it.",
        )
    target = target_fps or settings.interp_default_target_fps
    if target < 1 or target > settings.interp_max_target_fps:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"target_fps must be between 1 and {settings.interp_max_target_fps}",
        )
    filename = key.split("/", 1)[1] if "/" in key else key
    # Non-destructive: the title stays ready/playable; only the interp lifecycle
    # moves. The worker sets interp_manifest_url when the variant is published.
    catalog.update_fields(
        movie_id,
        {
            "interp_requested": True, "interp_target_fps": target,
            "interp_status": "queued",
        },
    )
    queue.enqueue_transcode_job(
        job_id=movie_id, s3_key=key, filename=filename,
        interp=True, interp_target_fps=target, interp_variant=True,
    )
    return {"job_id": movie_id, "status": "queued"}


@router.post("/{movie_id}/interpolate-copy", status_code=status.HTTP_202_ACCEPTED)
def interpolate_copy(
    movie_id: str,
    target_fps: int | None = Body(default=None, embed=True),
    height: int | None = Body(default=None, embed=True),
    _admin: str = Depends(require_admin),
) -> dict[str, str]:
    """Create a NEW title that is a frame-interpolated (and optionally downscaled)
    copy of an existing one — e.g. a 4K source smoothed into a 1080p·60fps copy for
    a fraction of the disk/time. The original is untouched; the copy re-uses the
    same source object in S3 and gets its own ladder."""
    settings = get_settings()
    if not settings.interp_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Frame interpolation is disabled on this server.",
        )
    src_movie = catalog.get(movie_id)
    if src_movie is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Movie not found")
    key = s3.first_key(settings.s3_video_bucket, f"{movie_id}/")
    if not key:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Original source is no longer stored — re-upload to make a copy.",
        )
    target = target_fps or settings.interp_default_target_fps
    if target < 1 or target > settings.interp_max_target_fps:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"target_fps must be between 1 and {settings.interp_max_target_fps}",
        )
    if height is not None and (height < 144 or height > settings.interp_max_height):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"height must be between 144 and {settings.interp_max_height}",
        )

    new_id = str(uuid4())
    label = f"{height}p{target}" if height else f"{target}fps"
    new_movie = Movie(
        id=new_id,
        created_at=datetime.now(tz=timezone.utc),
        status="processing",
        title=f"{src_movie.title} · {label}",
        description=src_movie.description,
        genre=src_movie.genre,
        year=src_movie.year,
        rating=src_movie.rating,
        duration=src_movie.duration,
        tag=src_movie.tag,
        poster_url=src_movie.poster_url,
        backdrop_url=src_movie.backdrop_url,
        visibility=src_movie.visibility,
        interp_requested=True,
        interp_target_fps=target,
        interp_status="queued",
        progress=0,
        stage="queued",
    )
    catalog.save(new_movie)
    filename = key.split("/", 1)[1] if "/" in key else key
    queue.enqueue_transcode_job(
        job_id=new_id, s3_key=key, filename=filename,
        interp=True, interp_target_fps=target, interp_height=height,
    )
    return {"job_id": new_id, "status": "queued"}
