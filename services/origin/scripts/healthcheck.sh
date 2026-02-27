#!/usr/bin/env sh
set -eu

if curl -sf http://127.0.0.1:8080/health >/dev/null; then
  exit 0
fi

exit 1
