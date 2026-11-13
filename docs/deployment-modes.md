# StreamSRE Deployment Modes

StreamSRE supports two related runtime roles:

1. **Publisher (Laptop A):** accepts source video, probes media, transcodes it,
   packages HLS/DASH/CMAF output, and sends a completed artifact bundle to the
   relay.
2. **Relay (Laptop B):** stores temporary packaged media, serves HTTPS playback,
   runs the watch-party room, and exposes operational metrics.

Laptop B is intentionally not a second transcoding machine. It should be a
small, restricted media relay rather than an unrestricted copy of the publisher
stack.

## Codec Ownership Boundary

Only Laptop A may perform codec-related work:

- source probing and codec detection;
- FFmpeg decoding and encoding;
- GPU/NVENC/NVDEC use;
- bitrate ladder selection;
- HDR-to-SDR conversion;
- CMAF, HLS, and DASH packaging;
- thumbnail or preview generation.

Laptop B must not run FFmpeg, ffprobe, a GPU runtime, or a media decoder. The
relay accepts a completed artifact bundle containing manifests, segments,
metadata, and checksums. Its validation is structural only: paths, sizes,
checksums, manifest references, expiration metadata, and the publisher's
signature. It does not inspect or convert compressed video frames.

An artifact manifest should carry the codec facts produced by Laptop A, for
example:

```json
{
  "movie_id": "movie-a81f2",
  "format": "hls-cmaf",
  "duration_seconds": 7200,
  "renditions": ["360p", "720p", "1080p"],
  "codecs": ["avc1.640028", "mp4a.40.2"],
  "objects": 1842,
  "sha256": "...",
  "expires_at": "2026-11-15T01:00:00Z"
}
```

The relay treats these values as signed publisher metadata. It may reject an
invalid bundle, but it does not become responsible for determining whether the
codec is playable.

## Laptop B Sandbox

The relay should be deployed on a dedicated or isolated Ubuntu installation.
Container isolation is an additional control, not a substitute for host
patching and firewall rules.

Required controls:

- run relay containers as a non-root user;
- use rootless Docker where practical;
- never mount `/var/run/docker.sock`;
- do not install FFmpeg, GPU drivers, or codec toolchains on the relay;
- use read-only container filesystems where possible;
- drop Linux capabilities and enable `no-new-privileges`;
- apply seccomp/AppArmor profiles;
- mount only the temporary media volume and required configuration;
- restrict public exposure to the HTTPS gateway;
- keep S3 administration, databases, metrics, and Docker management private;
- apply CPU, memory, process, storage, and concurrent-viewer limits;
- restrict relay egress to required storage, telemetry, and update endpoints;
- keep publisher upload credentials short-lived, scoped, and revocable;
- log security events without storing source media, chat contents, or full IPs.

The relay service must remain useful if the publisher disconnects. After the
bundle reaches `ready`, Laptop B owns room scheduling, playback authorization,
chat, presence, cleanup, and delivery until expiration.

## Runtime Roles

### Standalone

One computer runs the existing local stack. This mode is for development and
private viewing and keeps the current upload/transcode/player workflow.

### Publisher

Laptop A runs the upload API and transcode worker. It creates a staging bundle,
calculates checksums, signs the artifact manifest, and transfers the completed
bundle to Laptop B over an authenticated channel.

### Relay

Laptop B runs the gateway, party service, origin, temporary object storage,
cleanup worker, and relay metrics. It does not process source video.

## Phased Delivery

### Phase 0: Branch and baseline

- branch from the newest `origin/dev`;
- preserve and validate existing local changes;
- document deployment roles and security assumptions.

### Phase 1: Harden standalone mode

- make CPU-only Compose startup reliable;
- keep GPU reservations only in the GPU override;
- remove default credentials from active deployments;
- use same-origin configuration for browser requests;
- add service health checks and smoke tests.

### Phase 2: Build the Laptop B relay

- add a relay Compose profile/configuration using the existing gateway boundary;
- keep the relay profile free of Redis, extra databases, and codec services;
- add CIDR/interface controls only at the network boundary when required;
- add private storage and scoped publisher pairing;
- add artifact upload, checksum verification, and ready-state publication;
- enforce storage, duration, viewer, and bandwidth quotas;
- ensure the relay has no FFmpeg, ffprobe, GPU, or Docker socket access.

### Phase 3: Add temporary media lifecycle

- expire media after the event retention window;
- deny new playback before deleting objects;
- delete by movie prefix with retries;
- retain aggregate operational metrics separately.

### Phase 4: Add watch-party control

- private invitation links;
- scheduled premieres with IANA timezones;
- host-authorized playback state;
- WebSocket presence and chat;
- reconnect and catch-up behavior.

### Phase 5: Add networking options

- Caddy plus dynamic DNS for direct HTTPS where port forwarding works;
- Tailscale for private administration;
- tunnel support for UI and signaling experiments;
- document CGNAT and bandwidth limitations.

### Phase 6: Add optional voice and P2P

- WebRTC voice signaling over the party WebSocket;
- STUN first, TURN only when justified;
- optional HLS segment P2P with HTTP fallback;
- measure actual peer offload rather than assuming it.

## Capacity Calculations

For an average delivered bitrate of $R$ Mbps, $N$ viewers, and protocol
overhead $O$:

$$
B_{\text{required}} = N \times R \times (1 + O)
$$

With peer offload fraction $P$:

$$
B_{\text{relay}} = N \times R \times (1 - P) \times (1 + O)
$$

Example: 10 viewers, 6 Mbps each, 20% overhead, and no P2P:

$$
B_{\text{relay}} = 10 \times 6 \times 1.2 = 72\text{ Mbps}
$$

At 50% measured peer offload:

$$
B_{\text{relay}} = 10 \times 6 \times 0.5 \times 1.2 = 36\text{ Mbps}
$$

These are planning estimates. The relay's actual capacity must be measured
against its upload link, disk throughput, origin latency, and concurrent HTTP
connections.

## Acceptance Tests for Laptop B

- a relay image contains no FFmpeg or GPU runtime;
- the relay cannot access the Docker socket;
- an unauthenticated client cannot upload or read storage administration APIs;
- a publisher cannot read another publisher's media;
- malformed paths and checksum mismatches are rejected;
- media is not advertised before the complete bundle is verified;
- playback is denied after expiration;
- cleanup retries failed deletions and exposes a metric;
- the room continues after Laptop A shuts down;
- a relay restart preserves ready media and room state as designed;
- only Laptop A performs codec inspection and transcoding.

## Relay Profile Startup

The first relay profile uses the existing gateway and persistent Compose
services. It does not start Cloudflared automatically and does not add Redis or
another stateful service:

```bash
RELAY_BIND_ADDRESS=127.0.0.1 \
  docker compose -f docker-compose.yml -f docker-compose.relay.yml \
  --profile relay up -d gateway
```

For a protected reverse proxy or firewall on Laptop B, keep the gateway bound
to loopback. If a deliberately managed LAN interface is required, set
`RELAY_BIND_ADDRESS` to that interface address and enforce an allowlist at the
host firewall. Do not bind it to `0.0.0.0` by default.

## Artifact Ingress

The first Laptop B transfer path is intentionally separate from viewer traffic:

```text
Laptop A
  completed HLS/CMAF bundle + artifact.json
        |
        | HTTPS or private relay network, Bearer token
        v
Laptop B :8010/v1/artifacts
  validate paths, checksums, size, and manifest
        |
        v
MinIO streamsre-hls-segments/relay/<movie_id>/
  ready.json written only after every object succeeds
```

The ingress accepts a gzip tar bundle whose first file is `artifact.json`.
Every listed object must have a SHA-256 checksum. The service rejects absolute
paths, `..` traversal, duplicate files, unexpected files, incomplete bundles,
and bundles above `RELAY_MAX_BUNDLE_MB`.

The endpoint is not routed through the public viewer gateway. It is an
operator-to-relay transfer surface and should be reachable only through a
private network, a firewall allowlist, or a separately authenticated HTTPS
reverse proxy. The token is configured with `RELAY_INGRESS_TOKEN` and should
be generated with at least 32 random bytes, for example:

```bash
openssl rand -hex 32
```

The ingress first writes to `relay-staging/<movie_id>/`. It copies objects to
the public `relay/<movie_id>/` prefix only after all checksums pass, then writes
`ready.json`. This prevents viewers from reading a partially transferred
bundle. A verified HLS master is available through the relay gateway as:

```text
https://<relay-host>/relay/<movie_id>/master.m3u8
```

Public catalog registration and room scheduling are later phases.

## Laptop B Setup

### Branch and software

Laptop B must use the same implementation branch as Laptop A. After pushing the
branch from the development machine, run:

```bash
git clone https://github.com/ritikZ18/video-streaming-sre.git
cd video-streaming-sre
git switch --track origin/feat/watch-party-relay
```

If the branch is not pushed yet, transfer the repository or a Git bundle from
Laptop A first; do not silently use `main` for the relay.

Install only the relay host prerequisites:

- Ubuntu Server 24.04 LTS or another supported Linux host;
- Docker Engine;
- Docker Compose v2 plugin;
- Git, `curl`, and `openssl`;
- a persistent SSD location for Docker volumes and relay media;
- wired Ethernet where possible.

Do **not** install FFmpeg, ffprobe, NVIDIA drivers, CUDA, or a codec toolchain
on Laptop B. Laptop A owns all source decoding, encoding, and packaging.

Check the installation before starting:

```bash
docker version
docker compose version
git --version
curl --version
openssl version
```

Run these steps on Laptop B. Keep the token in a protected `.env` file and do
not paste it into chat or commit it:

```bash
git clone <repository-url>
cd video-streaming-sre
cp .env.example .env
openssl rand -hex 32
```

Set the generated value in `.env`:

```text
RELAY_INGRESS_TOKEN=<generated-value>
RELAY_BIND_ADDRESS=127.0.0.1
PARTY_ADMIN_TOKEN=<another-generated-token>
```

Set the required admin and Grafana passwords too, then start the relay profile:

```bash
./start.sh
docker compose -f docker-compose.yml -f docker-compose.relay.yml \
  --profile relay up -d --build
curl http://127.0.0.1:8010/health
```

For a separate private network between the laptops, bind `RELAY_BIND_ADDRESS`
to Laptop B's private interface address and allow only Laptop A's IP at the host
firewall. Do not expose port `8010` to the public internet without an
authenticated HTTPS reverse proxy.

Recommended host firewall policy on Laptop B:

```bash
sudo ufw default deny incoming
sudo ufw allow from <laptop-a-private-ip> to any port 8010 proto tcp
sudo ufw allow from <trusted-admin-ip> to any port 22 proto tcp
sudo ufw enable
```

If guests will connect directly to Laptop B for playback, expose only the
gateway's HTTPS port through a separately configured reverse proxy or router.
Keep port `8010` restricted to Laptop A.

## Laptop A Transfer

On Laptop A, stage the already-packaged HLS/CMAF directory from the existing
segments bucket. The directory must contain manifests and media segments, not a
source movie. Then create and upload the bundle:

```bash
python3 scripts/export-relay-artifact.py \
  movie-a81f2 ./relay-staging/movie-a81f2 relay-out/movie-a81f2.tar.gz \
  --duration-seconds 7200 \
  --expires-at 2026-11-15T01:00:00Z

scripts/upload-relay-artifact.sh \
  http://<laptop-b-private-ip>:8010 \
  relay-out/movie-a81f2.tar.gz \
  "$RELAY_INGRESS_TOKEN"
```

The upload response must report `"status":"ready"`. Laptop B writes the
objects under `relay/<movie_id>/` and only then creates `ready.json`. The
publisher can shut down after this response; public watch-party registration
and playback routing will be added in the next phase.

## Watch-Party API

Create rooms from the operator side with the party admin token:

```bash
curl -X POST http://127.0.0.1:8088/api/party/rooms \
  -H "Authorization: Bearer $PARTY_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"movie_id":"movie-a81f2","title":"Friday Movie Night"}'
```

Guests redeem the returned 10-digit `code` with:

```text
POST /api/party/rooms/<code>/join
```

The response contains a short-lived bearer session bound to that room and
movie. The browser sends it on every `/hls/<movie_id>/...` request. The party
WebSocket carries the session as a subprotocol (not in the URL, where proxies
would log it) and supports chat, readiness, presence, and QoE heartbeats.
Playback position is derived from the server clock; viewers cannot publish
play/pause/seek changes. Scheduled media authorization returns `403` before the
curtain time, anonymous media returns `401`, and ended rooms revoke access.

Room metadata is durable in DynamoDB-local. Active connections, participant
diagnostics, and recent events are intentionally in memory on the single relay
instance.
