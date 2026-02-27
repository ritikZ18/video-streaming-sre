#!/usr/bin/env sh
set -eu

echo "Running backend tests..."
for svc in transcode-worker beacon-collector; do
  echo "==> ${svc}"
  cd "services/${svc}"
  pytest -q
  cd - >/dev/null
done

echo "Skipping frontend tests in this environment."

echo "All backend tests passed."

