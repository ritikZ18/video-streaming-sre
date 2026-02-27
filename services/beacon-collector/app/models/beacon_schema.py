from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BeaconEvent(BaseModel):
    event: Literal["startup", "rebuffer", "bitrate_switch", "error", "heartbeat"]
    timestamp: datetime
    startup_ms: int | None = None
    rebuffer_ms: int | None = None
    current_bitrate_kbps: int | None = None
    error_type: str | None = None


class BeaconBatch(BaseModel):
    session_id: str
    content_id: str | None = None
    region: str | None = None
    player_version: str | None = None
    events: list[BeaconEvent] = Field(default_factory=list)


