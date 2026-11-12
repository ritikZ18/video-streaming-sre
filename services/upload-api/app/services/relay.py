from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import tarfile
from datetime import datetime, timezone

import httpx
from botocore.client import BaseClient

from app.config import get_settings
from app.services.s3 import _client


def _object_client() -> BaseClient:
    return _client()


def publish_movie(movie_id: str, duration_seconds: float, expires_at: str) -> dict[str, object]:
    settings = get_settings()
    if not settings.relay_server_url or not settings.relay_ingress_token:
        raise ValueError("RELAY_SERVER_URL and RELAY_INGRESS_TOKEN must be configured")

    client = _object_client()
    objects: list[dict[str, str]] = []
    payloads: list[tuple[str, bytes]] = []
    pages = client.get_paginator("list_objects_v2").paginate(
        Bucket=settings.s3_segments_bucket, Prefix=f"{movie_id}/"
    )
    for page in pages:
        for entry in page.get("Contents", []):
            key = entry["Key"]
            relative = key.removeprefix(f"{movie_id}/")
            if not relative or relative == "ready.json":
                continue
            data = client.get_object(Bucket=settings.s3_segments_bucket, Key=key)["Body"].read()
            digest = hashlib.sha256(data).hexdigest()
            content_type = mimetypes.guess_type(relative)[0] or "application/octet-stream"
            objects.append({"path": relative, "sha256": digest, "content_type": content_type})
            payloads.append((relative, data))
    if not objects:
        raise ValueError("No packaged HLS/CMAF objects found for this title")

    manifest = {
        "movie_id": movie_id,
        "format": "hls-cmaf",
        "duration_seconds": duration_seconds,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "objects": objects,
    }
    bundle = io.BytesIO()
    with tarfile.open(fileobj=bundle, mode="w:gz") as archive:
        raw_manifest = json.dumps(manifest, sort_keys=True, indent=2).encode()
        info = tarfile.TarInfo("artifact.json")
        info.size = len(raw_manifest)
        archive.addfile(info, io.BytesIO(raw_manifest))
        for relative, data in payloads:
            info = tarfile.TarInfo(relative)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    bundle.seek(0)
    response = httpx.post(
        f"{settings.relay_server_url.rstrip('/')}/v1/artifacts",
        headers={"Authorization": f"Bearer {settings.relay_ingress_token}"},
        files={"bundle": ("artifact.tar.gz", bundle.getvalue(), "application/gzip")},
        timeout=1800,
    )
    response.raise_for_status()
    return response.json()