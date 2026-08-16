# Live streaming

StreamSRE streams **live** as well as on-demand. A channel is either fed by a real
encoder pushing into the ingest server (OBS / SRT / a browser via WHIP) or by
re-streaming an already-uploaded title in real time ("go live from an upload").
Both produce the **same standard HLS ABR ladder**, served by the origin at
`/live/<id>/`, so the existing player, tunnel gateway, and Render viewer serve
live with almost no change from VOD.

Live is **additive** — it does not replace the on-demand path. Uploads, the
catalog, the transcode pipeline, and the player's VOD mode are untouched.

---

## Architecture

```
                 ADMIN / PRODUCER SIDE (host-only, never tunneled)
 OBS ──RTMP──┐
 SRT enc ─SRT┼─▶ live-ingest (MediaMTX) ──auth──▶ upload-api /live/mediamtx-auth
 Browser WHIP┘        │  (validates the stream key)
                      └────────── pull (RTMP) ─────────────┐
 "go live from ───────────────────────────────────────────▼
  an upload"  ──────▶ live-packager (ffmpeg + optional NVENC)
                        ffmpeg -re from S3 / pull  ──▶ live_segments volume
                        │ Prometheus metrics                     │
   scheduler (upload-api background loop)                        ▼
   auto go-live / auto-end / scheduled start-stop        origin  /live/<id>/  (public playback)
                                                                 │ (record: #EXT-X-ENDLIST + copy)
   catalog: dynamodb-local  streamsre-live-events                ▼
   (state, stream key server-side)                        /hls/<vod>/  replay VOD + catalog row
```

### Components

| Service | Role |
|---|---|
| `live-ingest` (MediaMTX) | RTMP `:1935` / SRT `:8890` / WHIP `:8889` ingest. Authorizes publishes against the upload API (stream key). API `:9997` + metrics `:9998`. **Host-only — never on the public tunnel.** |
| `live-packager` (FastAPI + ffmpeg) | Owns the per-channel live ffmpeg. Re-streams an uploaded title (playout) or pulls the encoder feed (ingest) into a rolling HLS ladder on the shared `live_segments` volume. Exposes `/metrics`. |
| `upload-api` (`routes/live.py` + services) | Control plane: create/list/start/stop/delete events, the `LiveEvent` catalog (`streamsre-live-events`), the MediaMTX auth hook, and the lifecycle **scheduler**. |
| `origin` | Serves the live window from disk at `/live/` (lowest latency), separate from the MinIO-backed `/hls/`. |

The stream key is a **secret**: the admin listing returns it, the public listing
and the sanitized `LiveEventPublic` projection never do. Ingest is a write path,
so its ports stay host/admin-only; only `/live/*` playback is public.

---

## Lifecycle (the scheduler)

A single background loop in the upload API reconciles state every few seconds so
the admin never has to babysit a channel:

| Transition | Trigger |
|---|---|
| `scheduled → live` | `scheduled_start` reached (playout starts; ingest opens the slot) |
| `idle/starting → live` | an encoder connects to the ingest server (**auto go-live**, no click) |
| `live → ended` | encoder disconnects, after a reconnect **grace** window (`LIVE_INGEST_GRACE_SECONDS`, default 20s) |
| `live → ended` | a non-looping playout's source finishes, or `scheduled_end` is reached |

MediaMTX publisher presence is read from its control API (`/v3/paths/list`); the
grace window absorbs brief encoder reconnects without flapping the channel.

---

## Record-to-VOD (replay, no re-encode)

A recorded channel (`record_to_vod`) keeps **every** segment during the stream
(`hls_list_size 0`, no rolling delete) instead of the low-latency rolling window.
The live segments are *already* a complete ABR HLS ladder, so on end there is **no
transcode**: ffmpeg writes `#EXT-X-ENDLIST`, the packager copies the segment folder
to the segments bucket under a new id, and the upload API registers a catalog row —
title `"<event> — Live <date>"`, genre `Live`, tagged with the stream date/time.
The replay then plays as an ordinary VOD via `/hls/<id>/`.

> Recording keeps all segments, so disk grows for the duration of the stream —
> intended for events, not 24/7 channels.

---

## Latency

Live ships as **standard HLS** (~6–10s glass-to-glass), which is rock-solid. The
player runs `lowLatencyMode` for live sources to sync tightly to the live edge.

**True LL-HLS** (`EXT-X-PART` partial segments, ~2s) is intentionally *not* faked:
ffmpeg's `hls` muxer cannot emit `EXT-X-PART`, so real LL-HLS needs a different
packager (MediaMTX's own LL-HLS egress — which loses the multi-rung ABR + origin
routing — or a dedicated packager like Shaka). That is a real architecture fork
and is scoped as follow-up; the player is already LL-ready.

---

## Observability

The packager exports per-channel metrics (`event` label):

| Metric | Meaning |
|---|---|
| `live_channel_up` | 1 while a channel is encoding |
| `live_encoder_speed_ratio` | encoder speed vs realtime — **≥ 1.0 = keeping up** |
| `live_encoder_fps` | encoder output fps |
| `live_active_channels` | number of active channels |

Prometheus scrapes `live-packager` and `live-ingest`; Grafana ships a **Live
Streaming** dashboard (`/d/live-streaming`). Alerts: `LiveEncoderBehindRealtime`,
`LiveEncoderStalled`, `LivePackagerDown`, `LiveIngestDown`. Runbook:
[`runbooks/live-encoder-behind-realtime.md`](../runbooks/live-encoder-behind-realtime.md).

> On a single consumer GPU keep `LIVE_MAX_CHANNELS=1`. A 720p 3-rung ladder sits
> ~0.93× on CPU; set `USE_NVENC=1` for headroom (`LiveEncoderBehindRealtime` alerts on it).

---

## AWS mapping

The local build mirrors the composable AWS live topology, the same way MinIO and
dynamodb-local stand in for S3 and DynamoDB.

| Production AWS | Local stand-in |
|---|---|
| **Amazon IVS** (turnkey) **or MediaLive** (RTMP/SRT push **or MP4/HLS pull = go-live-from-upload**) | `live-ingest` (MediaMTX) + `live-packager` (ffmpeg ladder) |
| **MediaPackage** (JIT packaging, DVR, live→VOD harvest) | `live-packager` HLS + origin `/live/` + record-to-VOD |
| **CloudFront + S3** | origin nginx + `live_segments` / MinIO |
| **EventBridge Scheduler + Step Functions** | scheduler loop in the upload API |
| **DynamoDB** | dynamodb-local `streamsre-live-events` |

---

## Using it

**Admin → Live tab** (`/admin`):

- **Go live from an upload** — pick a ready title, choose quality, optionally loop /
  record. Click **Go live**.
- **Encoder ingest** — create an ingest channel, copy the `rtmp://localhost:1935/live/<key>`
  push URL + stream key into OBS, start streaming. It **auto-goes-live** on connect
  (or hit **Go live** to force it).
- **Schedule** — set a start time to create the channel `scheduled`; it auto-starts.
- **Save replay** — keep the finished stream as a replay VOD.

Viewers see a **"Live & upcoming"** rail on the home and browse pages; audio-only
channels render a now-playing card. Watch links are `/player?live=<id>`.

### Config (`.env`)

```
LIVE_ENABLED=1
LIVE_INGEST_RTMP_HOST=localhost:1935     # shown to the admin's encoder
LIVE_HLS_TIME=4                          # segment length
LIVE_HLS_LIST_SIZE=6                     # rolling-window size
LIVE_MAX_HEIGHT=1080                     # ladder ceiling
LIVE_MAX_CHANNELS=1                      # keep at 1 on a single GPU
USE_NVENC=0                              # 1 = hardware live encode
```
