#!/usr/bin/env sh
set -eu

echo "Starting StreamSRE stack..."
docker compose up -d --build

echo "Seeding demo video (if script exists)..."
if [ -x "./scripts/seed-test-video.sh" ]; then
  ./scripts/seed-test-video.sh || true
fi

echo "Stack started. Frontend on http://localhost:3001"

