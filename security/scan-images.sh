#!/usr/bin/env sh
set -eu

SERVICES="upload-api transcode-worker origin beacon-collector"

scan_image() {
  image=$1
  if command -v trivy >/dev/null 2>&1; then
    trivy image --exit-code 1 --severity HIGH,CRITICAL "$image"
    return
  fi

  # Keep the scanner self-contained for clean CI runners and local `act` runs.
  docker run --rm \
    -v /var/run/docker.sock:/var/run/docker.sock \
    aquasec/trivy:0.71.0 \
    image --exit-code 1 --severity HIGH,CRITICAL "$image"
}

for svc in $SERVICES; do
  echo "Scanning image for service: $svc"
  docker build -t "streamsre-${svc}:scan" "./services/${svc}"
  scan_image "streamsre-${svc}:scan"
done

echo "Scanning image for service: frontend"
docker build -t "streamsre-frontend:scan" "./frontend"
scan_image "streamsre-frontend:scan"
