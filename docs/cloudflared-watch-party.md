# Cloudflared watch-party deployment

This is the single-node deployment. The admin laptop stores and transcodes the
video, hosts the local admin UI, and exposes only the viewer API, HLS media, and
party service through a free Cloudflare Quick Tunnel. No relay server is used.

## One-time setup

1. Copy `.env.example` to `.env` and replace every `change-this-*` value. Generate
   `PARTY_ADMIN_TOKEN` with `openssl rand -hex 32`.
2. Deploy `frontend/` as a Node web service (Render is the documented default):
   build command `npm ci && npm run build`, start command `npm start`, root
   directory `frontend`, and environment variable `NEXT_PUBLIC_VIEWER_ONLY=1`.
3. Put the resulting HTTPS URL in `.env` as `VIEWER_URL`.
4. Start the local stack with `./start.sh` and upload/transcode a title in
   `http://localhost:3001/admin`.

## Start and share a party

1. Run `./start.sh --tunnel`. This starts the gateway, party service, and
   Cloudflared, verifies the public endpoint, and prints a viewer link containing
   the temporary backend address.
2. Open the printed viewer link once on each viewer device. The frontend stores
   the current tunnel address in that browser.
3. In the local admin UI, choose a ready title under **Create a watch party**.
   Optionally choose a scheduled time, then copy the generated 10-digit code.
4. Guests open the hosted frontend, visit `/party`, and enter that code. A
   scheduled title remains locked until its start time.

Quick Tunnel hostnames change whenever Cloudflared restarts and may be reclaimed
after idle periods. Re-run `./start.sh --tunnel` and share/open the newly printed
viewer link when that happens. For a stable production URL, replace the Quick
Tunnel with a named Cloudflare Tunnel and a domain.

The gateway rejects upload/catalog mutations; administration remains on the
local UI. Party creation additionally requires the same Basic credentials used
by the admin studio.
