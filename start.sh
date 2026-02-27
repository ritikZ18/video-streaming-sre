#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "${ROOT_DIR}"

if [ ! -f ".env" ]; then
  echo "No .env found, copying from .env.example..."
  cp .env.example .env
fi

echo "Running test suite..."
if [ -x "./scripts/run-all-tests.sh" ]; then
  ./scripts/run-all-tests.sh
else
  echo "scripts/run-all-tests.sh not found or not executable, skipping tests."
fi

echo "Starting StreamSRE stack with Docker Compose..."
docker compose up -d --build

echo "StreamSRE is starting."
echo "Frontend:        http://localhost:3001"
echo "Upload API:      http://localhost:8000/docs"
echo "Beacon API:      http://localhost:8001/docs"
echo "Prometheus:      http://localhost:9090"
echo "Grafana:         http://localhost:3000"

