## Architecture – Mini Video Streaming Platform + SRE

This document describes the **system architecture** for the mini video streaming platform, focusing on:

- Components and responsibilities.
- Data flow for upload, playback, and telemetry.
- Where observability and SRE concepts are attached.

---

## 1. Components

### 1.1 Upload API

- **Tech**: Python 3.12, FastAPI, Uvicorn.
- **Responsibilities**:
  - Accept authenticated video uploads (multipart/form‑data).
  - Validate file type, size, and basic metadata.
  - Store raw file in an object store (e.g. S3 `raw-uploads` bucket).
  - Enqueue a **transcode job** with job ID and metadata to a message queue (e.g. SQS).
  - Expose job status via `GET /jobs/{id}`.
  - Expose health endpoints (`/health`, `/ready`) and **Prometheus metrics**.

### 1.2 Transcode Worker

- **Tech**: Python worker with FFmpeg.
- **Responsibilities**:
  - Poll the transcode queue (SQS) for jobs.
  - Download raw video from the `raw-uploads` bucket.
  - Run FFmpeg to:
    - Generate multiple renditions (e.g. 360p/720p/1080p).
    - Package into HLS (master manifest + per‑variant manifests + segments).
  - Write manifests and segments into a **segments bucket**.
  - Update the **catalog database** with:
    - Playback URLs (e.g. `https://cdn.example.com/movies/{id}/master.m3u8`).
    - Technical metadata (duration, resolutions).
  - Emit metrics:
    - Job duration, success/failure count.
    - Queue depth and processing lag.

### 1.3 Origin Gateway

- **Tech**: Nginx (or another high‑performance HTTP proxy).
- **Responsibilities**:
  - Serve HLS manifests and segments from the segments bucket (as an origin).
  - Add **caching headers** (Cache‑Control) for efficient CDN behavior.
  - Add security headers (HSTS, CSP, X‑Frame‑Options).
  - Expose Nginx metrics (via exporter) to Prometheus:
    - Request rates, status code breakdown, latency histograms.

In production, origin typically sits behind a **CDN (CloudFront)** for global caching. In local dev, you can use Nginx directly.

### 1.4 Web Player UI

- **Tech**: React + hls.js (or native HLS), styled to look like **Apple TV**.
- **Responsibilities**:
  - Display:
    - Hero banner with spotlight content.
    - Horizontal carousels for genres, trending, etc.
  - Fetch movie catalog data from the **Catalog API**.
  - Start playback using the HLS manifest from the catalog.
  - Send **beacons** to the Beacon Collector:
    - Startup time, rebuffer events, bitrates, heartbeats.
  - Provide an **“Add Movie”** panel that:
    - Collects metadata (title, genre, year, rating, description, tag).
    - Option 1: Calls Upload API to upload a file.
    - Option 2: Calls Catalog API to register a movie with an existing manifest.

### 1.5 Catalog Service (Database + API)

- **Tech**: FastAPI + Postgres (or another relational DB).
- **Responsibilities**:
  - Store **movie metadata**:
    - `id`, `title`, `description`, `genre`, `year`, `rating`, `duration`, `tag`.
    - `manifest_url`, `thumbnail_url`, `created_at`, `updated_at`.
  - Provide APIs used by the player:
    - `GET /catalog/movies` – list with filters/search.
    - `POST /catalog/movies` – create a new record.
    - `GET /catalog/movies/{id}` – detailed view.
  - Optionally, support simple lists like “Trending” or “New Release” using tags.

### 1.6 Beacon Collector

- **Tech**: FastAPI.
- **Responsibilities**:
  - Receive QoE events from the web player:
    - `startup_time`, `rebuffer_events`, `session_id`, `movie_id`, `bitrate_changes`, etc.
  - Validate payloads and transform into **Prometheus metrics**:
    - Histograms (startup duration).
    - Counters (rebuffer events, sessions).
  - Provide metrics for SLOs related to **user experience**.

### 1.7 Observability Stack

- **Prometheus** – metrics database and alerting rules evaluation.
- **Alertmanager** – routing and deduplicating alerts (Slack, PagerDuty).
- **Grafana** – dashboards for:
  - Backend health (Upload API, Transcoder, Origin).
  - Pipeline health (queue metrics, job success/fail).
  - QoE (startup time, rebuffering).
  - SLOs and error budget burn.

---

## 2. Data Flows

### 2.1 Upload Flow

1. Client (UI or script) calls **Upload API**:
   - `POST /upload` with video file + metadata.
2. Upload API:
   - Validates input.
   - Streams file to `raw-uploads` bucket.
   - Enqueues job to SQS with `job_id` and metadata.
3. Transcode Worker:
   - Dequeues job, downloads raw file.
   - Runs FFmpeg to create HLS packages.
   - Stores `master.m3u8` and segments in `segments` bucket.
   - Writes or updates movie record in **catalog DB**.
4. Client polls `GET /jobs/{id}` or catalog APIs to see if playback is ready.

**SRE Hooks**:

- Metrics on upload rate, validation failures, and queue lag.
- Alerts if transcode queue backs up or DLQ contains messages.

### 2.2 Playback Flow

1. Client opens the Player UI.
2. The Player calls:
   - `GET /catalog/movies` to render hero and carousels.
3. User clicks **Play**:
   - Player uses `manifest_url` from the catalog (e.g. CloudFront URL).
4. hls.js requests:
   - Master manifest → variant manifest → segments.
   - All requests go to **CDN → Origin → Segments bucket**.

**SRE Hooks**:

- Nginx / origin metrics:
  - `origin_http_requests_total`, `origin_request_duration_seconds_bucket`, etc.
- SLOs:
  - Manifest availability and latency.
  - Segment latency.

### 2.3 Telemetry (QoE) Flow

1. The player measures video startup time, rebuffer events, and bitrates.
2. Player sends batched beacons to **Beacon Collector**:
   - `POST /beacon` with JSON payload.
3. Beacon Collector transforms events into Prometheus metrics:
   - `qoe_startup_duration_seconds_bucket`.
   - `qoe_rebuffer_events_total`.
   - `qoe_session_heartbeats_total`.
4. Prometheus scrapes `/metrics` and recording rules compute:
   - P95 startup time.
   - Rebuffer ratio.
   - Error budget burn for QoE‑related SLOs.

---

## 3. SRE & Observability Anchors

This architecture is specifically designed to highlight SRE concepts:

- **Golden signals**:
  - Latency, traffic, errors, and saturation for each service.
- **SLOs & SLIs**:
  - Availability and latency for manifest/segment requests.
  - QoE metrics (startup time, rebuffering).
- **Burn‑rate alerts**:
  - Fast‑burn (1h/6h) for acute outages.
  - Slow‑burn (longer windows) for gradual degradation.
- **Runbooks**:
  - For high manifest error rate, high transcode queue depth, origin 5xx spikes, etc.
- **Chaos**:
  - Kill origin, inject latency, or corrupt segments to prove alerts and SLOs work.

---

## 4. Environments & Deployment (Planned)

For now, this document focuses on architecture; full deployment (Terraform, ECS, CloudFront, etc.) will come later. The intended pattern is:

- **Local**:
  - Docker Compose + LocalStack S3/SQS + local Postgres.
  - All services on a single machine for fast iteration.
- **Staging / Prod** (future):
  - ECS Fargate services for Upload API, Transcoder, Origin, Beacon Collector.
  - Managed Postgres (RDS) for the catalog.
  - S3 buckets and CloudFront for video delivery.
  - Prometheus/Grafana/Alertmanager running as separate ECS services or hosted solutions.

The important part for interviews is that you can explain **how each component scales** and **what failures look like** (e.g. transcode worker stuck, origin slow, bucket permission issues), then tie that back to metrics and runbooks.

