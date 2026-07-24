from __future__ import annotations

import boto3
import structlog
from app.config import get_settings
from botocore.exceptions import ClientError

logger = structlog.get_logger()


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
    movie_id: str,
    manifest_url: str,
    dash_url: str,
    duration: str | None = None,
    thumbnail_url: str | None = None,
    audio_tracks: list | None = None,
    subtitle_tracks: list | None = None,
    media_info: dict | None = None,
) -> None:
    expr = "SET #s = :s, manifest_url = :m, dash_url = :d, #p = :p, #stg = :stg"
    names = {"#s": "status", "#p": "progress", "#stg": "stage"}
    values: dict[str, object] = {
        ":s": "ready",
        ":m": manifest_url,
        ":d": dash_url,
        ":p": 100,
        ":stg": "ready",
    }
    if duration:
        # "duration" is a DynamoDB reserved word, so alias it.
        expr += ", #dur = :dur"
        names["#dur"] = "duration"
        values[":dur"] = duration
    if thumbnail_url:
        expr += ", thumbnail_url = :t"
        values[":t"] = thumbnail_url
    if audio_tracks is not None:
        expr += ", audio_tracks = :au"
        values[":au"] = audio_tracks
    if subtitle_tracks is not None:
        expr += ", subtitle_tracks = :su"
        values[":su"] = subtitle_tracks
    if media_info is not None:
        expr += ", media_info = :mi"
        values[":mi"] = media_info
    _table().update_item(
        Key={"id": movie_id},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def is_canceled(movie_id: str) -> bool:
    """True if the upload-api flagged this job for cancellation. Best-effort:
    any read error is treated as 'not canceled' so a transient blip never aborts
    a healthy transcode."""
    try:
        item = _table().get_item(Key={"id": movie_id}).get("Item") or {}
        return bool(item.get("cancel_requested"))
    except Exception:  # noqa: BLE001
        return False


def delete_row(movie_id: str) -> None:
    """Remove a catalog row (used after a cancellation so it leaves the grid)."""
    try:
        _table().delete_item(Key={"id": movie_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning("catalog_delete_failed", movie_id=movie_id, error=str(exc))


def update_progress(movie_id: str, pct: int, stage: str | None = None) -> None:
    """Best-effort transcode progress (0-100) + current stage. Never raises."""
    try:
        expr = "SET #p = :p"
        names = {"#p": "progress"}
        values: dict[str, object] = {":p": pct}
        if stage is not None:
            expr += ", #stg = :st"
            names["#stg"] = "stage"
            values[":st"] = stage
        _table().update_item(
            Key={"id": movie_id},
            UpdateExpression=expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
    except Exception as exc:  # noqa: BLE001 - progress is non-critical
        logger.warning("catalog_progress_update_failed", movie_id=movie_id, error=str(exc))


def mark_ready(
    movie_id: str,
    manifest_url: str,
    dash_url: str,
    duration: str | None = None,
    thumbnail_url: str | None = None,
    audio_tracks: list | None = None,
    subtitle_tracks: list | None = None,
    media_info: dict | None = None,
) -> None:
    """Flip the catalog entry for this job to ready and attach its manifest URLs,
    duration, thumbnail, audio/subtitle track lists and media metadata.

    The movie id equals the job id (see upload-api), so a completed transcode
    maps directly onto its catalog row.
    """
    kw = {
        "duration": duration,
        "thumbnail_url": thumbnail_url,
        "audio_tracks": audio_tracks,
        "subtitle_tracks": subtitle_tracks,
        "media_info": media_info,
    }
    try:
        _update(movie_id, manifest_url, dash_url, **kw)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
            _ensure_table()
            _update(movie_id, manifest_url, dash_url, **kw)
            return
        raise
