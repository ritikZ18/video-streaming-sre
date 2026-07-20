#!/usr/bin/env bash
#
# Stop the platform.
#   ./stop.sh          stop the Docker Compose services (floci left running)
#   ./stop.sh --all    also stop the floci local AWS stack
#   ./stop.sh --clean  stop services AND remove volumes/images (compose down -v)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

FLOCI="${FLOCI:-$HOME/floci-stack/floci.sh}"

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }

case "${1:-}" in
  --clean)
    log "Stopping services and removing volumes/images"
    docker compose down -v --rmi local
    ;;
  *)
    log "Stopping services"
    docker compose down
    ;;
esac

if [ "${1:-}" = "--all" ] && [ -f "$FLOCI" ]; then
  log "Stopping floci"
  bash "$FLOCI" stop
fi

log "Stopped."
