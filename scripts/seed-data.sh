#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
require_linux_root "$@"
python3 "$ROOT/simulator/generate.py" \
  --vehicles 5 \
  --events-per-vehicle 5 \
  --seed 42 \
  --interval-ms 1000 \
  --start 2026-11-13T16:00:00Z \
  --run-id fixture-seed42 \
  --output "$ROOT/data/fixtures/fleet-seed42.json"
ip netns exec "$FT_CLIENT_NS" python3 "$ROOT/simulator/replay.py" \
  --fixture "$ROOT/data/fixtures/fleet-seed42.json" \
  --base-url "$(api_base)" \
  --ca "$(ca_file)" \
  --register-only
