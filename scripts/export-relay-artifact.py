#!/usr/bin/env python3
"""Package an already-transcoded HLS/CMAF directory for Laptop B."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import tarfile
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("movie_id", help="Stable movie identifier used by the relay")
    parser.add_argument("source_dir", type=Path, help="Directory containing packaged HLS/CMAF files")
    parser.add_argument("output", type=Path, help="Output .tar.gz bundle")
    parser.add_argument("--duration-seconds", type=float, required=True)
    parser.add_argument("--expires-at", required=True, help="UTC ISO-8601 expiration timestamp")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    if not source_dir.is_dir():
        raise SystemExit(f"source directory does not exist: {source_dir}")
    if not args.movie_id.replace("-", "").replace("_", "").isalnum():
        raise SystemExit("movie_id may contain only letters, numbers, '-' and '_'")

    files = sorted(path for path in source_dir.rglob("*") if path.is_file())
    if not files:
        raise SystemExit("source directory contains no files")

    objects = []
    for path in files:
        relative = path.relative_to(source_dir).as_posix()
        content_type = mimetypes.guess_type(relative)[0] or "application/octet-stream"
        objects.append(
            {
                "path": relative,
                "sha256": sha256(path),
                "content_type": content_type,
            }
        )

    manifest = {
        "movie_id": args.movie_id,
        "format": "hls-cmaf",
        "duration_seconds": args.duration_seconds,
        "expires_at": args.expires_at,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "objects": objects,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.output, "w:gz") as archive:
        manifest_bytes = json.dumps(manifest, sort_keys=True, indent=2).encode()
        info = tarfile.TarInfo("artifact.json")
        info.size = len(manifest_bytes)
        archive.addfile(info, fileobj=__import__("io").BytesIO(manifest_bytes))
        for path in files:
            archive.add(path, arcname=path.relative_to(source_dir).as_posix(), recursive=False)

    print(f"created {args.output} ({len(objects)} objects)")


if __name__ == "__main__":
    main()