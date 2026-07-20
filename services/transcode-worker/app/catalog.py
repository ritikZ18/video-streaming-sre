from __future__ import annotations

import boto3
from botocore.client import BaseClient

from app.config import get_settings


def _table():
    settings = get_settings()
    resource = boto3.resource(
        "dynamodb",
        region_name=settings.aws_region,
        endpoint_url=settings.dynamodb_endpoint_url,
    )
    return resource.Table(settings.dynamodb_table)


def mark_ready(movie_id: str, manifest_url: str, dash_url: str) -> None:
    """Flip the catalog entry for this job to ready and attach manifest URLs.

    The movie id equals the job id (see upload-api), so a completed transcode
    maps directly onto its catalog row.
    """
    _table().update_item(
        Key={"id": movie_id},
        UpdateExpression="SET #s = :s, manifest_url = :m, dash_url = :d",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "ready",
            ":m": manifest_url,
            ":d": dash_url,
        },
    )
