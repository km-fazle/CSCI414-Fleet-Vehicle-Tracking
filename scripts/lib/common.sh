# Shared paths and the Linux-only guard. Source this; do not execute it.
_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$_LIB_DIR/../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/network/addresses.env"

require_linux_root() {
  if [[ "$(uname -s)" != "Linux" ]]; then
    cat >&2 <<EOF
This step runs inside the FleetTrace Linux container.
From the repository on macOS:

  docker compose up -d --build
  docker compose exec -T lab bash scripts/run-lab.sh
EOF
    exit 2
  fi
  if [[ "${EUID}" -ne 0 ]]; then
    exec sudo -E bash "$(readlink -f "$0")" "$@"
  fi
}

section() {
  printf '\n===== %s =====\n' "$1"
}

api_base() {
  printf 'https://%s:%s' "$FT_SERVICE_IP" "$FT_API_PORT"
}

ca_file() {
  printf '%s/network/tls/certs/ca.crt' "$ROOT"
}
