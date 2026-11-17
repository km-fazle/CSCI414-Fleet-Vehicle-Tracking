#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
require_linux_root "$@"
source "$ROOT/scripts/lib/services.sh"
source "$ROOT/scripts/lib/net.sh"
clear_netem || true
stop_api || true
stop_mongo || true
delete_project_namespaces
echo "removed FleetTrace namespaces, processes, and netem rules"
