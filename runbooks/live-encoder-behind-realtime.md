# LiveEncoderBehindRealtime

## Summary
A live channel's encoder is running slower than realtime (`live_encoder_speed_ratio < 0.95`).
A live source is paced at 1.0× wall-clock; if the encoder can't keep up it accumulates
delay, the playlist stops advancing in real time, and viewers eventually stall at the
live edge. This is the defining failure mode of a live channel.

## Impact
- **User-facing?** Yes — increasing latency, then rebuffering/stall at the live edge.
- **SLO affected:** live availability / rebuffer ratio.
- **Severity:** Warning (becomes an outage if it persists and the buffer drains).

## Detection
- **Alert rule:** `live_encoder_speed_ratio < 0.95 and on(event) live_channel_up == 1` for 30s
- **Dashboard:** Grafana → **Live Streaming** → "Encoder speed vs realtime" / "Encoder output fps".
- **Ad hoc:** `curl -s localhost:8091/status/<event_id>` → `speed`, `fps`.

## Triage Steps
1. Identify the channel from the `event` label and how far below 1.0× it is.
2. Is `USE_NVENC=0`? CPU encoding a multi-rung 720p+ ladder is the usual cause on a
   single box — check the packager env.
3. How many channels are active (`live_active_channels`)? More than one on a single GPU
   will contend.
4. Is the host CPU/GPU saturated? (`docker stats streamsre-live-packager`.)

## Remediation
### Quick fix (pick one, least disruptive first)
- [ ] **Enable hardware encode:** set `USE_NVENC=1` (+ uncomment the packager GPU block in
      docker-compose) and restart `live-packager`. NVENC on the GTX 1650 binds under WSL2.
- [ ] **Lower the ladder ceiling:** recreate the channel with a smaller `max_height`
      (e.g. 480). Fewer/smaller rungs = less encode work. (480p sat at ~1.0× on CPU.)
- [ ] **Reduce concurrency:** keep `LIVE_MAX_CHANNELS=1` on a single encoder; end other
      channels.
- [ ] **Cheaper preset:** raise `LIVE_X264_PRESET` toward `ultrafast`.

### Root cause investigation
- [ ] `docker compose logs live-packager` for ffmpeg warnings (dropped frames, HW init).
- [ ] Confirm the source itself isn't the bottleneck (a stuttering ingest feed shows as
      low fps too — check `live-ingest` and the encoder's upload).

## Escalation
- **After 15 min with no progress and viewers stalling:** end the channel (`/stop`), post
  a status note, and switch the source to a lower rung before restarting.

## Post-Incident
- [ ] Record the ladder/encode settings that held realtime for this content class.
- [ ] Consider making NVENC the default for live if CPU margin is consistently thin.
