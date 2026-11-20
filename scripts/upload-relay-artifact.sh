#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  printf 'usage: %s <relay-url> <bundle.tar.gz> <bearer-token>\n' "$0" >&2
  exit 2
fi

relay_url="${1%/}"
bundle="$2"
token="$3"

[[ -f "$bundle" ]] || { echo "bundle not found: $bundle" >&2; exit 1; }
curl --fail-with-body --http1.1 \
  -H "Authorization: Bearer ${token}" \
  -H "Content-Type: application/gzip" \
  --data-binary "@${bundle}" \
  "${relay_url}/v1/artifacts"
printf '\n'