## Product Overview – Mini Video Streaming Platform

This project mimics a modern **Apple TV / Netflix–style streaming experience** with a strong focus on **SRE and observability** rather than building a full commercial product.

From a product point of view, the platform offers:

- **Beautiful TV‑like browsing UI** with a cinematic hero section and horizontal carousels.
- **Movie catalog** powered by a database, not just hard‑coded JSON.
- **Video playback** via HLS manifests and segments served from an origin and cached by a CDN.
- **Quality‑of‑experience (QoE) telemetry** to measure how the product feels for users.

---

## Core User Flows

### 1. Browse & Discover

- Open the home page and see:
  - A **hero title** with gradient artwork, title, description, tags (e.g. “Trending”).
  - Horizontal rows like **Trending**, **Action**, **Sci‑Fi**, **Drama**, etc.
- Rows are driven by **catalog queries** (e.g. by genre, tag, or sort order).
- Cards show:
  - Title, genre, year, rating, and a subtle gradient background.
  - A hover state with a play glyph (like Apple TV tiles).

### 2. View Movie Details

- Click a movie card to open a **detail panel**:
  - Large artwork header with gradient.
  - Chips for year, rating, duration, and genre.
  - Long‑form description / synopsis.
  - **Play** button (starts HLS playback).
  - **Add to List** (future: simple favorites or watchlist).

The detail view is the natural place to expose **technical metadata** in future (bitrate ladder, available resolutions, etc.) if you want to showcase more SRE/video knowledge.

### 3. Play a Video

- When the user presses **Play**:
  - The player loads the **master.m3u8** manifest for that movie.
  - hls.js (or the browser’s native HLS) handles adaptive bitrate selection.
  - The **Beacon SDK** in the player sends:
    - Startup time (time to first frame).
    - Rebuffer events (count + duration).
    - Bitrate switches.
    - Session heartbeats.

These beacons feed into **Prometheus metrics** via the Beacon Collector, powering QoE dashboards and SLOs.

### 4. Add Movies to the Catalog (admin only)

Adding content lives behind the **`/admin` login** (default `admin`/`admin`).
The public site is browse + watch only. There are two paths, both admin-gated:

1. **Upload Flow** (the real ingestion pipeline):
   - On `/admin`, upload a raw video file plus metadata.
   - The system:
     - Stores the raw file in the “raw uploads” bucket.
     - Registers a catalog record (`status = processing`) and sends a message to
       the transcode queue.
     - After transcoding, writes HLS + DASH manifests and CMAF segments into the
       “segments” bucket and flips the record to `status = ready` with its
       manifest URLs (movie ID, title, genre, rating, year, tag, etc.).

2. **Register existing HLS** (fast for testing):
   - The `/admin` "Add Movie" form calls `POST /api/v1/movies/` with metadata and
     an HLS folder id; the API stores a playable `manifest_url`
     (`<origin>/hls/<id>/master.m3u8`). Useful when the HLS assets already exist.

The Apple TV–style UI uses the catalog API for:

- `GET /api/v1/movies/` – list for carousels and search (public, auto-refreshed).
- `POST /api/v1/movies/` – add a movie from the admin “Add Movie” panel (auth).

---

## What This Project Mimics

This project is intentionally **smaller than a real streaming service**, but it mimics the critical pieces you can talk about in interviews:

- A **production‑like video pipeline**:
  - Upload → queue → transcode → package → origin → CDN → player.
- **Clear separation of concerns**:
  - Upload, worker, origin, player, beacon collector, and observability are separated services.
- **SRE best practices** applied end‑to‑end:
  - SLOs for availability and latency of manifests, QoE metrics for startup/rebuffer.
  - Multi‑window burn‑rate alerts instead of simple thresholds.
  - Runbooks and chaos scenarios to practice incident response.
- **Security and reliability**:
  - Non‑root containers, secrets management, IAM least privilege.
  - Buckets with blocked public access and encryption at rest.

In short, this project lets you say:

> “I built a mini version of an Apple TV / Netflix backend, with SLOs, dashboards, and alerts that behave like a real SRE environment.”

---

## Non‑Goals (What This Project Is Not)

To keep the scope focused on SRE and learnings, this project **does not** aim to:

- Implement full account management, payments, parental controls, etc.
- Handle complex recommendation systems or ML ranking.
- Optimize for multi‑CDN, multi‑region failover beyond what’s needed to explain SRE concepts.

Those features can be mentioned as **future work**, but they are not required for a strong SRE portfolio project.

