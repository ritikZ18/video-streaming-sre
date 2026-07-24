from io import BytesIO

import pytest
from app.utils.validators import validate_extension, validate_magic_bytes
from fastapi import HTTPException, UploadFile


def test_validate_extension_allows_mp4() -> None:
    validate_extension("video.mp4")


def test_validate_extension_rejects_txt() -> None:
    with pytest.raises(HTTPException):
        validate_extension("notes.txt")


def test_validate_magic_bytes_accepts_mp4_signature() -> None:
    fileobj = BytesIO(b"ftypmp4" + b"\x00" * 8)
    upload = UploadFile(filename="video.mp4", file=fileobj)
    validate_magic_bytes(upload)

