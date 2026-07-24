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
- **Transcode Worker** – Consumes jobs and runs **FFmpeg** once to produce a CMAF (fMP4) bitrate ladder, publishing **HLS** (`master.m3u8`) and **MPEG-DASH** (`manifest.mpd`) manifests from the *same* segments, then writes them to the segments bucket.
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
- **Storage**: S3 (via the **floci** local AWS emulator in dev) for video files.
- **Queue**: SQS (via **floci** in dev).
- **Infra as code**: Terraform provisions the S3 buckets + SQS queues into floci (`infra/terraform`). See `docs/infra-floci.md`.
- **Observability**: Prometheus, Grafana, Alertmanager, blackbox exporter.
- **Containerization**: Docker, docker‑compose for local development.

Deployment to cloud (e.g. AWS ECS + CloudFront) is planned but implemented separately from this initial project skeleton.

---

## Repository Structure

- `services/` – Backend components:
  - `upload-api/` – FastAPI upload endpoint; stores to S3, enqueues to SQS.
  - `transcode-worker/` – SQS consumer; FFmpeg → CMAF + HLS/DASH manifests.
  - `origin/` – Nginx origin that proxies/caches manifests + segments from S3.
  - `beacon-collector/` – Ingests QoE telemetry from the player.
- `frontend/` – Next.js player UI (Apple TV–style rows, `hls.js` playback).
- `infra/terraform/` – Terraform for the S3 buckets + SQS queues (targets floci).
- `observability/` – Prometheus, Grafana, Alertmanager configs and dashboards.
- `slo/`, `runbooks/`, `chaos/` – SRE artifacts (SLOs, incident runbooks, chaos).
- `security/` – Image + secret scanning scripts.
- `docs/` – Detailed documentation:
  - `architecture.md` – System design, components, and data flows.
  - `product.md` – What the product is and what it mimics.
  - `database.md` – Catalog DB schema and access patterns.
  - `api-structure.md` – API surface for upload, catalog, and beacons.
  - `design.md` – **Full application design** (goals, data model, flows, decisions).
  - `infra-floci.md` – **How Terraform + the floci local AWS emulator work together.**

---

## Local Development

AWS (S3 + SQS + DynamoDB) is emulated locally by **floci**, which runs as its
own stack and listens on `http://localhost:4566`. See `docs/infra-floci.md` for
the full story and `docs/design.md` for the complete application design.

**Quickest path — one command:**

```bash
./start.sh            # floci → Terraform infra → all services   (--seed for a demo clip)
./stop.sh             # stop services   (./stop.sh --all also stops floci)
```

Or step by step with the Makefile:

```bash
make floci-up      # 1. start floci (local AWS emulator)
make tf-apply      # 2. Terraform creates S3 buckets + SQS queues + DynamoDB table
cp .env.example .env   # 3. config already matches floci + terraform defaults
make up            # 4. docker compose up (upload-api, worker, origin, player, obs stack)
bash scripts/seed-test-video.sh   # 5. push a test clip through the pipeline
```

`make bootstrap` does steps 1–2; `make demo` does 1–5. Then:

- **Browse & watch** on the public site (`http://localhost:3001`).
- **Upload** at `http://localhost:3001/admin` — log in (default `admin`/`admin`,
  set via `ADMIN_USERNAME` / `ADMIN_PASSWORD`). The video transcodes to HLS+DASH
  and appears on the home grid within a few seconds (the grid auto-refreshes).
- **Play** the result at `http://localhost:8080/hls/<job>/master.m3u8` (HLS) or
  `.../manifest.mpd` (DASH).
- **Watch metrics & alerts** in Grafana (`http://localhost:3000`): origin
  latency/errors, transcode queue depth/failures, QoE (startup, rebuffering).
- **Run chaos** (`chaos/`): kill origin / inject latency, observe SLO burn‑rate
  alerts.

If an upload stays **"Processing"**, run `bash scripts/diagnose.sh` — it dumps
the worker logs plus the live S3 / SQS / DynamoDB state to show why.

---

## Documentation

All detailed docs live in the `docs/` directory:

- **Architecture** – Components, request flows, dependencies.
- **Product** – What a user can do and what the system mimics.
- **Database** – How movie metadata is stored, queried, and updated.
- **APIs** – REST contracts for Upload, Catalog, and Beacon services.

Start with `docs/product.md` for a product‑level tour, then move to `docs/architecture.md` to understand how it’s built.

