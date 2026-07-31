# I/O Framer

> **Frames in, interpolated frames out.** A plug-and-play sidecar that boosts a
> title's frame rate (e.g. 24/30 → 60 fps) with **RIFE** neural frame
> interpolation running on **Vulkan** — no CUDA, no NVENC/NVDEC dependency.

I/O Framer is a **pre-processing** step, not part of the streaming path. The
transcode worker hands it a source clip, gets back a *mezzanine* (the same clip at
a higher frame rate), and then runs the normal HLS/DASH ladder on that mezzanine.
The packaging, QoE beacon, and player never know interpolation happened — they
just receive a smoother master.

- **Container:** `streamsre-io-framer` · FastAPI on `:8000` · compose name `io-framer`
- **Engine:** [`rife-ncnn-vulkan`](https://github.com/nihui/rife-ncnn-vulkan) (C++/Vulkan) wrapped by a thin FastAPI orchestrator
- **Interface:** see [CONTRACT.md](./CONTRACT.md) — `GET /healthz`, `POST /interpolate`, `GET /interpolate/{job_id}`
- **Status:** Phase 0 complete (flags, catalog fields, contract). Not yet wired.

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

## Build phases

Each phase is independently shippable and leaves the platform working. Interpolation
stays behind `INTERP_ENABLED` (off) until Phase 3.

| # | Phase | Outcome | Scope | Touches |
|---|-------|---------|-------|---------|
| **0** | **Flags & contract** ✅ | plumbing, zero behaviour | `INTERP_*` flags in upload-api + worker; `interp_requested / interp_target_fps / interp_status / interp_detail` on `Movie`; this contract | upload-api, worker, docs |
| **1** | **Toggle + validation** ✅ | end-to-end flag, still no GPU work | upload-form toggle + options; upload-api server-side validation; store fields; worker reads the flag but **no-ops** (logs, publishes normally) | frontend, upload-api, worker |
| **2** | **The service, standalone** ✅ | interpolation works in isolation | scaffold `services/io-framer/` (Dockerfile: Vulkan + rife + ffmpeg, FastAPI); chunked pipeline; in-service guardrails; test via `curl`, verify fps with `ffprobe` — not yet wired to the worker | new service |
| **3** | **Worker integration** | real feature behind the flag | worker: ffprobe → guardrails → call service → ladder on the mezzanine → fallback/skip; publish message notes fps; GPU serialization (encoder vs. interpolator) | worker (+ compose) |
| **4** | **Admin observability** | see & trust it | studio shows `interp_status` + reason; Prometheus metrics (jobs / duration / skips / failures) → Grafana | frontend, service |
| **5** | **Hardening** | production-ish | disk preflight, progress folded into the existing bar, poison/timeout tuning, README/docs | as needed |

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
