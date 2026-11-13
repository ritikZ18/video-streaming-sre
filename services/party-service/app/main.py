from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    aws_region: str = "us-east-1"
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin123"
    dynamodb_endpoint_url: str = "http://dynamodb-local:8000"
    party_table: str = "streamsre-parties"
    party_admin_token: str = Field(min_length=32)
    admin_username: str = Field(min_length=1)
    admin_password: str = Field(min_length=1)
    party_max_participants: int = Field(default=20, ge=2, le=100)


settings = Settings()
app = FastAPI(title="StreamSRE Party Service", version="1.0.0")
connections: dict[str, set[WebSocket]] = defaultdict(set)
participant_meta: dict[str, dict[WebSocket, dict[str, Any]]] = defaultdict(dict)
room_events: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=500))
room_end_tasks: dict[str, asyncio.Task[None]] = {}


def record_event(room_id: str, kind: str, **detail: Any) -> None:
    room_events[room_id].append({"timestamp": time.time(), "type": kind, **detail})


class CreateRoom(BaseModel):
    movie_id: str = Field(min_length=3, max_length=96, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(min_length=1, max_length=160)
    starts_at: datetime | None = None
    duration_seconds: int = Field(ge=1, le=86_400)


def table():
    resource = boto3.resource(
        "dynamodb",
        region_name=settings.aws_region,
        endpoint_url=settings.dynamodb_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    return resource.Table(settings.party_table)


def ensure_table() -> None:
    client = table().meta.client
    try:
        client.describe_table(TableName=settings.party_table)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
            raise
        client.create_table(
            TableName=settings.party_table,
            KeySchema=[{"AttributeName": "room_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "room_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def encode_session(room_id: str, movie_id: str, viewer_id: str) -> str:
    payload = {"room": room_id, "movie": movie_id, "viewer": viewer_id, "exp": int(time.time()) + 21_600}
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(settings.party_admin_token.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{signature}"


def decode_session(token: str) -> dict[str, Any] | None:
    try:
        raw, signature = token.split(".", 1)
        expected = hmac.new(settings.party_admin_token.encode(), raw.encode(), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(signature, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        return payload if int(payload["exp"]) >= int(time.time()) else None
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def bearer_token(authorization: str | None) -> str:
    return authorization[7:] if authorization and authorization.startswith("Bearer ") else ""


def require_admin(authorization: str | None) -> None:
    bearer = f"Bearer {settings.party_admin_token}"
    basic = "Basic " + base64.b64encode(
        f"{settings.admin_username}:{settings.admin_password}".encode()
    ).decode()
    if not authorization or not any(
        secrets.compare_digest(authorization, expected) for expected in (bearer, basic)
    ):
        raise HTTPException(status_code=401, detail="Party admin authorization required")


def room_item(room_id: str) -> dict[str, Any] | None:
    return table().get_item(Key={"room_id": room_id}).get("Item")


def room_has_ended(item: dict[str, Any]) -> bool:
    if item.get("state") == "ended":
        return True
    try:
        return bool(item.get("ends_at")) and time.time() >= float(item["ends_at"])
    except (TypeError, ValueError):
        return False


async def mark_room_ended(room_id: str) -> None:
    item = room_item(room_id)
    if not item or item.get("state") == "ended":
        return
    ended_at = int(time.time())
    table().update_item(
        Key={"room_id": room_id},
        UpdateExpression="SET #s = :s, ended_at = :e, playing = :p, position_seconds = :d",
        ExpressionAttributeNames={"#s": "state"},
        ExpressionAttributeValues={":s": "ended", ":e": ended_at, ":p": False, ":d": item.get("duration_seconds", 0)},
    )
    record_event(room_id, "ended")
    await broadcast(room_id, {"type": "ended", "ended_at": ended_at})


async def wait_for_room_end(room_id: str, ends_at: float) -> None:
    try:
        await asyncio.sleep(max(0, ends_at - time.time()))
        await mark_room_ended(room_id)
    finally:
        room_end_tasks.pop(room_id, None)


def schedule_room_end(item: dict[str, Any]) -> None:
    room_id = str(item.get("room_id", ""))
    if not room_id or room_has_ended(item) or room_id in room_end_tasks:
        return
    try:
        ends_at = float(item["ends_at"])
    except (KeyError, TypeError, ValueError):
        return
    room_end_tasks[room_id] = asyncio.create_task(wait_for_room_end(room_id, ends_at))


def public_room(item: dict[str, Any]) -> dict[str, Any]:
    room = {key: item[key] for key in ("room_id", "movie_id", "title", "state", "starts_at", "ends_at", "duration_seconds", "position_seconds", "playing", "version", "created_at", "ended_at") if key in item}
    if room_has_ended(item):
        room.update(state="ended", playing=False, position_seconds=item.get("duration_seconds", item.get("position_seconds", 0)), server_time=time.time())
        room["participants"] = len(connections.get(str(item.get("room_id")), set()))
        room["ready_participants"] = sum(1 for meta in participant_meta.get(str(item.get("room_id")), {}).values() if meta.get("ready"))
        return jsonable_encoder(room)
    starts_at = str(item.get("starts_at", ""))
    if item.get("state") != "ended" and starts_at:
        try:
            start_epoch = datetime.fromisoformat(starts_at.replace("Z", "+00:00")).timestamp()
            if time.time() >= start_epoch:
                room.update(state="live", playing=True, position_seconds=max(0, time.time() - start_epoch), server_time=time.time())
        except ValueError:
            pass
    room["participants"] = len(connections.get(str(item.get("room_id")), set()))
    room["ready_participants"] = sum(1 for meta in participant_meta.get(str(item.get("room_id")), {}).values() if meta.get("ready"))
    return jsonable_encoder(room)


async def broadcast(room_id: str, message: dict[str, Any]) -> None:
    stale: list[WebSocket] = []
    for socket in connections[room_id]:
        try:
            await socket.send_json(message)
        except Exception:
            stale.append(socket)
    for socket in stale:
        connections[room_id].discard(socket)


@app.on_event("startup")
async def startup() -> None:
    ensure_table()
    for item in table().scan(Limit=100).get("Items", []):
        if room_has_ended(item) and item.get("state") != "ended":
            await mark_room_ended(str(item["room_id"]))
        else:
            schedule_room_end(item)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/rooms", status_code=201)
async def create_room(request: CreateRoom, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(authorization)
    # A fixed-width, cryptographically random code is easy to type on a TV or
    # phone. Conditional insertion makes the already unlikely collision safe.
    room_id = ""
    host_token = secrets.token_urlsafe(32)
    for _ in range(8):
        room_id = f"{secrets.randbelow(10_000_000_000):010d}"
        starts_at = request.starts_at.isoformat() if request.starts_at else datetime.now().astimezone().isoformat()
        start_epoch = datetime.fromisoformat(starts_at.replace("Z", "+00:00")).timestamp()
        item = {
            "room_id": room_id,
            "movie_id": request.movie_id,
            "title": request.title,
            "state": "scheduled" if request.starts_at else "live",
            "starts_at": starts_at,
            "duration_seconds": request.duration_seconds,
            # DynamoDB rejects Python floats; whole-second epoch precision is
            # sufficient for a watch-party curtain time.
            "ends_at": int(start_epoch) + request.duration_seconds,
            "position_seconds": 0,
            "playing": False,
            "version": 0,
            "host_hash": digest(host_token),
            "created_at": int(time.time()),
        }
        try:
            table().put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(room_id)",
            )
            schedule_room_end(item)
            return {"code": room_id, "host_token": host_token, "room": public_room(item)}
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
    raise HTTPException(status_code=503, detail="Could not allocate a party code")


@app.get("/v1/rooms/{room_id}")
def get_room(room_id: str) -> dict[str, Any]:
    item = room_item(room_id)
    if not item:
        raise HTTPException(status_code=404, detail="Room not found")
    return public_room(item)


@app.post("/v1/rooms/{room_id}/join")
def join_room(room_id: str) -> dict[str, Any]:
    item = room_item(room_id)
    if not item or room_has_ended(item):
        raise HTTPException(status_code=404, detail="Room not found")
    viewer_id = secrets.token_urlsafe(12)
    return {"access_token": encode_session(room_id, item["movie_id"], viewer_id), "viewer_id": viewer_id, "room": public_room(item)}


@app.get("/v1/authorize", status_code=204)
def authorize_media(movie_id: str, authorization: str | None = Header(default=None)) -> None:
    session = decode_session(bearer_token(authorization))
    if not session or not secrets.compare_digest(str(session.get("movie", "")), movie_id):
        raise HTTPException(status_code=401, detail="Valid watch-party session required")
    item = room_item(str(session.get("room", "")))
    if not item or room_has_ended(item) or item.get("movie_id") != movie_id:
        raise HTTPException(status_code=403, detail="Party access expired")
    starts_at = str(item.get("starts_at", ""))
    try:
        if starts_at and time.time() < datetime.fromisoformat(starts_at.replace("Z", "+00:00")).timestamp():
            raise HTTPException(status_code=403, detail="Screening has not started")
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid screening schedule")


@app.get("/v1/admin/rooms")
def list_rooms(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(authorization)
    items = table().scan(Limit=100).get("Items", [])
    rooms = sorted((public_room(item) for item in items), key=lambda room: int(room.get("created_at", 0)), reverse=True)
    for room in rooms:
        room_id = str(room["room_id"])
        room["participant_details"] = list(participant_meta.get(room_id, {}).values())
        room["recent_events"] = list(room_events.get(room_id, ()))[-100:]
    return {"rooms": rooms, "generated_at": time.time()}


@app.post("/v1/admin/rooms/{room_id}/end")
async def end_room(room_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(authorization)
    if not room_item(room_id):
        raise HTTPException(status_code=404, detail="Room not found")
    task = room_end_tasks.pop(room_id, None)
    if task:
        task.cancel()
    await mark_room_ended(room_id)
    return {"status": "ended"}


@app.websocket("/ws/rooms/{room_id}")
async def room_socket(websocket: WebSocket, room_id: str, name: str = "Guest") -> None:
    item = room_item(room_id)
    protocols = [value.strip() for value in websocket.headers.get("sec-websocket-protocol", "").split(",")]
    token = protocols[1] if len(protocols) == 2 and protocols[0] == "party-v1" else ""
    session = decode_session(token)
    if not item or room_has_ended(item) or not session or session.get("room") != room_id or session.get("movie") != item.get("movie_id"):
        await websocket.close(code=1008)
        return
    if len(connections[room_id]) >= settings.party_max_participants:
        await websocket.close(code=1013)
        return
    await websocket.accept(subprotocol="party-v1")
    schedule_room_end(item)
    connections[room_id].add(websocket)
    forwarded_ip = websocket.headers.get("cf-connecting-ip") or websocket.headers.get("x-forwarded-for", "").split(",")[0].strip() or (websocket.client.host if websocket.client else "unknown")
    ip_hash = hmac.new(settings.party_admin_token.encode(), forwarded_ip.encode(), hashlib.sha256).hexdigest()[:12]
    participant_meta[room_id][websocket] = {"viewer_id": session["viewer"], "name": name[:40], "ready": False, "joined_at": time.time(), "ip_hash": ip_hash, "country": websocket.headers.get("cf-ipcountry", "—"), "drift_ms": 0, "bitrate_kbps": 0}
    record_event(room_id, "join", viewer_id=session["viewer"], name=name[:40])
    await websocket.send_json({"type": "room_state", "room": public_room(item)})
    await broadcast(room_id, {"type": "presence", "name": name, "count": len(connections[room_id])})
    try:
        while True:
            message = await websocket.receive_json()
            kind = message.get("type")
            if kind == "chat":
                text = str(message.get("text", "")).strip()[:1000]
                if text:
                    record_event(room_id, "chat", viewer_id=session["viewer"])
                    await broadcast(room_id, {"type": "chat", "name": name, "text": text})
            elif kind == "ready":
                participant_meta[room_id][websocket]["ready"] = bool(message.get("ready", True))
                record_event(room_id, "ready", viewer_id=session["viewer"], ready=bool(message.get("ready", True)))
                current = room_item(room_id) or item
                await broadcast(room_id, {"type": "room_state", "room": public_room(current)})
            elif kind == "heartbeat":
                participant_meta[room_id][websocket].update(last_seen=time.time(), drift_ms=max(-60_000, min(60_000, int(message.get("drift_ms", 0)))), bitrate_kbps=max(0, int(message.get("bitrate_kbps", 0))))
    except WebSocketDisconnect:
        connections[room_id].discard(websocket)
        participant_meta[room_id].pop(websocket, None)
        record_event(room_id, "leave", viewer_id=session["viewer"])
        await broadcast(room_id, {"type": "presence", "name": name, "count": len(connections[room_id])})
