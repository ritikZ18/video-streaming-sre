## Mini Video Streaming Platform + SRE

This repository contains **Project 1 – Mini Video Streaming Platform + SRE**, a portfolio-ready system that mimics a modern OTT service (think Apple TV / Netflix) while showcasing **SRE fundamentals**:

- **End‑to‑end video delivery path**: upload → transcode → package → origin → CDN → web player.
- **Strong observability**: Prometheus, Grafana, SLO dashboards, multi‑window burn‑rate alerts.
- **Operational maturity**: runbooks, chaos experiments, incident workflows.
- **Security and reliability**: least‑privilege IAM, secret management, safe Docker images.

This project is designed so that in an interview you can walk through:

- How a video request flows through the system.
- Which SLOs you defined and how they are enforced with alerts.
- How you would debug a real incident using metrics, logs, and runbooks.

---

## High‑Level Architecture

At a high level the system is composed of:

- **Upload API** – Receives video uploads, stores raw assets in object storage, and enqueues transcode jobs.
- **Transcode Worker** – Consumes jobs, runs **FFmpeg** to generate HLS renditions and manifests, and writes them to the segments bucket.
- **Origin Gateway** – An Nginx layer that serves manifests and segments, with caching and security headers.
- **Web Player** – A UI inspired by **Apple TV**, showing rows of movies and allowing playback.
- **Beacon Collector** – Ingests QoE telemetry from the player (startup time, rebuffering, bitrate changes).
- **Observability Stack** – Prometheus + Alertmanager + Grafana (and optionally OpenTelemetry).

All of this is backed by:

- **Object storage** (e.g. S3) for raw uploads and HLS segments.
- A **catalog database** (e.g. Postgres) for movie metadata (title, genre, year, tags).
- A **queue** (e.g. SQS) for decoupling uploads from transcoding.

See `docs/architecture.md` for diagrams and data‑flow details.

---

## Tech Stack (Core)

- **Backend services**: Python 3.12, FastAPI, Uvicorn.
- **Workers**: Python + FFmpeg for transcoding and HLS packaging.
- **Web player UI**: React (Apple TV–style hero & rows layout).
- **Database (catalog)**: Postgres for movie metadata.
- **Storage**: S3 (or LocalStack S3 in local dev) for video files.
- **Queue**: SQS (or LocalStack SQS in local dev).
- **Observability**: Prometheus, Grafana, Alertmanager, blackbox exporter.
- **Containerization**: Docker, docker‑compose for local development.

Deployment to cloud (e.g. AWS ECS + CloudFront) is planned but implemented separately from this initial project skeleton.

---

## Repository Structure (Current Phase)

This initial commit focuses on **project planning and documentation**:

- `README.md` – This overview.
- `docs/` – Detailed documentation:
  - `architecture.md` – System design, components, and data flows.
  - `product.md` – What the product is, user experience, and what this project mimics.
  - `database.md` – How the catalog database is used (schema, access patterns).
  - `api-structure.md` – High‑level API surface for upload, catalog, and beacons.

Future phases will add:

- `services/` for each backend component (Upload API, Transcode Worker, Origin, Beacon Collector).
- `frontend/` containing the React UI.
- `observability/` for Prometheus, Grafana, and alert rules.
- `slo/`, `runbooks/`, and `chaos/` directories for SRE artifacts.

---

## Local Development (Planned Flow)

Once the services are implemented, the typical local loop will be:

1. **Configure environment**  
   - Copy `.env.example` → `.env` (will be added later).  
   - Fill in local credentials / URLs (LocalStack, Postgres, etc.).

2. **Start the stack**  
   - Use `docker-compose` to bring up:
     - Upload API, Transcode Worker, Origin, Player UI.
     - LocalStack (S3/SQS), Postgres (catalog DB).
     - Prometheus, Grafana, Alertmanager.

3. **Upload a sample video**  
   - Call the Upload API or use the web player “Add Movie” flow.

4. **Watch metrics & alerts**  
   - Open Grafana dashboards to view:
     - Origin latency and error rate.
     - Transcode queue depth and failure rate.
     - QoE metrics (startup time, rebuffering).

5. **Run chaos scenarios**  
   - Kill origin / inject latency and observe SLO burn‑rate alerts.

---

## Documentation

All detailed docs live in the `docs/` directory:

- **Architecture** – Components, request flows, dependencies.
- **Product** – What a user can do and what the system mimics.
- **Database** – How movie metadata is stored, queried, and updated.
- **APIs** – REST contracts for Upload, Catalog, and Beacon services.

Start with `docs/product.md` for a product‑level tour, then move to `docs/architecture.md` to understand how it’s built.

