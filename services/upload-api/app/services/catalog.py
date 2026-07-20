from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from app.config import get_settings
from app.models.schemas import Movie


def _resource():
    settings = get_settings()
    return boto3.resource(
        "dynamodb",
        region_name=settings.aws_region,
        endpoint_url=settings.dynamodb_endpoint_url,
    )


def _table():
    return _resource().Table(get_settings().dynamodb_table)


def _ensure_table() -> None:
    """Create the catalog table on demand (parity with lazy S3/SQS creation)."""
    settings = get_settings()
    resource = _resource()
    client: BaseClient = resource.meta.client
    try:
        client.describe_table(TableName=settings.dynamodb_table)
        return
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
            raise
    resource.create_table(
        TableName=settings.dynamodb_table,
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    client.get_waiter("table_exists").wait(TableName=settings.dynamodb_table)


def _to_item(movie: Movie) -> dict[str, Any]:
    item = movie.model_dump()
    item["created_at"] = movie.created_at.isoformat()
    # DynamoDB rejects None; drop null attributes.
    return {k: v for k, v in item.items() if v is not None}


def _to_movie(item: dict[str, Any]) -> Movie:
    data = dict(item)
    # DynamoDB returns numbers as Decimal; coerce the int fields.
    for key in ("year", "progress"):
        if isinstance(data.get(key), Decimal):
            data[key] = int(data[key])
    return Movie(**data)


def save(movie: Movie) -> None:
    try:
        _table().put_item(Item=_to_item(movie))
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
            _ensure_table()
            _table().put_item(Item=_to_item(movie))
            return
        raise


def list_all() -> list[Movie]:
    try:
        response = _table().scan()
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
            _ensure_table()
            return []
        raise
    items = response.get("Items", [])
    movies = [_to_movie(i) for i in items]
    # Newest first.
    movies.sort(key=lambda m: m.created_at, reverse=True)
    return movies


def get(movie_id: str) -> Movie | None:
    item = _table().get_item(Key={"id": movie_id}).get("Item")
    return _to_movie(item) if item else None


def mark_ready(movie_id: str, manifest_url: str, dash_url: str) -> None:
    """Flip a processing entry to ready and attach its manifest URLs."""
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


# Convenience for building a processing entry at upload time.
def new_processing_movie(**fields: Any) -> Movie:
    fields.setdefault("created_at", datetime.now())
    return Movie(status="processing", **fields)
