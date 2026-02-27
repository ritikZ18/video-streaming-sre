from __future__ import annotations

from typing import BinaryIO

from fastapi import HTTPException, UploadFile, status

from app.config import get_settings


MP4_SIGNATURES = (b"ftypisom", b"ftypmp4", b"ftypM4V")
MKV_SIGNATURE = b"matroska"


def validate_extension(filename: str) -> None:
    settings = get_settings()
    if "." not in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have an extension",
        )
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in settings.allowed_extension_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extension .{ext} is not allowed",
        )


def _read_magic(fileobj: BinaryIO, max_bytes: int = 16) -> bytes:
    current_pos = fileobj.tell()
    header = fileobj.read(max_bytes)
    fileobj.seek(current_pos)
    return header


def validate_magic_bytes(upload: UploadFile) -> None:
    """Validate container format via magic bytes for mp4/mov/mkv."""
    header = _read_magic(upload.file)
    if any(sig in header for sig in MP4_SIGNATURES):
        return
    if MKV_SIGNATURE in header:
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported video container format",
    )


def validate_size(upload: UploadFile) -> None:
    settings = get_settings()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    # Read file once into memory for size check; for a portfolio project this is acceptable.
    upload.file.seek(0)
    data = upload.file.read()
    size = len(data)
    if size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Uploaded file exceeds maximum size",
        )
    # Reset file handle so downstream can re-read from start.
    upload.file.seek(0)


