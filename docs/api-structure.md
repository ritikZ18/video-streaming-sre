# API Structure — Mini Video Streaming Platform

The **actual** HTTP surface as implemented. The Apple-TV UI talks to three
services: **Upload API** (ingest + catalog + job status), **Beacon** (QoE
telemetry), and the **Origin** (manifests + segments).

Interactive docs: `http://localhost:8000/docs` and `http://localhost:8001/docs`.

---

## 1. Upload API — `http://localhost:8000`

The Upload API owns both ingestion **and** the movie catalog (backed by
DynamoDB). There is no separate catalog service.

### 1.1 `POST /api/v1/upload`

Ingest a video and register a catalog entry.

- **Content-Type**: `multipart/form-data`
- **Fields**:
  - `file` (required) — video file (`mp4`, `mov`, `mkv`), up to 500 MB.
  - `title`, `genre`, `year` (int), `rating`, `duration`, `tag`, `description`
    — all **optional**; sensible defaults are applied (e.g. `title` = filename).
- **`202 Accepted`**:
  ```json
  { "job_id": "b1c2...", "status": "queued" }
  ```
- Side effects: raw file → `raw-uploads` bucket; catalog row created with
  `status=processing` and `id == job_id`; SQS transcode job enqueued.

### 1.2 `GET /api/v1/jobs/{job_id}`

Job status, derived from the presence of `master.m3u8` in the segments bucket.

- **`200 OK`**:
  ```json
  { "job_id": "b1c2...", "status": "processing", "stream_url": null }
  ```
  When complete:
  ```json
  {
    "job_id": "b1c2...",
    "status": "complete",
    "stream_url": "http://localhost:8080/hls/b1c2.../master.m3u8"
  }
  ```
  `status` ∈ `queued | processing | complete`.

### 1.3 `GET /api/v1/movies/`

List the catalog (used by the home + browse pages).

- **`200 OK`**:
  ```json
  {
    "movies": [
      {
        "id": "b1c2...",
        "title": "Aurora Drift",
        "description": "…",
        "genre": "Sci-Fi",
        "year": 2025,
        "rating": "PG-13",
        "duration": "1h 58m",
        "tag": "Trending",
        "status": "ready",
        "manifest_url": "http://localhost:8080/hls/b1c2.../master.m3u8",
        "dash_url": "http://localhost:8080/hls/b1c2.../manifest.mpd",
        "created_at": "2026-07-19T12:00:00Z"
      }
    ]
  }
  ```

### 1.4 `POST /api/v1/movies/`

Register a movie directly (admin flow — e.g. HLS assets that already exist).

- **Request** (`application/json`):
  ```json
  {
    "title": "Neon Ronin",
    "genre": "Action",
    "year": 2025,
    "rating": "R",
    "duration": "1h 58m",
    "tag": "New Release",
    "description": "…",
    "manifest_url": "http://localhost:8080/hls/neon-ronin/master.m3u8"
  }
  ```
- **`201 Created`** → the created `Movie` (with `id`, `created_at`,
  `status: "ready"`).

### 1.5 Health & metrics

- `GET /health` → `{ "status": "ok" }`
- `GET /ready` → `{ "status": "ready" }` (or `"degraded"` if storage is unreachable)
- `GET /metrics` → Prometheus text (`upload_api_http_requests_total`, …)

### `Movie` object

| Field | Type | Notes |
|---|---|---|
| `id` | string | equals `job_id` for pipeline uploads |
| `title`, `genre`, `rating` | string | |
| `year` | int | |
| `description`, `duration`, `tag` | string \| null | |
| `status` | `processing` \| `ready` | |
| `manifest_url`, `dash_url` | string \| null | set by the worker when ready |
| `created_at` | ISO-8601 | |

---

## 2. Beacon API — `http://localhost:8001`

### 2.1 `POST /api/v1/beacon/`

Ingest a batch of QoE events from the player.

- **Request** (`application/json`):
  ```json
  {
    "session_id": "sess-123",
    "content_id": "b1c2...",
    "region": "us-east-1",
    "player_version": "1.0.0",
    "events": [
      { "event": "startup", "timestamp": "2026-07-19T12:00:00Z", "startup_ms": 1700 },
      { "event": "rebuffer", "timestamp": "2026-07-19T12:00:25Z", "rebuffer_ms": 900 },
      { "event": "bitrate_switch", "timestamp": "2026-07-19T12:00:30Z", "current_bitrate_kbps": 800 },
      { "event": "error", "timestamp": "2026-07-19T12:00:40Z", "error_type": "manifestLoadError" },
      { "event": "heartbeat", "timestamp": "2026-07-19T12:00:45Z" }
    ]
  }
  ```
  `event` ∈ `startup | rebuffer | bitrate_switch | error | heartbeat`.
- **`202 Accepted`**:
  ```json
  { "status": "accepted" }
  ```
- Converts events into Prometheus metrics (startup histogram, rebuffer
  events/duration, bitrate switches, errors, session counters).

### 2.2 Health & metrics

- `GET /health` → `{ "status": "ok" }`
- `GET /metrics` → Prometheus text (`qoe_*`)

---

## 3. Origin — `http://localhost:8080`

Serves the manifests and CMAF segments the worker wrote to the segments bucket
(path-style S3 proxy + cache).

- `GET /hls/{job_id}/master.m3u8` — HLS master playlist
- `GET /hls/{job_id}/manifest.mpd` — DASH manifest (same segments)
- `GET /hls/{job_id}/media_*.m3u8`, `.../*.m4s` — media playlists + CMAF segments
- `GET /health` → `{ "status": "ok" }`
- Nginx stub metrics on `:9113/nginx_status`

CORS (`Access-Control-Allow-Origin: *`) and per-content-type cache TTLs
(short for manifests, long for immutable segments) are set at the origin.

---

## 4. How the UI maps onto these APIs

- **Home / Browse**: `GET /api/v1/movies/` → hero + genre rows.
- **Upload page**: `POST /api/v1/upload` (file + metadata), then poll
  `GET /api/v1/jobs/{job_id}` until `complete`.
- **Play**: navigate to `/player?url=<manifest_url>`; hls.js loads it from the
  **origin**; the player POSTs QoE events to `POST /api/v1/beacon/`.
