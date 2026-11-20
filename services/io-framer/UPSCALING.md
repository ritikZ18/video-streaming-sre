# I/O Framer — Upscaling (Real-ESRGAN) · _in progress_

> **Sharper frames out.** Real-ESRGAN super-resolution (×2/×4) via Vulkan, built
> **into** I/O Framer alongside RIFE interpolation. This is the plan + interface;
> nothing calls it yet.

Interpolation raises **frame rate** (smoother); upscaling raises **resolution /
detail** (sharper). They're orthogonal per-frame transforms — a title can want
either or both. Real-ESRGAN is [`realesrgan-ncnn-vulkan`](https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan)
— the ncnn/Vulkan sibling of RIFE — so it reuses I/O Framer's exact image and
pipeline (download → extract frames → ncnn binary → encode → upload). No new service.

## How Real-ESRGAN works

Single-image super-resolution: given a low-res frame, synthesize a plausible
higher-res one — not just interpolate pixels, but **hallucinate** believable
high-frequency detail (edges, texture).

- **Generator: RRDBNet** (Residual-in-Residual Dense Blocks, from ESRGAN) upsamples
  ×4 through learned convolutions + pixel-shuffle.
- **Trained as a GAN** — a U-Net discriminator pushes the generator toward realistic
  texture, combined with a perceptual (VGG-feature) loss and an L1 loss for fidelity.
- **The "Real" part — a high-order synthetic degradation model.** Training pairs are
  built by chaining realistic degradations (blur → resize → noise → JPEG, applied
  repeatedly), so the model learns to restore *real* soft / compressed / noisy
  sources, not only clean bicubic-downscaled ones. That's what makes it useful on
  actual streaming content.
- **Runs per frame:** decode → upscale each frame ×N → re-encode at the new
  resolution. Cost scales with output pixels (×4 = 16× the pixels of ×2).

**Models** (bundled with the binary): `realesr-general-x4v3` (general video, has a
denoise strength knob — our default), `realesrgan-x4plus` (photographic),
`realesr-animevideov3` (anime/cartoon). Selectable via config.

**Citation:** Xintao Wang, Liangbin Xie, Chao Dong, Ying Shan. *"Real-ESRGAN:
Training Real-World Blind Super-Resolution with Pure Synthetic Data."* ICCV Workshops
2021. arXiv:[2107.10833](https://arxiv.org/abs/2107.10833). Impl:
[xinntao/Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN),
[realesrgan-ncnn-vulkan](https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan).

## Contract (planned)

`POST /upscale` — async, mirrors `/interpolate`:
```json
{
  "movie_id": "8f3c…",
  "factor": 2,
  "source": { "s3_bucket": "streamsre-raw-uploads", "s3_key": "8f3c…/source.mp4" },
  "output": { "s3_bucket": "streamsre-raw-uploads", "s3_key": "8f3c…/upscaled.mp4" },
  "options": { "model": "realesr-general-x4v3" }
}
```
→ `202 { "job_id": "us_…", "status": "queued" }`.
`GET /upscale/{job_id}` → the same job-status shape as interpolation, with
`output: { s3_bucket, s3_key, width, height, scale }`. `GET /metrics` gains
`iof_upscale_jobs_total{status}` + `iof_upscale_duration_seconds`.

## Guardrails

Enforced in upload-api before enqueue **and** re-checked in the sidecar. A violation
→ `upscale_status = "skipped"` with a reason; never a hard error.

| Guard | Env | Default | Rationale |
|-------|-----|---------|-----------|
| Feature on/off | `UPSCALE_ENABLED` | `false` | master kill-switch |
| Factor | `UPSCALE_MAX_FACTOR` | `4` | ×4 ceiling |
| Source too big | `UPSCALE_MAX_INPUT_HEIGHT` | `1080` | don't upscale already-hi-res |
| Result cap | `UPSCALE_MAX_OUTPUT_HEIGHT` | `2160` | bound cost + scratch |
| Duration | `UPSCALE_MAX_DURATION_SECONDS` | `300` | upscaling is heavier than interpolation |
| Timeout | `UPSCALE_TIMEOUT_SECONDS` | `3600` | wall-clock kill on the binary |

**Catalog fields:** `upscale_requested`, `upscale_factor`, `upscale_status`
(`queued|processing|done|skipped|failed`), `upscale_detail`.

## Composing with interpolation

A title may request **both**. The worker chains: interpolate → then upscale the
mezzanine (two sidecar passes to start). A later **fused** pipeline (extract frames
once, RIFE → Real-ESRGAN → encode once) would halve the frame I/O — noted as an
optimization, not required for the first cut.

## Phase map (mirrors interpolation)

| # | Phase | Scope |
|---|-------|-------|
| **0** | **Flags & contract** | `UPSCALE_*` flags in upload-api + worker + io-framer; `upscale_*` catalog fields; this doc |
| **1** | **Toggle + validation** | upload + edit-drawer toggle **"Enhance quality → ×2"**; server validation; store fields; worker no-op |
| **2** | **The engine, standalone** | add `realesrgan-ncnn-vulkan` + model to the io-framer image; `/upscale` endpoint + pipeline; verify with ffprobe (resolution grows) |
| **3** | **Worker integration** | upscale the (possibly interpolated) mezzanine; publish; drive `upscale_status`; GPU serialization |
| **4** | **Observability** | admin panel + Prometheus `upscale_*` / `iof_upscale_*` metrics |
| **5** | **Hardening** | disk preflight sized on the **output** resolution (×N pixels!), timeout tuning, GPU note |

## Caveats (read before enabling)

- **Much heavier than interpolation** — ×4 means 16× the output pixels, plus a
  larger network. On **WSL2 lavapipe** (CPU) it is impractically slow; it needs GPU
  Vulkan for real use, which does **not** bind on WSL2 (the toolkit injects
  CUDA/NVENC, not the Vulkan ICD — see the README GPU note). Functional but slow on
  this box; designed for a native-Linux GPU host.
- **Disk** — upscaled PNG frames are large; the preflight must estimate on the
  **output** resolution, not the input.
