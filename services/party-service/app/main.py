from __future__ import annotations

import hashlib
import json
import secrets
import time
from collections import defaultdict
from typing import Any

import boto3
from botocore.exceptions import ClientError
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
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
    party_max_participants: int = Field(default=20, ge=2, le=100)


settings = Settings()
app = FastAPI(title="StreamSRE Party Service", version="1.0.0")
connections: dict[str, set[WebSocket]] = defaultdict(set)


class CreateRoom(BaseModel):
    movie_id: str = Field(min_length=3, max_length=96, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(min_length=1, max_length=160)
    starts_at: str | None = None


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


def require_admin(authorization: str | None) -> None:
    expected = f"Bearer {settings.party_admin_token}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Party admin authorization required")


def room_item(room_id: str) -> dict[str, Any] | None:
    return table().get_item(Key={"room_id": room_id}).get("Item")


def public_room(item: dict[str, Any]) -> dict[str, Any]:
    return {key: item[key] for key in ("room_id", "movie_id", "title", "state", "starts_at", "position_seconds", "playing", "version") if key in item}


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
def startup() -> None:
    ensure_table()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/rooms", status_code=201)
def create_room(request: CreateRoom, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(authorization)
    room_id = secrets.token_urlsafe(9)
    invite_token = secrets.token_urlsafe(24)
    host_token = secrets.token_urlsafe(32)
    item = {
        "room_id": room_id,
        "movie_id": request.movie_id,
        "title": request.title,
        "state": "scheduled" if request.starts_at else "waiting",
        "starts_at": request.starts_at or "",
        "position_seconds": 0,
        "playing": False,
        "version": 0,
        "invite_hash": digest(invite_token),
        "host_hash": digest(host_token),
        "created_at": int(time.time()),
    }
    table().put_item(Item=item)
    return {"room_id": room_id, "invite_token": invite_token, "host_token": host_token, "room": public_room(item)}


@app.get("/v1/rooms/{room_id}")
def get_room(room_id: str, invite_token: str) -> dict[str, Any]:
    item = room_item(room_id)
    if not item or not secrets.compare_digest(invite_token, item.get("invite_hash", "")):
        raise HTTPException(status_code=404, detail="Room not found")
    return public_room(item)


@app.websocket("/ws/rooms/{room_id}")
async def room_socket(websocket: WebSocket, room_id: str, invite_token: str, name: str = "Guest") -> None:
    item = room_item(room_id)
    if not item or not secrets.compare_digest(invite_token, item.get("invite_hash", "")):
        await websocket.close(code=1008)
        return
    if len(connections[room_id]) >= settings.party_max_participants:
        await websocket.close(code=1013)
        return
    await websocket.accept()
    connections[room_id].add(websocket)
    await websocket.send_json({"type": "room_state", "room": public_room(item)})
    await broadcast(room_id, {"type": "presence", "name": name, "count": len(connections[room_id])})
    try:
        while True:
            message = await websocket.receive_json()
            kind = message.get("type")
            if kind == "chat":
                text = str(message.get("text", "")).strip()[:1000]
                if text:
                    await broadcast(room_id, {"type": "chat", "name": name, "text": text})
            elif kind == "playback":
                current = room_item(room_id) or item
                version = int(current.get("version", 0)) + 1
                update = {"position_seconds": max(0, float(message.get("position_seconds", 0))), "playing": bool(message.get("playing", False)), "version": version}
                table().update_item(Key={"room_id": room_id}, UpdateExpression="SET position_seconds = :p, playing = :l, #v = :v", ExpressionAttributeNames={"#v": "version"}, ExpressionAttributeValues={":p": update["position_seconds"], ":l": update["playing"], ":v": version})
                await broadcast(room_id, {"type": "playback", **update})
    except WebSocketDisconnect:
        connections[room_id].discard(websocket)
        await broadcast(room_id, {"type": "presence", "name": name, "count": len(connections[room_id])})