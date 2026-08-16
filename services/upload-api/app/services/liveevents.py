from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import boto3
from app.config import get_settings
from app.models.schemas import LiveEvent
from botocore.client import BaseClient
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def _resource():
    settings = get_settings()
    return boto3.resource(
        "dynamodb",
        region_name=settings.aws_region,
        endpoint_url=settings.dynamodb_endpoint_url,
    )


def _table():
    return _resource().Table(get_settings().live_events_table)


def _ensure_table() -> None:
    """Create the live-events table on demand (parity with the catalog/queue)."""
    settings = get_settings()
    resource = _resource()
    client: BaseClient = resource.meta.client
    try:
        client.describe_table(TableName=settings.live_events_table)
        return
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
            raise
    resource.create_table(
        TableName=settings.live_events_table,
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    client.get_waiter("table_exists").wait(TableName=settings.live_events_table)


def _to_item(event: LiveEvent) -> dict[str, Any]:
    # mode="json" turns every datetime into an ISO string and enums into plain
    # strings — both DynamoDB-safe. Drop None so DynamoDB doesn't reject nulls.
    item = event.model_dump(mode="json")
    return {k: v for k, v in item.items() if v is not None}


def _to_event(item: dict[str, Any]) -> LiveEvent:
    # Pydantic re-parses ISO strings back into datetimes; ints come back as
    # Decimal from DynamoDB, which Pydantic coerces to int for max_height.
    return LiveEvent(**dict(item))


def save(event: LiveEvent) -> None:
    try:
        _table().put_item(Item=_to_item(event))
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
            _ensure_table()
            _table().put_item(Item=_to_item(event))
            return
        raise


def list_all() -> list[LiveEvent]:
    try:
        response = _table().scan()
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
            _ensure_table()
            return []
        raise
    events: list[LiveEvent] = []
    for item in response.get("Items", []):
        try:
            events.append(_to_event(item))
        except Exception as exc:  # noqa: BLE001 - one bad row must not sink the list
            logger.warning("skipping malformed live-event row %s: %s", item.get("id"), exc)
    events.sort(key=lambda e: e.created_at, reverse=True)
    return events


def get(event_id: str) -> LiveEvent | None:
    try:
        item = _table().get_item(Key={"id": event_id}).get("Item")
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
            return None
        raise
    return _to_event(item) if item else None


def find_by_stream_key(stream_key: str) -> LiveEvent | None:
    """Resolve an ingest event by its publish key (used to authorize a push).
    A full scan is fine — there are only a handful of live events at a time."""
    if not stream_key:
        return None
    for event in list_all():
        if event.stream_key and event.stream_key == stream_key:
            return event
    return None


def delete_row(event_id: str) -> None:
    _table().delete_item(Key={"id": event_id})


def update_fields(event_id: str, fields: dict[str, Any]) -> None:
    """Update the given attributes; skips None, aliases every name so reserved
    words (status/state/…) are safe, and ISO-encodes datetime values."""
    items: list[tuple[str, Any]] = []
    for key, value in fields.items():
        if value is None:
            continue
        items.append((key, value.isoformat() if isinstance(value, datetime) else value))
    if not items:
        return
    names = {f"#k{i}": k for i, (k, _) in enumerate(items)}
    values = {f":v{i}": v for i, (_, v) in enumerate(items)}
    expr = "SET " + ", ".join(f"#k{i} = :v{i}" for i in range(len(items)))
    _table().update_item(
        Key={"id": event_id},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ConditionExpression="attribute_exists(id)",
    )
