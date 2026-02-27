#!/usr/bin/env sh
set -eu

SERVICES="upload-api transcode-worker origin beacon-collector frontend"

for svc in $SERVICES; do
  echo "Scanning image for service: $svc"
  docker build -t "streamsre-${svc}:scan" "./services/${svc}" || continue
  trivy image --exit-code 1 --severity HIGH,CRITICAL "streamsre-${svc}:scan"
done

