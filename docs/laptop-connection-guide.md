# StreamSRE Laptop A to Laptop B Connection Guide

This guide connects the publisher laptop (Laptop A) to the relay laptop
(Laptop B) without Redis, a second transcoder, or a public storage port.

## Roles

```text
Laptop A                         Laptop B
Publisher                        Relay
-----------                      -----------
Upload source                   Store verified HLS/CMAF
FFmpeg / GPU transcode          Serve relay playback
Create checksums                Run party rooms/chat
Send artifact bundle  --------> Cleanup and observability
```

Only Laptop A installs or runs codec tooling. Laptop B receives completed
artifacts and does not decode, encode, or package video.

## Prerequisites

Both laptops need Git, Docker Engine, Docker Compose v2, `curl`, and OpenSSL.
Laptop B should use wired Ethernet and an SSD for Docker volumes. Do not install
FFmpeg, ffprobe, CUDA, or NVIDIA tooling on Laptop B.

Both machines use the same branch during this phase:

```bash
git clone https://github.com/ritikZ18/video-streaming-sre.git
cd video-streaming-sre
git switch --track origin/feat/watch-party-relay
```

## Choose the connection

### Same private LAN

Find Laptop B's private address:

```bash
ip -br address
```

Use the address on the trusted Ethernet/Wi-Fi interface, for example
`192.168.1.50`. Do not use `127.0.0.1` for cross-laptop traffic.

### Separate networks or CGNAT

Use a private overlay such as Tailscale or WireGuard. The relay still binds to
the private interface address, and only Laptop A's overlay IP may access port
`8010`. Do not expose MinIO, DynamoDB, Grafana, Prometheus, or the ingress
port directly to the internet.

## Configure Laptop B

```bash
cp .env.example .env
openssl rand -hex 32
```

Set these values in `.env`:

```text
ADMIN_USERNAME=<unique-admin-name>
ADMIN_PASSWORD=<unique-admin-password>
GRAFANA_ADMIN_PASSWORD=<unique-grafana-password>
RELAY_INGRESS_TOKEN=<32-byte-token>
PARTY_ADMIN_TOKEN=<another-32-byte-token>
RELAY_BIND_ADDRESS=192.168.1.50
MAX_UPLOAD_SIZE_MB=10000
```

Start the relay:

```bash
./start.sh
docker compose -f docker-compose.yml -f docker-compose.relay.yml \
  --profile relay up -d --build
curl http://192.168.1.50:8010/health
```

The first command starts the persistent MinIO, DynamoDB-local, origin, and
observability services. The second enables only the relay ingress, party
service, and gateway profile additions.

## Firewall on Laptop B

Allow only Laptop A to upload artifacts:

```bash
sudo ufw default deny incoming
sudo ufw allow from <laptop-a-ip> to any port 8010 proto tcp
sudo ufw allow from <admin-ip> to any port 22 proto tcp
sudo ufw enable
```

Viewer traffic should enter through the gateway or a separately configured
HTTPS reverse proxy. Port `8010` is for publisher-to-relay transfer only.

## Prepare Laptop A

After a movie is ready, stage its already-packaged HLS/CMAF directory. Do not
stage the original MKV/MP4 for relay transfer:

```bash
python3 scripts/export-relay-artifact.py \
  movie-a81f2 ./relay-staging/movie-a81f2 relay-out/movie-a81f2.tar.gz \
  --duration-seconds 7200 \
  --expires-at 2026-11-15T01:00:00Z
```

Upload to Laptop B:

```bash
scripts/upload-relay-artifact.sh \
  http://192.168.1.50:8010 \
  relay-out/movie-a81f2.tar.gz \
  '<relay-ingress-token>'
```

The response must contain `"status":"ready"`. Playback is then available at:

```text
http://192.168.1.50:8088/relay/movie-a81f2/master.m3u8
```

## Party Room

Create a room from Laptop B:

```bash
curl -X POST http://127.0.0.1:8088/api/party/rooms \
  -H 'Authorization: Bearer <party-admin-token>' \
  -H 'Content-Type: application/json' \
  -d '{"movie_id":"movie-a81f2","title":"Friday Movie Night"}'
```

Share the resulting room and invite token through the party UI. Keep invite
tokens private; anyone holding one can join that room.

## Checks

```bash
docker compose ps
curl http://192.168.1.50:8010/health
curl http://192.168.1.50:8088/healthz
curl -I http://192.168.1.50:8088/relay/movie-a81f2/master.m3u8
```

For troubleshooting:

```bash
docker compose logs relay-ingress party-service origin gateway
```

If the artifact upload works but playback returns 404, verify the artifact
contains `master.m3u8`, the movie ID matches the URL, and `ready.json` exists
under `relay/<movie_id>/` in MinIO.