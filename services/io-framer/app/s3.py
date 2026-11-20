from __future__ import annotations

import boto3

from app.config import get_settings


def _client():
    s = get_settings()
    return boto3.client(
        "s3", region_name=s.aws_region, endpoint_url=s.s3_endpoint_url
    )


def download(bucket: str, key: str, dest: str) -> None:
    _client().download_file(bucket, key, dest)


def upload(bucket: str, key: str, src: str, content_type: str = "video/mp4") -> None:
    _client().upload_file(src, bucket, key, ExtraArgs={"ContentType": content_type})
