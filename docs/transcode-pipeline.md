# Transcode pipeline

How an uploaded source becomes an adaptive HLS/DASH stream. The worker
(`services/transcode-worker`) pulls a job off SQS, transcodes with ffmpeg on the
GPU where possible, and writes a CMAF (fMP4) rendition ladder to object storage.

```
SQS job -> download source -> ffprobe -> encode ladder(s) -> encode audio ->
package CMAF (HLS master.m3u8 + DASH manifest.mpd) -> thumbnail -> upload to
MinIO -> catalog row flipped to "ready"
```

Everything below lives in `app/transcoder.py` (encode/package) and `app/main.py`
(orchestration).

---

## 1. Which rungs get made — the ladder

Profiles (`app/profiles.py`): **360p, 720p, 1080p, 1440p (2560×1440), 2160p
(3840×2160)**. The top rung is 4K — there is **no 8K rung** (NVENC H.264 maxes at
4096px wide; 8K in a browser is impractical).

`ladder_for(source_height)` returns every profile **≤ the source height, never
above** (no upscaling), always at least 360p.

**Ladder is chosen by WIDTH-class, not just height.** A wide/letterboxed "4K"
trailer can be only ~1350–1610px tall, which would wrongly cap it at 1080p. So the
worker uses an *effective* height:

```
effective_height = max(source_height, round(source_width * 9 / 16))
```

- `2560×1350` (a "1440p"-labelled Maverick clip) → `max(1350, 1440) = 1440` → gets a **1440p** rung.
- `3840×2160` (true 16:9 4K) → `2160` → full `[360 … 2160]`.
- `1920×1080` → `1080`.

## 2. Aspect-preserving scale (no distortion, keep the width)

Each rung scales with `force_original_aspect_ratio=decrease:force_divisible_by=2`
— fit **inside** the rung box, keep the source's shape, even dimensions, never
upscale. So a `2560×1350` source at the 1440p rung stays **2560×1350** (native),
and its 1080p rung is `1920×1012` — not stretched into an exact `1920×1080`.
(The old `scale=W:H` forced exact dimensions and distorted non-16:9 sources.)
CPU scaling uses **lanczos**; GPU (`scale_cuda`) uses its default (GPU lanczos
isn't in this build).

## 3. Quality — constant-quality (CQ), not fixed bitrate

Fixed `-b:v` spends the same bits on a static shot and an action scene. Instead
every rung uses **CQ-VBR** — a visual-quality target, so complex frames get more
bits — with a `-maxrate` cap so peaks stay streamable:

| | Rate control | NVENC tuning |
|---|---|---|
| **H.264** (`h264_nvenc`) | `-rc vbr -cq 20 -b:v 0` + `-maxrate/-bufsize` cap | `-preset p7 -tune hq -spatial-aq -temporal-aq -rc-lookahead -b_ref_mode middle -multipass fullres` |
| **HEVC** (`hevc_nvenc`) | `-cq 23` (HEVC is more efficient) | `-preset p7 -tune hq -multipass fullres` (AQ/lookahead report "No capable devices" for 10-bit on this Turing card, so kept conservative) |

CPU last-resort uses libx264/libx265 `-crf`.

## 4. Codec routing — SDR vs HDR (dual output)

`is_hdr(media)` checks the source `color_transfer` (`smpte2084` = PQ, `arib-std-b67`
= HLG).

- **SDR source** → **one H.264 ladder** (universal). Done.
- **HDR source** → **two ladders in one master**:
  - **H.264-SDR** (listed first): HDR is tone-mapped to SDR (`zscale` + `tonemap=hable`
    → `bt709`). Plays everywhere.
  - **HEVC-Main10** (10-bit, BT.2020/PQ kept via `-color_primaries/-color_trc`): the
    HDR tier. Plays on Safari / Chrome-with-HEVC.

  The player reads each variant's `CODECS` and picks the best it can decode — HEVC
  where supported, H.264 otherwise. This fixes HDR sources that used to come out as
  unplayable HDR-tagged H.264.

> **Why H.264 is listed first + the codec string matters.** ffmpeg tags HEVC
> variants with a bare `hvc1`, which browsers can't evaluate — Chrome may *claim*
> support then fail to decode 10-bit HEVC and never fall back. `package_cmaf`
> rewrites it to a precise Main10 string **`hvc1.2.4.L153.B0`** so hls.js keeps HEVC
> only where it's genuinely playable, and H.264 is the default variant.

## 5. Encoder/decoder fallback — full-GPU → hybrid → CPU

Per codec, `_encode_one_ladder` tries, in order:

1. **Full GPU** — NVDEC decode + `scale_cuda` + NVENC (fastest). Retried once for
   cold-start NVENC. **Only for SDR sources this GPU can NVDEC-decode.**
2. **Hybrid** — CPU decode + libswscale + **NVENC encode**. Keeps the expensive
   encode on the GPU for sources with no NVDEC path.
3. **CPU** — libx264/libx265 (only if NVENC itself is unavailable).

`can_nvdec_decode(media)` short-circuits step 1 for **AV1** (Turing GTX 1650 has no
AV1 NVDEC) and **10-bit H.264** (NVDEC H.264 is 8-bit only) — they go **straight to
hybrid**, instead of burning ~90s on two doomed full-GPU attempts per job. HDR modes
always CPU-decode (the tonemap needs CPU frames).

Expected GPU behaviour for an AV1 source: **decoder 0%** (CPU), **encoder > 0%**
(NVENC) — that's correct, not "the GPU isn't working."

## 6. Packaging & storage

`package_cmaf` stream-copies (`-c copy`, no re-encode) all video rungs + per-language
AAC audio into ONE CMAF set via the ffmpeg `dash` muxer with `-hls_playlist 1`.
Each codec gets its own DASH **adaptation set** (a set must be single-codec); in the
HLS master they appear as `#EXT-X-STREAM-INF` variants. Output → **MinIO**
`streamsre-hls-segments/<job_id>/` (see `docs/infra-floci.md`), served by the origin
at `/hls/<job_id>/…`. Per title: `master.m3u8`, `media_N.m3u8`, `init-streamN.m4s`,
`chunk-streamN-*.m4s`, `manifest.mpd`, `thumbnail.jpg`.

## 7. Deleting a title

`DELETE /api/v1/movies/{id}` (admin) removes the catalog row **and** every object
under `<job_id>/` in both buckets (segments + raw source). Surfaced in the Library
as a hover **trash button** on ready cards — so re-uploading a title isn't blocked by
the duplicate-title guard.

---

### Re-transcode to pick up pipeline changes

A finished title keeps whatever the pipeline produced at the time. To get new
behaviour (dual HDR, the quality bump, the width-class ladder), **re-transcode** it —
delete + re-upload, or re-enqueue its source (still in `streamsre-raw-uploads`). The
HEVC codec-string fix is the exception: it's applied to the `master.m3u8` text, so it
can be patched in place without a re-encode.
