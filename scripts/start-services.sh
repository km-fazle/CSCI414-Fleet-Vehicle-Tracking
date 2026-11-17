#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
require_linux_root "$@"
source "$ROOT/scripts/lib/services.sh"
mkdir -p "$ROOT/evidence/security"
if [[ ! -f "$ROOT/network/tls/certs/server.crt" ]]; then
  echo "server certificate is missing; run scripts/generate-certs.sh" >&2
  exit 1
fi
start_mongo
start_api
wait_ready
bash "$ROOT/scripts/start-dashboard.sh"
