from __future__ import annotations

from typing import BinaryIO

from app.config import get_settings
from fastapi import HTTPException, UploadFile, status

# Every mp4/mov/m4v begins with an ISO-BMFF `ftyp` box at byte 4. The major
# brand that follows varies widely (isom, mp41/42, iso5/6, dash, avc1, av01,
# qt, M4V …), so we match the box marker itself rather than a fixed brand list —
# otherwise valid files (e.g. AV1/HDR mp4s branded iso5) get rejected with a 400.
ISO_FTYP = b"ftyp"
MKV_SIGNATURE = b"matroska"
EBML_SIGNATURE = b"\x1aE\xdf\xa3"  # Matroska / WebM container header (bytes 0-3)


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
    # Read enough to reach the Matroska "doctype": the EBML header id is at
    # bytes 0-3 but the "matroska" string sits ~24 bytes in, so a 16-byte read
    # used to reject valid .mkv files with a 400.
    header = _read_magic(upload.file, 64)
    if ISO_FTYP in header[:16]:  # any mp4 / mov / m4v brand
        return
    if header.startswith(EBML_SIGNATURE) or MKV_SIGNATURE in header:
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported video container format",
    )


def validate_size(upload: UploadFile) -> None:
    settings = get_settings()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    # Measure size via seek (do NOT read the whole file into memory).
    upload.file.seek(0, 2)  # seek to end
    size = upload.file.tell()
    upload.file.seek(0)  # reset for downstream streaming upload
    if size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Uploaded file exceeds maximum size",
        )


