#!/usr/bin/env bash
#
# Generate a short test clip and push it through the upload -> transcode ->
# HLS/DASH pipeline, so `make demo` yields something playable end to end.
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
TMP="$(mktemp -d)"
CLIP="$TMP/demo.mp4"

echo "Generating a 15s test clip with ffmpeg..."
ffmpeg -y -loglevel error \
  -f lavfi -i "testsrc2=size=1280x720:rate=24:duration=15" \
  -f lavfi -i "sine=frequency=440:duration=15" \
  -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "$CLIP"

echo "Uploading to ${API_URL}/api/v1/upload ..."
RESP="$(curl -sS -X POST "${API_URL}/api/v1/upload" -F "file=@${CLIP};type=video/mp4")"
echo "Response: ${RESP}"

JOB_ID="$(printf '%s' "$RESP" | sed -n 's/.*"job_id"[: ]*"\([^"]*\)".*/\1/p')"
if [ -n "${JOB_ID}" ]; then
  echo ""
  echo "Job queued: ${JOB_ID}"
  echo "After the worker finishes, manifests will be served at:"
  echo "  HLS:  http://localhost:8080/hls/${JOB_ID}/master.m3u8"
  echo "  DASH: http://localhost:8080/hls/${JOB_ID}/manifest.mpd"
fi

rm -rf "${TMP}"
