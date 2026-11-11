# Architecture — Mini Video Streaming Platform + SRE

This document describes the **system as it is actually built**: the components,
how a request flows through them, where local storage is provided by persistent
MinIO and DynamoDB containers,
and where the SRE/observability hooks attach.

For the full narrative design (goals, data model, decisions), see
[design.md](design.md). For endpoints, see [api-structure.md](api-structure.md).
For the Terraform + floci story, see [infra-floci.md](infra-floci.md).

---

## 1. High-level diagram

```mermaid
flowchart TD
    subgraph Browser
      UI["Next.js Apple-TV UI\n(hls.js player)"]
    end

    subgraph Services["Docker Compose services"]
      UP["upload-api\n:8000 (FastAPI)"]
      TW["transcode-worker\n(FFmpeg, queue consumer)"]
      OG["origin\n:8080 (Nginx)"]
      BC["beacon-collector\n:8001 (FastAPI)"]
    end

    subgraph Storage["Persistent Docker Compose storage"]
      S3RAW[("MinIO: raw-uploads")]
      S3SEG[("MinIO: hls-segments")]
      QUEUE[["DynamoDB: transcode queue"]]
      DDB[("DynamoDB: catalog")]
    end

    subgraph Obs["Observability"]
      PROM["Prometheus :9090"]
      GRAF["Grafana :3000"]
      AM["Alertmanager :9093"]
    end

    UI -- "upload (file+meta)" --> UP
    UI -- "GET /movies (catalog)" --> UP
    UI -- "QoE beacons" --> BC
    UI -- "HLS/DASH manifests + segments" --> OG

    UP -- "raw file" --> S3RAW
    UP -- "job msg" --> QUEUE
    UP -- "movie row (processing)" --> DDB

    QUEUE --> TW
    TW -- "download raw" --> S3RAW
    TW -- "CMAF + HLS + DASH" --> S3SEG
    TW -- "mark ready + manifest URLs" --> DDB

    OG -- "proxy + cache" --> S3SEG

    UP -- "/metrics" --> PROM
    TW -- "/metrics :9100" --> PROM
    BC -- "/metrics" --> PROM
    OG -- "nginx_status :9113" --> PROM
    PROM --> GRAF
    PROM --> AM
```

---

## 2. Components

| Component | Tech | Port(s) | Responsibility |
|---|---|---|---|
| **Web player** (`frontend/`) | Next.js 14, React, hls.js, Tailwind | 3001 | Public Apple-TV–style catalog UI + HLS playback + QoE beacons; login-gated `/admin` for uploads |
| **Upload API** (`services/upload-api`) | Python 3.12, FastAPI | 8000 | Validate + store uploads (S3), enqueue transcode jobs, own the catalog (DynamoDB), job status; **admin auth on write endpoints** |
| **Transcode Worker** (`services/transcode-worker`) | Python + FFmpeg | 9100 (metrics) | Consume the durable queue, one FFmpeg pass → CMAF + HLS + DASH, upload to segments bucket, mark catalog ready |
| **Origin** (`services/origin`) | Nginx | 8080, 9113 (metrics) | Proxy + cache manifests/segments from the S3 segments bucket; CDN-edge stand-in |
| **Beacon Collector** (`services/beacon-collector`) | Python 3.12, FastAPI | 8001 | Ingest player QoE events → Prometheus metrics |
| **Prometheus** | Prometheus | 9090 | Scrape metrics; evaluate recording + alert rules |
| **Grafana** | Grafana | 3000 | Dashboards (backend, pipeline, QoE, SLOs) |
| **Alertmanager** | Alertmanager | 9093 | Route/dedupe alerts |
| **MinIO** | S3-compatible object storage | 9000/9001 | Persistent raw uploads and HLS segments |
| **DynamoDB-local** | Local catalog and queue | 8000 (internal) | Persistent metadata and transcode queue |

**Local resources (created automatically by the services):**

| Resource | Name | Used by |
|---|---|---|
| S3 bucket | `streamsre-raw-uploads` | upload-api (write), worker (read) |
| S3 bucket | `streamsre-hls-segments` | worker (write), origin (read) |
| DynamoDB queue | `streamsre-transcode-queue` | upload-api (send), worker (receive) |
| DynamoDB table | `streamsre-catalog` | upload-api (CRUD), worker (update status) |

---

## 3. Data flows

### 3.1 Upload → transcode → ready

1. Admin UI (`/admin`, login-gated) `POST /api/v1/upload` with the admin Basic
   auth header (multipart: file + optional title/genre/year/…).
1. **upload-api**: validates → puts raw file to `raw-uploads` → writes a
   DynamoDB catalog row with `status=processing` (the **movie id is the job id**)
  → enqueues a durable queue item `{job_id, s3_key}`.
3. **transcode-worker**: receives the job, downloads the raw file, runs **one**
   FFmpeg pass producing CMAF (fMP4) segments plus `master.m3u8` (HLS) and
   `manifest.mpd` (DASH), uploads everything to `hls-segments/<job_id>/`, then
   updates the DynamoDB row to `status=ready` with the manifest URLs.
4. UI polls `GET /api/v1/jobs/{job_id}` (S3-derived: complete once
   `master.m3u8` exists) and/or re-fetches the catalog.

### 3.2 Playback

1. UI `GET /api/v1/movies/` renders the hero + genre rows (polled every 5s so
   newly-ready uploads appear without a reload).
2. Click **Play** → navigate to `/player?url=<manifest_url>`.
3. hls.js requests `master.m3u8` → media playlists → `.m4s` segments, all via
   the **origin** (`:8080/hls/...`), which proxies and caches the S3 segments
   bucket. DASH players can use `manifest.mpd` from the same segments.

### 3.3 Telemetry (QoE)

1. The player measures startup time, rebuffering, bitrate switches, errors.
2. It `POST`s batches to **beacon-collector** `POST /api/v1/beacon/`.
3. The collector converts events into Prometheus metrics (startup histogram,
   rebuffer counters, session counters), scraped by Prometheus.

---

## 4. Local storage and optional AWS compatibility

- The default Compose deployment uses MinIO for objects and DynamoDB-local for
  the catalog and durable transcode queue.
- Buckets, tables, and queue state are initialized by the services and persist
  in Docker volumes.
- `infra/terraform` and [infra-floci.md](infra-floci.md) document an optional
  AWS-compatible path for experiments; they are not required by `start.sh`.

See [infra-floci.md](infra-floci.md) for the optional compatibility path and the
real-to-production mapping.

---

## 5. SRE & observability anchors

- **Golden signals** per service: latency, traffic, errors, saturation.
- **Metrics**: `upload_api_http_*` (upload-api), transcode job duration / queue
  depth / segments uploaded (worker, `:9100`), `qoe_*` (beacon), nginx stub
  status (origin, `:9113`).
- **SLOs / burn-rate alerts** (`slo/`, `observability/prometheus/rules`):
  manifest/segment availability + latency, transcode success, QoE startup and
  rebuffer ratio; multi-window fast/slow burn.
- **Runbooks** (`runbooks/`): high manifest error rate, transcode queue backup /
  DLQ, origin 5xx spikes.
- **Chaos** (`chaos/`): kill origin, inject latency — prove the alerts + SLOs.

---

## 6. Deployment mapping (local → cloud)

Everything here is designed to lift onto real AWS by swapping the floci endpoint
for real service endpoints:

| Local (this repo) | Real AWS |
|---|---|
| floci S3 | S3 |
| floci SQS | SQS |
| floci DynamoDB | DynamoDB |
| Nginx origin | S3 + CloudFront (OAC) |
| Docker Compose | ECS Fargate / EKS |
| Prometheus + Grafana | Amazon Managed Prometheus/Grafana or CloudWatch |
| Terraform → floci | Same Terraform → AWS (drop the `endpoints{}`/skip_* in `provider.tf`) |
