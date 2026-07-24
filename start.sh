#!/usr/bin/env bash
#
# One-command bring-up for the whole platform:
#   floci (local AWS emulator)  ->  Terraform infra  ->  Docker Compose services
#
# Usage:
#   ./start.sh            # start floci + infra + services
#   ./start.sh --seed     # also push a generated demo video through the pipeline
#
# Override the floci control script location if yours lives elsewhere:
#   FLOCI=/path/to/floci.sh ./start.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

FLOCI="${FLOCI:-$HOME/floci-stack/floci.sh}"
ENDPOINT="http://localhost:4566"
FLOCI_HEALTH="${ENDPOINT}/_floci/health"

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }

floci_up() {
  curl -fsS "$FLOCI_HEALTH" >/dev/null 2>&1
}

# 1) Environment file --------------------------------------------------------
if [ ! -f .env ]; then
  log "Creating .env from .env.example"
  cp .env.example .env
fi

# 2) floci (local AWS on :4566) ---------------------------------------------
if floci_up; then
  log "floci already running on ${ENDPOINT}"
elif [ -f "$FLOCI" ]; then
  log "Starting floci ($FLOCI)"
  bash "$FLOCI" up
else
  echo "ERROR: floci control script not found at: $FLOCI" >&2
  echo "Start your local AWS emulator on :4566, or re-run with FLOCI=/path/to/floci.sh" >&2
  exit 1
fi

log "Waiting for floci to be healthy on ${ENDPOINT}"
for _ in $(seq 1 30); do
  if floci_up; then break; fi
  sleep 1
done
if ! floci_up; then
  echo "ERROR: floci did not become healthy in time." >&2
  exit 1
fi

# 3) Infrastructure as code (S3 buckets + SQS queues + DynamoDB table) -------
# Terraform is the "real" path; if it is not installed the services will
# lazily self-create the same resources in floci on first use.
if command -v terraform >/dev/null 2>&1; then
  log "Provisioning infra with Terraform (S3 + SQS + DynamoDB)"
  (
    cd infra/terraform
    terraform init -input=false >/dev/null
    terraform apply -auto-approve
  )
else
  log "Terraform not installed — services will self-create S3/SQS/DynamoDB on first use"
fi

# 4) GPU detection -----------------------------------------------------------
# Use NVENC only if an NVIDIA GPU AND the docker nvidia runtime are both present.
COMPOSE_ARGS=""
detect_gpu() {
  command -v nvidia-smi >/dev/null 2>&1 || return 1
  nvidia-smi -L >/dev/null 2>&1 || return 1
  if docker info 2>/dev/null | grep -qiE 'Runtimes:.*nvidia' \
     || command -v nvidia-container-runtime >/dev/null 2>&1; then
    return 0
  fi
  return 2  # GPU present, but no container runtime
}

detect_gpu; gpu=$?
if [ "$gpu" -eq 0 ]; then
  log "NVIDIA GPU + container runtime detected -> enabling NVENC (GPU transcode)"
  COMPOSE_ARGS="-f docker-compose.yml -f docker-compose.gpu.yml"
elif [ "$gpu" -eq 2 ]; then
  log "NVIDIA GPU detected but nvidia-container-toolkit is not set up -> CPU transcode"
  echo "  Enable the GPU with:"
  echo "    sudo apt-get install -y nvidia-container-toolkit"
  echo "    sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker"
  echo "  then re-run ./start.sh"
else
  log "No NVIDIA GPU detected -> CPU transcode"
fi

# 5) Application services -----------------------------------------------------
log "Building & starting services (docker compose)"
docker compose $COMPOSE_ARGS up -d --build

# 6) Optional demo seed ------------------------------------------------------
if [ "${1:-}" = "--seed" ]; then
  log "Seeding a generated demo video (waiting for the API to be ready)"
  sleep 8
  bash scripts/seed-test-video.sh || echo "seed step failed (services may still be starting)"
fi

log "Platform is up. Open:"
cat <<'EOF'
  Frontend (Apple-TV UI):  http://localhost:3001
  Upload API (docs):       http://localhost:8000/docs
  Beacon API (docs):       http://localhost:8001/docs
  Origin (HLS/DASH):       http://localhost:8080
  Grafana:                 http://localhost:3000
  Prometheus:              http://localhost:9090
  Alertmanager:            http://localhost:9093

Upload a video at http://localhost:3001/upload — it transcodes to HLS+DASH,
appears on the home grid, and streams when you click it.

Stop with:  ./stop.sh        (services only)
            ./stop.sh --all  (also stop floci)
EOF
