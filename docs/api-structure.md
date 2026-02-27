## API Structure – Mini Video Streaming Platform

This document outlines the **high‑level API design** for the platform. It is meant as a planning/specification doc you can point to in interviews and implement incrementally.

The APIs are grouped by service:

- **Upload API** – ingest raw videos and track transcode jobs.
- **Catalog API** – manage movie metadata (used by the Apple TV–style UI).
- **Beacon API** – collect quality‑of‑experience telemetry from the player.

---

## 1. Upload API

**Base URL (local)**: `http://localhost:8000`

### 1.1 `POST /upload`

**Description**: Upload a new video for ingestion.

- **Request**:
  - Content‑Type: `multipart/form-data`
  - Fields:
    - `file` (required) – video file, max ~500MB.
    - `title` (required) – string.
    - `description` (optional) – string.
    - `genre` (required) – string (e.g. `Action`, `Sci-Fi`).
    - `year` (required) – int.
    - `rating` (required) – e.g. `PG-13`.
    - `tag` (optional) – e.g. `Trending`, `New Release`.
- **Response** `202 Accepted`:
  ```json
  {
    "job_id": "uuid",
    "movie_id": "uuid",
    "status": "queued"
  }
  ```

### 1.2 `GET /jobs/{job_id}`

**Description**: Check the status of a transcode job.

- **Response** `200 OK`:
  ```json
  {
    "job_id": "uuid",
    "movie_id": "uuid",
    "status": "queued | processing | completed | failed",
    "error_message": null
  }
  ```

### 1.3 Health & Metrics

- `GET /health` – basic health probe (no heavy dependencies).
- `GET /ready` – readiness probe (checks queue, storage access).
- `GET /metrics` – Prometheus metrics endpoint.

---

## 2. Catalog API

**Base URL (local)**: e.g. `http://localhost:8002` (you can choose).

This API front‑ends the **Postgres catalog database** and is what the **React UI** uses for:

- Home page carousels.
- Search.
- Adding movies via the “Add Movie” panel.

### 2.1 `GET /catalog/movies`

**Description**: List movies with optional filters and search.

- **Query params**:
  - `genre` (optional) – filter by genre.
  - `tag` (optional) – filter by tag (e.g. `Trending`).
  - `q` (optional) – search in title/genre.
  - `limit` (optional, default 50).
- **Response** `200 OK`:
  ```json
  [
    {
      "id": "uuid",
      "title": "Quantum Horizon",
      "description": "A physicist discovers a portal...",
      "genre": "Sci-Fi",
      "year": 2025,
      "rating": "PG-13",
      "duration": "2h 14m",
      "tag": "Trending",
      "manifest_url": "https://cdn.example.com/movies/123/master.m3u8",
      "thumbnail_url": "https://cdn.example.com/movies/123/cover.jpg"
    }
  ]
  ```

### 2.2 `GET /catalog/movies/{id}`

**Description**: Get full details for a single movie.

Used by the UI when opening the **Movie Detail** view.

### 2.3 `POST /catalog/movies`

**Description**: Add a new movie to the catalog.

This is the **“one way to add movies to the database”** that the UI can call directly. It is perfect when:

- You already have a manifest URL (e.g. test content).
- You want to demo the product without running the full transcode pipeline.

- **Request**:
  ```json
  {
    "title": "Neon Ronin",
    "description": "In a cyberpunk Tokyo...",
    "genre": "Action",
    "year": 2025,
    "rating": "R",
    "duration": "1h 58m",
    "tag": "New Release",
    "manifest_url": "https://cdn.example.com/movies/neon-ronin/master.m3u8",
    "thumbnail_url": "https://cdn.example.com/movies/neon-ronin/cover.jpg"
  }
  ```

- **Response** `201 Created`:
  ```json
  {
    "id": "uuid",
    "title": "Neon Ronin",
    "genre": "Action",
    "year": 2025,
    "rating": "R",
    "duration": "1h 58m",
    "tag": "New Release",
    "manifest_url": "...",
    "thumbnail_url": "...",
    "created_at": "2025-01-01T12:00:00Z"
  }
  ```

The **React UI** “Add Movie Panel” can simply:

1. Collect this JSON via a form.
2. Call `POST /catalog/movies`.
3. On success, insert the new movie into local state so it appears instantly in rows.

---

## 3. Beacon API

**Base URL (local)**: `http://localhost:8001`

### 3.1 `POST /beacon`

**Description**: Ingest QoE events from the player.

- **Request**:
  ```json
  {
    "session_id": "uuid",
    "movie_id": "uuid",
    "events": [
      {
        "type": "startup",
        "timestamp_ms": 0,
        "startup_time_ms": 1700
      },
      {
        "type": "rebuffer",
        "timestamp_ms": 25000,
        "duration_ms": 900
      },
      {
        "type": "bitrate_change",
        "timestamp_ms": 30000,
        "from_kbps": 2500,
        "to_kbps": 800
      }
    ],
    "client": {
      "platform": "web",
      "app_version": "1.0.0",
      "device": "desktop"
    }
  }
  ```

- **Response** `202 Accepted`:
  ```json
  { "status": "accepted" }
  ```

The service:

- Validates payloads via Pydantic models.
- Converts events into Prometheus metrics:
  - Startup histogram.
  - Rebuffer counters.
  - Session heartbeats.

### 3.2 Health & Metrics

- `GET /health`
- `GET /metrics`

---

## 4. How the Apple TV–Style UI Fits In

The UI example you provided maps cleanly onto these APIs:

- **Home page load**:
  - Calls `GET /catalog/movies?tag=Trending` for hero + trending row.
  - Calls `GET /catalog/movies?genre=Action`, etc., for each genre row.
- **Search bar**:
  - Debounced calls to `GET /catalog/movies?q=query`.
- **Add Movie Panel**:
  - On submit, calls `POST /catalog/movies` with metadata and manifest URL.
- **Play button**:
  - Uses `manifest_url` from the movie to initialize hls.js and start playback.
  - Sends QoE events to `POST /beacon`.

This gives you a **clean, interview‑friendly story**:

> “The Apple TV–style UI only talks to three services: Catalog for metadata, Upload for ingestion, and Beacon for telemetry. Everything else (transcoding, storage, CDN) is behind those APIs.”

