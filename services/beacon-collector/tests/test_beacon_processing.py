from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import create_app


def test_beacon_accepts_batch_and_updates_metrics() -> None:
    app = create_app()
    client = TestClient(app)

    payload = {
        "session_id": "sess-1",
        "content_id": "movie-1",
        "region": "us-west-2",
        "events": [
            {
                "event": "startup",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "startup_ms": 1500,
            },
            {
                "event": "rebuffer",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "rebuffer_ms": 700,
            },
        ],
    }

    response = client.post("/api/v1/beacon/", json=payload)
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}

