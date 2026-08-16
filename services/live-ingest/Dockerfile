# StreamSRE live ingest — MediaMTX (RTMP/SRT/WHIP) with our config baked in.
# Ingest-only: it authorizes pushes via the upload API and is pulled by the
# live-packager. Never exposed through the public tunnel.
FROM bluenviron/mediamtx:latest

# The binary reads /mediamtx.yml by default; overwrite it with ours.
COPY mediamtx.yml /mediamtx.yml

# rtmp / srt(udp) / webrtc / api / metrics
EXPOSE 1935 8890/udp 8889 9997 9998
