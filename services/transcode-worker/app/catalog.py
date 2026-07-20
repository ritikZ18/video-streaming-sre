from __future__ import annotations

import boto3
from botocore.exceptions import ClientError

from app.config import get_settings


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
    settings = get_settings()
    resource = _resource()
    client = resource.meta.client
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


def _update(
    movie_id: str, manifest_url: str, dash_url: str, duration: str | None = None
) -> None:
    expr = "SET #s = :s, manifest_url = :m, dash_url = :d"
    names = {"#s": "status"}
    values: dict[str, str] = {":s": "ready", ":m": manifest_url, ":d": dash_url}
    if duration:
        # "duration" is a DynamoDB reserved word, so alias it.
        expr += ", #dur = :dur"
        names["#dur"] = "duration"
        values[":dur"] = duration
    _table().update_item(
        Key={"id": movie_id},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def mark_ready(
    movie_id: str,
    manifest_url: str,
    dash_url: str,
    duration: str | None = None,
) -> None:
    """Flip the catalog entry for this job to ready and attach manifest URLs
    (and the probed duration, if available).

    The movie id equals the job id (see upload-api), so a completed transcode
    maps directly onto its catalog row.
    """
    try:
        _update(movie_id, manifest_url, dash_url, duration)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
            _ensure_table()
            _update(movie_id, manifest_url, dash_url, duration)
            return
        raise
