#!/usr/bin/env bash
#
# Diagnose the running pipeline: floci health, container status, worker logs,
# and the actual S3 / SQS / DynamoDB state. Run this when uploads seem stuck.
#
#   bash scripts/diagnose.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1
EP="${AWS_ENDPOINT_URL:-http://localhost:4566}"

hr() { printf '\n\033[1;36m===== %s =====\033[0m\n' "$1"; }

hr "floci health ($EP)"
curl -fsS "$EP/_floci/health" && echo "  (floci OK)" || echo "  FLOCI NOT REACHABLE"

hr "containers"
docker compose ps 2>&1

hr "transcode-worker logs (tail 50)"
docker compose logs --tail=50 transcode-worker 2>&1 | tail -50

hr "upload-api logs (tail 20)"
docker compose logs --tail=20 upload-api 2>&1 | tail -20

hr "S3 buckets"
aws --endpoint-url "$EP" s3 ls 2>&1

hr "segments produced (first 25 keys)"
aws --endpoint-url "$EP" s3 ls s3://streamsre-hls-segments/ --recursive 2>&1 | head -25

hr "DynamoDB catalog (id + status)"
aws --endpoint-url "$EP" dynamodb scan --table-name streamsre-catalog \
  --projection-expression "id, #s, manifest_url" \
  --expression-attribute-names '{"#s":"status"}' 2>&1 | head -60

hr "SQS queues + message counts"
aws --endpoint-url "$EP" sqs list-queues 2>&1
for q in streamsre-transcode-queue streamsre-transcode-dlq; do
  url="$EP/000000000000/$q"
  echo "--- $q ---"
  aws --endpoint-url "$EP" sqs get-queue-attributes --queue-url "$url" \
    --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible 2>&1 | tail -8
done
