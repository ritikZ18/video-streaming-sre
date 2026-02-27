from fastapi import APIRouter, status

from app.metrics.qoe import (
    QOE_BITRATE_SWITCHES,
    QOE_ERRORS,
    QOE_REBUFFER_DURATION,
    QOE_REBUFFER_EVENTS,
    QOE_SESSIONS_NO_REBUFFER,
    QOE_SESSIONS_TOTAL,
    QOE_SESSION_HEARTBEATS,
    QOE_STARTUP,
)
from app.models.beacon_schema import BeaconBatch


router = APIRouter(prefix="/api/v1/beacon", tags=["beacon"])


@router.post(
    "/",
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_beacon(batch: BeaconBatch) -> dict[str, str]:
    seen_rebuffer = False

    for event in batch.events:
        if event.event == "startup" and event.startup_ms is not None:
            QOE_STARTUP.observe(event.startup_ms / 1000.0)
        elif event.event == "rebuffer" and event.rebuffer_ms is not None:
            QOE_REBUFFER_EVENTS.labels(
                region=batch.region or "unknown",
                content_id=batch.content_id or "unknown",
            ).inc()
            QOE_REBUFFER_DURATION.observe(event.rebuffer_ms / 1000.0)
            seen_rebuffer = True
        elif event.event == "bitrate_switch":
            QOE_BITRATE_SWITCHES.inc()
        elif event.event == "error" and event.error_type:
            QOE_ERRORS.labels(error_type=event.error_type).inc()
        elif event.event == "heartbeat":
            QOE_SESSION_HEARTBEATS.inc()

    QOE_SESSIONS_TOTAL.inc()
    if not seen_rebuffer:
        QOE_SESSIONS_NO_REBUFFER.inc()

    return {"status": "accepted"}


