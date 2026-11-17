#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
require_linux_root "$@"
source "$ROOT/scripts/lib/net.sh"
source "$ROOT/scripts/lib/scenario.sh"
# shellcheck disable=SC1091
source "$ROOT/network/experiment.env"
cleanup() {
  clear_netem || true
}
trap cleanup EXIT
run_scenario delay "$FT_NETEM_DELAY"
clear_netem
trap - EXIT
echo "impairment removed"
