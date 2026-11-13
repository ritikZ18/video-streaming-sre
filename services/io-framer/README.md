# I/O Framer

> **Frames in, better frames out.** A plug-and-play sidecar that makes a title
> **smoother** (RIFE frame interpolation, 24/30 → 60 fps) and — _in progress_ —
> **sharper** (Real-ESRGAN upscaling, ×2/×4). Both are neural, per-frame, and run
> on **Vulkan** — no CUDA, no NVENC/NVDEC dependency.

I/O Framer is a **pre-processing** step, not part of the streaming path. The
transcode worker hands it a source clip, gets back a *mezzanine* (the same clip at
a higher frame rate), and then runs the normal HLS/DASH ladder on that mezzanine.
The packaging, QoE beacon, and player never know interpolation happened — they
just receive a smoother master.

- **Container:** `streamsre-io-framer` · FastAPI on `:8000` · compose name `io-framer`
- **Engine:** [`rife-ncnn-vulkan`](https://github.com/nihui/rife-ncnn-vulkan) (C++/Vulkan) wrapped by a thin FastAPI orchestrator
- **Interface:** see [CONTRACT.md](./CONTRACT.md) — `GET /healthz`, `POST /interpolate`, `GET /interpolate/{job_id}`
- **Status:** all 6 phases complete — wired into the transcode pipeline and shipping (opt-in per upload).

---

## Scope — two transforms

I/O Framer runs two orthogonal, per-frame neural transforms; a title can want either
or both:

- **Frame rate — _shipping_.** RIFE interpolation raises fps (24/30 → 48/60) so motion
  looks smoother. Resolution is unchanged. (Documented below.)
- **Quality / resolution — _in progress_.** Real-ESRGAN upscaling raises resolution
  and detail (×2/×4) so a soft / low-res source looks sharper. Frame rate is
  unchanged. See **[UPSCALING.md](./UPSCALING.md)** for the how / contract / phase map.

They stay independent: interpolation never changes resolution; upscaling never
changes fps. Everything below documents the shipping **interpolation** path.

## Using it (admin studio)

The frame-rate boost is **opt-in per upload**, shown only when the server has
`INTERP_ENABLED=1` (`GET /api/v1/interp/config` → `enabled: true`):

1. Go to **/admin** and drop or pick your video file(s) — the **Upload queue** appears.
2. In the queue's controls row (next to **Genre / Rating / Tag**) tick
   **"Smooth motion → 60 fps"**, and optionally change the target fps.
3. Press **Start** — the toggle applies to every file in that batch.

The controls row (and the toggle) only shows **after** files are queued and
**before** you press Start — that is why it isn't visible on an empty upload page.
Progress and outcome show in **Admin → Observability → Frame interpolation · I/O
Framer**. A source that trips a guardrail (already high-fps, too tall/long, HDR) is
transcoded at its native rate and marked `skipped` with the reason.

---

## Why this exists

The obvious "just use ffmpeg" answer doesn't hold on this hardware:

- **`ffmpeg minterpolate` is CPU-only and slow**, and produces motion-boundary
  artifacts on real content. There is no GPU build path for it here.
- **NVENC/NVDEC don't interpolate** — they encode/decode. And the GTX 1650 can't
  even NVDEC-decode AV1, so leaning on the codec engines is a dead end.

So we need a *neural* interpolator that's fast on a modest GPU and doesn't drag in
a CUDA/PyTorch toolchain. That's **RIFE** via **ncnn + Vulkan**.

---

## How RIFE works

Frame interpolation asks: given two consecutive frames **I₀** and **I₁**, synthesize
a believable in-between frame **Iₜ** at time **t ∈ (0, 1)**. To go 24 → 60 fps you
insert ~1.5 new frames per original pair, so the interpolator must support an
**arbitrary t**, not just the midpoint.

**The classic flow-based approach does it in two hops:**

1. Estimate bidirectional optical flow `F₀→₁`, `F₁→₀` between the two inputs.
2. **Linearly reverse/scale** those into the *intermediate* flows `Fₜ→₀`, `Fₜ→₁`
   needed to warp each input to time t.

Step 2 is the weak link: it guesses motion for pixels that only exist in the frame
being invented, so it smears around motion boundaries and occlusions.

**RIFE's contribution — IFNet — skips the reversal.** It estimates the intermediate
flows **directly**, from the perspective of the frame being created:

- **IFNet (coarse-to-fine).** A stack of *IFBlocks* at increasing resolution
  progressively refines `Fₜ→₀` and `Fₜ→₁`. Crucially, **t is an input** to the
  network, so a single model does 2×, 3×, or arbitrary-ratio interpolation — not a
  fixed 2× doubling.
- **Backward warp.** Warp I₀ by `Fₜ→₀` and I₁ by `Fₜ→₁` to bring both inputs to
  time t.
- **Fusion + refine.** A small encoder–decoder predicts a soft fusion mask **M**
  and a residual. The output is
  **Iₜ = M · warp(I₀, Fₜ→₀) + (1 − M) · warp(I₁, Fₜ→₁) + residual.**
  The mask resolves occlusion (use whichever input actually *sees* each pixel); the
  residual cleans up warping artifacts.
- **Privileged distillation (training only).** A *teacher* block is allowed to peek
  at the ground-truth middle frame and produce a sharper intermediate flow, which is
  distilled into the *student* IFNet. This improves flow estimation with **zero**
  extra inference cost — the teacher is discarded at runtime.

The result is the "RT" in RIFE: one forward pass, no per-frame optimization and no
flow-reversal heuristics, so it runs in real time on a single GPU while beating much
heavier prior models (DAIN, SepConv, …) on the standard VFI benchmarks.

### Why `rife-ncnn-vulkan` (and the CPU path)

- **Vulkan, not CUDA.** `rife-ncnn-vulkan` reimplements RIFE on Tencent's
  [**ncnn**](https://github.com/Tencent/ncnn) inference framework with a **Vulkan**
  compute backend. Vulkan is vendor-neutral, so it runs on the GTX 1650 (and on
  AMD/Intel) with **no CUDA/cuDNN/PyTorch** — the image stays small and portable.
  Interpolation is a Vulkan *compute* job, so the 1650's codec limits (no AV1
  NVDEC, etc.) are irrelevant here.
- **The wrapper language doesn't move the needle.** The heavy compute is the
  precompiled Vulkan binary; FastAPI only orchestrates (S3 in/out, chunking,
  ffmpeg frame extract/reassemble, progress). Python is chosen for glue ergonomics,
  not speed.
- **CPU fallback.** With no Vulkan device the binary can run on CPU — correct but
  far too slow for real content. We keep it **only for CI/smoke tests** (prove the
  pipeline end-to-end on a tiny clip without a GPU). Production requires Vulkan,
  which `GET /healthz` reports.

---

## Architecture

```
                         ┌─────────────── admin browser ───────────────┐
                         │  Upload form: [x] Smooth motion → 60fps      │
                         │  guardrail hints (≤1080p, ≤10min, opt-in)    │
                         └───────────────────┬──────────────────────────┘
                                             │ multipart + interp flags
                                             ▼
   ┌──────────────┐   validate flags   ┌──────────────┐   job body {interp:true,
   │  upload-api  │───(server-side)────▶│  catalog     │    target_fps:60}
   │  guardrails  │   store fields      │ (dynamodb)   │
   └──────┬───────┘                     └──────────────┘
          │ enqueue (durable DynamoDB queue)
          ▼
   ┌───────────────────────── transcode-worker ─────────────────────────┐
   │ 1. ffprobe  →  evaluate guardrails (h≤1080, dur≤cap, srcfps<target) │
   │ 2. if PASS →  POST /interpolate ───────────────┐                    │
   │ 3. else / on error → skip (normal encode), set interp_status=skipped│
   │ 4. run ladder on the returned mezzanine        │                    │
   │ 5. package CMAF → publish (message notes fps)  │                    │
   └────────────────────────────────────────────────┼────────────────────┘
                                                     ▼
                         ┌──────────── io-framer (NEW) ────────────────┐
                         │ FastAPI: /interpolate /healthz /metrics     │
                         │ GPU: Vulkan + rife-ncnn-vulkan              │
                         │ read src ← MinIO                            │
                         │ chunk → extract → rife → reassemble → concat│
                         │ remux audio → write mezzanine → MinIO       │
                         │ concurrency=1 (GPU), timeout, disk-preflight│
                         └─────────────────────────────────────────────┘
```

Guardrails are enforced **twice** — once by upload-api before the job is enqueued,
and again inside the service (defence in depth). A violation is never a hard error:
it sets `interp_status = "skipped"` with a reason in `interp_detail`, and the title
transcodes normally at its native frame rate. See the guardrail table in
[CONTRACT.md](./CONTRACT.md#guardrails).

---

## Running it (standalone)

Phase 2 ships the service runnable on its own (not yet wired to the worker). It sits
behind a compose profile, so a normal `docker compose up` leaves it out:

```bash
# build + start (lavapipe CPU fallback by default)
docker compose --profile interp up -d --build io-framer

# which backend bound?
curl -s localhost:8090/healthz
# {"status":"ok","backend":"cpu","gpu":false,"model":"rife-v4.6","devices":["llvmpipe …"]}

# interpolate a source already in MinIO (24 → 48 fps), then poll
curl -s -XPOST localhost:8090/interpolate -H 'content-type: application/json' -d '{
  "movie_id":"demo","target_fps":48,
  "source":{"s3_bucket":"streamsre-raw-uploads","s3_key":"demo/src.mp4"},
  "output":{"s3_bucket":"streamsre-raw-uploads","s3_key":"demo/out.mp4"}}'
curl -s localhost:8090/interpolate/<job_id>
```

Verified on a 24 → 48 fps clip: `nb_read_frames` doubles (48 → 96) and
`avg_frame_rate` becomes `48/1`. On the lavapipe CPU fallback a 2 s 320×240 clip
takes ~75 s; the GPU path is far faster — uncomment the GPU block in
`docker-compose.yml` (needs `nvidia-container-toolkit` and
`NVIDIA_DRIVER_CAPABILITIES=all` so the NVIDIA Vulkan ICD is visible in the
container). `/healthz` will then report `backend: vulkan`.

## Operations & hardening

- **Single-flight.** One interpolation pass runs at a time (an async semaphore).
  The GPU/lavapipe is the bottleneck and must not be oversubscribed; the worker
  also blocks on the pass before its own NVENC ladder, so RIFE and the encoder
  never contend for the GTX 1650.
- **Disk preflight.** Before extracting frames the service estimates the PNG
  scratch (~2 bytes/pixel × (input + output) frames, +10%) and fails fast with a
  clear message if the temp volume can't hold it — no half-filled disk.
- **Hard timeout.** `INTERP_TIMEOUT_SECONDS` (default 1800) is enforced as a
  wall-clock kill on the rife subprocess (the binary has no self-timeout); the
  worker polls under the same budget.
- **Graceful fallback.** Any failure — guardrail, preflight, sidecar error, or an
  unreachable sidecar — makes the worker publish at the **native** frame rate and
  record `interp_status = failed/skipped`. A title never fails to transcode
  because interpolation didn't happen.
- **Idempotency.** A duplicate `(movie_id, target_fps)` request folds into the
  in-flight job; the key frees on terminal status so a later re-request restarts.
- **Scaling caveat.** The current pipeline extracts the *whole* clip to PNG, so
  scratch scales with pixels × frames. The height (≤1080p) and duration (≤10 min)
  guardrails plus the preflight bound the worst case; true per-chunk streaming is
  the next scaling step.

### GPU vs. CPU

`/healthz` reports the bound backend. By default the container uses the Mesa
**lavapipe** software Vulkan device (`backend: cpu`) — correct but slow, for
smoke tests. To run on the NVIDIA GPU, uncomment the `NVIDIA_*` env + the `deploy`
block on the `io-framer` service in `docker-compose.yml` (needs
`nvidia-container-toolkit`); `/healthz` then reports `backend: vulkan`.

> **WSL2 caveat (this dev box).** The toolkit injects **CUDA/NVENC** (which the
> transcode worker uses) but **not** the Vulkan ICD, so even with the block
> enabled `vulkaninfo` sees only lavapipe and `/healthz` stays `backend: cpu` —
> the service falls back cleanly. Binding the GPU here would need the WSL Vulkan
> libs (`/usr/lib/wsl/lib` + the NVIDIA ICD) mounted in. On **native Linux** with
> the toolkit, the block binds `backend: vulkan` directly. lavapipe is the working
> path on WSL2.

## Build phases

Each phase is independently shippable and leaves the platform working. Interpolation
stays behind `INTERP_ENABLED` (off) until Phase 3.

| # | Phase | Outcome | Scope | Touches |
|---|-------|---------|-------|---------|
| **0** | **Flags & contract** ✅ | plumbing, zero behaviour | `INTERP_*` flags in upload-api + worker; `interp_requested / interp_target_fps / interp_status / interp_detail` on `Movie`; this contract | upload-api, worker, docs |
| **1** | **Toggle + validation** ✅ | end-to-end flag, still no GPU work | upload-form toggle + options; upload-api server-side validation; store fields; worker reads the flag but **no-ops** (logs, publishes normally) | frontend, upload-api, worker |
| **2** | **The service, standalone** ✅ | interpolation works in isolation | scaffold `services/io-framer/` (Dockerfile: Vulkan + rife + ffmpeg, FastAPI); chunked pipeline; in-service guardrails; test via `curl`, verify fps with `ffprobe` — not yet wired to the worker | new service |
| **3** | **Worker integration** ✅ | real feature behind the flag | worker: ffprobe → guardrails → call service → ladder on the mezzanine → fallback/skip; drives `interp_status`; GPU serialization (encoder vs. interpolator) | worker (+ compose) |
| **4** | **Admin observability** ✅ | see & trust it | studio shows `interp_status` + reason (observability panel); Prometheus metrics — worker `interp_jobs_total{result}` / `interp_duration_seconds`, sidecar `iof_jobs_total{status}` / `iof_job_duration_seconds` — scraped into Grafana | frontend, worker, service |
| **5** | **Hardening** ✅ | production-ish | disk preflight, live interpolation progress, hard rife timeout, graceful fallback, ops docs; GPU wiring documented | service, docs |

---

## Research & citations

**Primary method**

> Zhewei Huang, Tianyuan Zhang, Wen Heng, Boxin Shi, Shuchang Zhou.
> **"Real-Time Intermediate Flow Estimation for Video Frame Interpolation" (RIFE).**
> ECCV 2022. arXiv:[2011.06294](https://arxiv.org/abs/2011.06294).

This is the IFNet / direct-intermediate-flow / privileged-distillation method the
service runs. The "why it's fast and clean" above is a summary of this paper.

**Implementation we wrap**

- [`nihui/rife-ncnn-vulkan`](https://github.com/nihui/rife-ncnn-vulkan) — RIFE on
  ncnn + Vulkan; the binary this sidecar shells out to.
- [`Tencent/ncnn`](https://github.com/Tencent/ncnn) — the Vulkan-backed inference
  runtime underneath it.

**Reference PyTorch implementations** (for model weights / behaviour parity)

- [`hzwer/ECCV2022-RIFE`](https://github.com/hzwer/ECCV2022-RIFE) — the authors' official code.
- [`hzwer/Practical-RIFE`](https://github.com/hzwer/Practical-RIFE) — the maintained, production-tuned line the `v4.x` weights come from.
