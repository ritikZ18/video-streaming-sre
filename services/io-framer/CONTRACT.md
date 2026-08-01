# I/O Framer — service contract

> Frames in, interpolated frames out. RIFE (intermediate-flow) FPS boost via Vulkan,
> run as a plug-and-play sidecar. This document is the **interface**; the service
> itself is built in a later phase. Nothing in the platform calls it yet.
>
> For the *why/how* (RIFE mechanism, why Vulkan, the CPU path), the architecture
> diagram, and the full phase plan, see [README.md](./README.md). The planned
> Real-ESRGAN upscaling capability (`/upscale`) is specced in [UPSCALING.md](./UPSCALING.md).

- **Container:** `streamsre-io-framer` · listens on `:8000` (compose network name `io-framer`)
- **Engine:** `rife-ncnn-vulkan` (C++/Vulkan binary) wrapped by a small FastAPI orchestrator
- **GPU:** Vulkan compute (works on the GTX 1650; no NVENC/NVDEC dependency). Falls
  back to a slow CPU path when no Vulkan device is present — used only for smoke tests.
- **Role:** a *pre-processing* step. The worker hands I/O Framer a source clip, gets
  back the same clip at a higher frame rate, then runs its normal HLS/DASH ladder on
  the smoothed master. Interpolation never touches the packaging/QoE path.

## Flow (once wired, Phase 3)

```
admin requests smoothing (target_fps)
        │  upload-api validates against guardrails, sets interp_requested/interp_status=queued
        ▼
transcode-worker  ──POST /interpolate──►  io-framer  ──(decode ▸ RIFE ▸ encode)──►  S3
        │  ◄──── GET /interpolate/{job_id} (poll) ────┘
        ▼
worker transcodes the interpolated master into the ladder, marks interp_status=done
```

The source and result are exchanged as **S3 keys** (MinIO), not raw HTTP bodies, so a
10-minute clip never rides the request/response.

## Endpoints

### `GET /healthz`
Readiness + which backend actually bound.
```json
{ "status": "ok", "backend": "vulkan", "gpu": true, "model": "rife-v4.6", "devices": ["NVIDIA GeForce GTX 1650"] }
```

### `POST /interpolate`  →  `202 Accepted`
Enqueue an interpolation pass. Idempotent on `movie_id` + `target_fps` (a duplicate
request returns the in-flight `job_id`, it does not start a second pass).

Request:
```json
{
  "movie_id": "8f3c…",
  "target_fps": 60,
  "source": { "s3_bucket": "streamsre-raw-uploads", "s3_key": "8f3c…/source.mp4" },
  "output": { "s3_bucket": "streamsre-raw-uploads", "s3_key": "8f3c…/interpolated.mp4" },
  "options": { "model": "rife-v4.6", "max_height": 1080 }
}
```

Response:
```json
{ "job_id": "if_2b9a…", "status": "queued" }
```

`400` if the request violates a guardrail the caller should have caught; `409` never —
duplicates fold into the running job.

### `GET /interpolate/{job_id}`
Poll status. `progress` is 0–100 across the whole pass; `stage` names the current step.
```json
{
  "job_id": "if_2b9a…",
  "status": "processing",
  "stage": "interpolating",
  "progress": 47,
  "source_fps": 24.0,
  "target_fps": 60,
  "output": null,
  "detail": null,
  "metrics": { "gpu": true, "elapsed_seconds": 138.2 }
}
```
On `done`, `output` carries the written object + real frame count:
```json
{ "status": "done", "stage": "uploading", "progress": 100,
  "output": { "s3_bucket": "streamsre-raw-uploads", "s3_key": "8f3c…/interpolated.mp4", "fps": 60, "frames": 14400 },
  "metrics": { "gpu": true, "elapsed_seconds": 511.7 } }
```
On `failed`, `detail` is a short human-readable reason; the original ladder is untouched.

`status` maps 1:1 onto the catalog `InterpStatus` (`schemas.py`):
`queued · processing · done · failed`, plus `skipped` which is decided **before** a job
is created (a guardrail declined it), so it never appears in a `GET` response.

## Guardrails

Enforced by the **upload-api** before enqueue *and* re-checked by the sidecar (defence in
depth). Config lives in both services (`INTERP_*`, see `config.py`); a violation yields
`interp_status = "skipped"` with a reason in `interp_detail` — never a hard error.

| Guard | Env | Default | Rationale |
|-------|-----|---------|-----------|
| Feature on/off | `INTERP_ENABLED` | `false` | master kill-switch |
| Target fps | `INTERP_MAX_TARGET_FPS` | `60` | 60 is the QoE ceiling; higher buys little on typical displays |
| Source fps | `INTERP_MAX_SOURCE_FPS` | `40` | a ≥40fps source is already smooth — skip, don't waste GPU |
| Height | `INTERP_MAX_HEIGHT` | `1080` | RIFE cost scales with pixels; cap the ladder input |
| Duration | `INTERP_MAX_DURATION_SECONDS` | `600` | bound worst-case GPU time on the single 1650 |
| Target default | `INTERP_DEFAULT_TARGET_FPS` | `60` | used when the admin doesn't name a target |

Sidecar-side timeout: `INTERP_TIMEOUT_SECONDS` (worker default `1800`).

## Phase map

- **Phase 0 (this) — plumbing only.** `INTERP_*` flags in upload-api + worker `config.py`;
  `interp_requested / interp_target_fps / interp_status / interp_detail` on the catalog
  `Movie`; this contract. No behaviour: the flags are read by nothing, the fields move no
  pixels, `services/io-framer/` holds only this doc.
- **Phase 1** — admin can *request* smoothing; upload-api validates guardrails and persists
  intent/state. Still no interpolation.
- **Phase 2** — the I/O Framer service itself (Dockerfile, FastAPI, rife-ncnn-vulkan),
  implementing the endpoints above. Runnable standalone, not yet wired into a transcode.
- **Phase 3** — worker calls the sidecar as a pre-processing step; publishes the smoothed
  ladder; drives `interp_status` through its lifecycle.
- **Phase 4** — admin observability (an interpolation-jobs panel, like transcode jobs).
- **Phase 5** — hardening: idempotency, retries/leasing, GPU contention with the encoder.
