from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import boto3
import structlog
from app.config import get_settings
from botocore.exceptions import ClientError

logger = structlog.get_logger()


def _ddb_safe(value: Any) -> Any:
    """Make a value safe for DynamoDB (boto3 resource): recursively convert every
    float to Decimal. A single stray float (e.g. an fps like 23.976) otherwise
    fails the whole write with 'Float types are not supported'."""
    return json.loads(json.dumps(value), parse_float=Decimal)


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
    hdr_manifest_url: str | None = None,
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
    if hdr_manifest_url:
        expr += ", hdr_manifest_url = :h"
        values[":h"] = hdr_manifest_url
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
        values[":mi"] = _ddb_safe(media_info)
    _table().update_item(
        Key={"id": movie_id},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        # Don't resurrect a row deleted/canceled mid-job: marking ready would
        # otherwise upsert a row missing title/genre/year/rating.
        ConditionExpression="attribute_exists(id)",
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


def clear_cancel(movie_id: str) -> None:
    """Drop a stale cancel flag so a re-enqueued job starts fresh. Without this, a
    leftover ``cancel_requested`` from a prior session makes the worker immediately
    cancel the re-enqueued job — and cancel-cleanup deletes its source."""
    try:
        _table().update_item(
            Key={"id": movie_id},
            UpdateExpression="REMOVE cancel_requested",
            ConditionExpression="attribute_exists(id)",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("catalog_clear_cancel_failed", movie_id=movie_id, error=str(exc))


def list_processing_ids() -> list[str]:
    """IDs of every row still marked 'processing'. Used by the startup reconciler to
    recover jobs whose SQS message was lost when the ephemeral queue restarted."""
    ids: list[str] = []
    try:
        table = _table()
        kwargs: dict = {
            "FilterExpression": "#s = :s",
            "ExpressionAttributeNames": {"#s": "status"},
            "ExpressionAttributeValues": {":s": "processing"},
            "ProjectionExpression": "id",
        }
        while True:
            resp = table.scan(**kwargs)
            ids.extend(it["id"] for it in resp.get("Items", []) if "id" in it)
            lek = resp.get("LastEvaluatedKey")
            if not lek:
                break
            kwargs["ExclusiveStartKey"] = lek
    except Exception as exc:  # noqa: BLE001
        logger.warning("catalog_list_processing_failed", error=str(exc))
    return ids


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
            # Never recreate a row that was deleted mid-job: an unguarded update_item
            # upserts, leaving a phantom {id, progress, stage} row with no required
            # fields that then 500s the catalog listing.
            ConditionExpression="attribute_exists(id)",
        )
    except Exception as exc:  # noqa: BLE001 - progress is non-critical
        # ConditionalCheckFailedException just means the row is gone (canceled/deleted).
        logger.warning("catalog_progress_update_skipped", movie_id=movie_id, error=str(exc))


def update_interp(movie_id: str, status: str, detail: str | None = None) -> None:
    """Best-effort update of the frame-interpolation lifecycle field
    (queued|processing|done|skipped|failed) + an optional human reason. Never
    raises; a missing row (canceled/deleted) is silently ignored."""
    try:
        expr = "SET interp_status = :s"
        values: dict[str, object] = {":s": status}
        if detail is not None:
            expr += ", interp_detail = :d"
            values[":d"] = detail
        else:
            expr += " REMOVE interp_detail"
        _table().update_item(
            Key={"id": movie_id},
            UpdateExpression=expr,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_exists(id)",
        )
    except Exception as exc:  # noqa: BLE001 - interp state is non-critical
        logger.warning("catalog_interp_update_skipped", movie_id=movie_id, error=str(exc))


def mark_ready(
    movie_id: str,
    manifest_url: str,
    dash_url: str,
    duration: str | None = None,
    thumbnail_url: str | None = None,
    hdr_manifest_url: str | None = None,
    audio_tracks: list | None = None,
    subtitle_tracks: list | None = None,
    media_info: dict | None = None,
) -> None:
    """Flip the catalog entry for this job to ready and attach its manifest URLs,
    duration, thumbnail, audio/subtitle track lists and media metadata.

    ``hdr_manifest_url`` (the HEVC master) is set only for HDR videos; the player
    switches to it when the browser can decode HEVC.

    The movie id equals the job id (see upload-api), so a completed transcode
    maps directly onto its catalog row.
    """
    kw = {
        "duration": duration,
        "thumbnail_url": thumbnail_url,
        "hdr_manifest_url": hdr_manifest_url,
        "audio_tracks": audio_tracks,
        "subtitle_tracks": subtitle_tracks,
        "media_info": media_info,
    }
    try:
        _update(movie_id, manifest_url, dash_url, **kw)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code == "ResourceNotFoundException":
            _ensure_table()
            _update(movie_id, manifest_url, dash_url, **kw)
            return
        if code == "ConditionalCheckFailedException":
            # Row was deleted/canceled before this job finished — nothing to mark.
            logger.warning("catalog_mark_ready_skipped_row_gone", movie_id=movie_id)
            return
        raise
