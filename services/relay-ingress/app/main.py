from __future__ import annotations

import hashlib
import json
import re
import secrets
import tarfile
from pathlib import PurePosixPath
from tempfile import SpooledTemporaryFile
from typing import BinaryIO

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, File, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    aws_region: str = "us-east-1"
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin123"
    s3_endpoint_url: str = "http://minio:9000"
    relay_bucket: str = "streamsre-hls-segments"
    relay_ingress_token: str = Field(min_length=32)
    relay_max_bundle_mb: int = Field(default=10240, ge=1, le=102400)


settings = Settings()
app = FastAPI(title="StreamSRE Relay Ingress", version="1.0.0")
MOVIE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,95}$")
CHUNK_SIZE = 1024 * 1024


class ArtifactObject(BaseModel):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_type: str = "application/octet-stream"


class ArtifactManifest(BaseModel):
    movie_id: str
    format: str = "hls-cmaf"
    duration_seconds: float = Field(gt=0)
    expires_at: str
    objects: list[ArtifactObject] = Field(min_length=1)


def _client() -> BaseClient:
    session = boto3.session.Session(
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    return session.client("s3", endpoint_url=settings.s3_endpoint_url)


def _safe_path(path: str) -> str:
    candidate = PurePosixPath(path)
    if (
        not path
        or path.startswith("/")
        or "\\" in path
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or str(candidate) != path
    ):
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    return path


def _authorized(authorization: str | None) -> None:
    expected = f"Bearer {settings.relay_ingress_token}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid relay credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _copy_and_hash(source: BinaryIO) -> tuple[SpooledTemporaryFile[bytes], str, int]:
    staged = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    digest = hashlib.sha256()
    size = 0
    while chunk := source.read(CHUNK_SIZE):
        size += len(chunk)
        digest.update(chunk)
        staged.write(chunk)
    staged.seek(0)
    return staged, digest.hexdigest(), size


def _validate_manifest(raw: bytes) -> ArtifactManifest:
    try:
        manifest = ArtifactManifest.model_validate_json(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid artifact manifest") from exc
    if not MOVIE_ID.fullmatch(manifest.movie_id) or manifest.format != "hls-cmaf":
        raise HTTPException(status_code=400, detail="Unsupported artifact metadata")
    seen: set[str] = set()
    for item in manifest.objects:
        item.path = _safe_path(item.path)
        if item.path in seen or item.path == "artifact.json":
            raise HTTPException(status_code=400, detail="Duplicate artifact path")
        seen.add(item.path)
    return manifest


def _ensure_bucket(client: BaseClient) -> None:
    try:
        client.head_bucket(Bucket=settings.relay_bucket)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchBucket"}:
            client.create_bucket(Bucket=settings.relay_bucket)
        else:
            raise


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/artifacts", status_code=status.HTTP_201_CREATED)
def ingest_artifact(
    authorization: str | None = Header(default=None),
    bundle: UploadFile = File(...),
) -> dict[str, str | int]:
    _authorized(authorization)
    if bundle.content_type not in {"application/gzip", "application/x-gzip", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="Artifact bundle must be gzip tar")

    manifest: ArtifactManifest | None = None
    staged: list[tuple[ArtifactObject, SpooledTemporaryFile[bytes]]] = []
    total_size = 0
    try:
        with tarfile.open(fileobj=bundle.file, mode="r|gz") as archive:
            first = archive.next()
            if first is None or first.name != "artifact.json" or not first.isfile():
                raise HTTPException(status_code=400, detail="artifact.json must be the first file")
            manifest = _validate_manifest(archive.extractfile(first).read())  # type: ignore[union-attr]
            expected = {item.path: item for item in manifest.objects}
            for member in iter(archive.next, None):
                if not member.isfile() or member.name not in expected or member.name in {item.path for item, _ in staged}:
                    raise HTTPException(status_code=400, detail="Bundle contains unexpected files")
                item = expected[member.name]
                staged_file, digest, size = _copy_and_hash(archive.extractfile(member))  # type: ignore[arg-type]
                total_size += size
                if total_size > settings.relay_max_bundle_mb * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="Artifact bundle is too large")
                if not secrets.compare_digest(digest, item.sha256):
                    raise HTTPException(status_code=400, detail=f"Checksum mismatch: {item.path}")
                staged.append((item, staged_file))
    except tarfile.TarError as exc:
        raise HTTPException(status_code=400, detail="Invalid gzip tar artifact") from exc
    finally:
        bundle.file.close()

    assert manifest is not None
    if {item.path for item, _ in staged} != {item.path for item in manifest.objects}:
        raise HTTPException(status_code=400, detail="Artifact bundle is incomplete")

    client = _client()
    staging_prefix = f"relay-staging/{manifest.movie_id}/"
    public_prefix = f"relay/{manifest.movie_id}/"
    try:
        _ensure_bucket(client)
        for item, staged_file in staged:
            client.upload_fileobj(
                staged_file,
                settings.relay_bucket,
                staging_prefix + item.path,
                ExtraArgs={"ContentType": item.content_type},
            )
            staged_file.close()
        for item in manifest.objects:
            client.copy_object(
                Bucket=settings.relay_bucket,
                CopySource={"Bucket": settings.relay_bucket, "Key": staging_prefix + item.path},
                Key=public_prefix + item.path,
                MetadataDirective="COPY",
            )
        marker = manifest.model_dump_json().encode()
        client.put_object(
            Bucket=settings.relay_bucket,
            Key=public_prefix + "ready.json",
            Body=marker,
            ContentType="application/json",
        )
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(status_code=502, detail="Failed to publish relay artifact") from exc

    return {"movie_id": manifest.movie_id, "status": "ready", "objects": len(staged)}