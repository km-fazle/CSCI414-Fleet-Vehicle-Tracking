#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
require_linux_root "$@"
source "$ROOT/scripts/lib/services.sh"
source "$ROOT/scripts/lib/scenario.sh"
scenario_stamp
out="$ROOT/evidence/logs/api-errors"
mkdir -p "$out"
body="$out/bad.json"
cat >"$body" <<EOF
{"vehicle_id":"lab-errors","label":"Errors"}
EOF
ip netns exec "$FT_CLIENT_NS" python3 "$ROOT/simulator/probe.py" \
  --base-url "$(api_base)" --ca "$(ca_file)" --timeout 8 \
  --method POST --path /api/v1/vehicles --body-file "$body" \
  --operation create_vehicle --vehicle-id lab-errors --out "$out/create.json"
python3 - <<PY
import json, sys
doc = json.load(open("$out/create.json"))
if doc["http_status"] not in (201, 409):
    sys.exit(f"create failed: {doc}")
PY
ip netns exec "$FT_CLIENT_NS" python3 "$ROOT/simulator/probe.py" \
  --base-url "$(api_base)" --ca "$(ca_file)" --timeout 8 \
  --method POST --path /api/v1/vehicles --body-file "$body" \
  --operation create_vehicle --vehicle-id lab-errors --out "$out/duplicate.json"
python3 - <<PY
import json, sys
doc = json.load(open("$out/duplicate.json"))
if doc["http_status"] != 409:
    sys.exit(f"expected 409, got {doc}")
PY
cat >"$out/bad-lat.json" <<EOF
{"event_id":"lab-errors-bad","vehicle_id":"lab-errors","event_time":"2026-11-13T16:00:00Z","lat":91,"lon":-73.9,"sequence":1}
EOF
ip netns exec "$FT_CLIENT_NS" python3 "$ROOT/simulator/probe.py" \
  --base-url "$(api_base)" --ca "$(ca_file)" --timeout 8 \
  --method POST --path /api/v1/telemetry --body-file "$out/bad-lat.json" \
  --operation post_telemetry --out "$out/bad-lat-response.json"
python3 - <<PY
import json, sys
doc = json.load(open("$out/bad-lat-response.json"))
if doc["http_status"] != 422:
    sys.exit(f"expected 422, got {doc}")
PY
cat >"$out/unknown.json" <<EOF
{"event_id":"missing-1","vehicle_id":"missing-vehicle","event_time":"2026-11-13T16:00:00Z","lat":40.7,"lon":-73.9,"sequence":1}
EOF
ip netns exec "$FT_CLIENT_NS" python3 "$ROOT/simulator/probe.py" \
  --base-url "$(api_base)" --ca "$(ca_file)" --timeout 8 \
  --method POST --path /api/v1/telemetry --body-file "$out/unknown.json" \
  --operation post_telemetry --out "$out/unknown-response.json"
python3 - <<PY
import json, sys
doc = json.load(open("$out/unknown-response.json"))
if doc["http_status"] != 404:
    sys.exit(f"expected 404, got {doc}")
PY
stop_mongo
ip netns exec "$FT_CLIENT_NS" python3 "$ROOT/simulator/probe.py" \
  --base-url "$(api_base)" --ca "$(ca_file)" --timeout 8 \
  --method GET --path /health/live --operation live --out "$out/live-during-db-outage.json"
ip netns exec "$FT_CLIENT_NS" python3 "$ROOT/simulator/probe.py" \
  --base-url "$(api_base)" --ca "$(ca_file)" --timeout 8 \
  --method GET --path /health/ready --operation ready --out "$out/ready-during-db-outage.json"
python3 - <<PY
import json, sys
live = json.load(open("$out/live-during-db-outage.json"))
ready = json.load(open("$out/ready-during-db-outage.json"))
if live["http_status"] != 200 or ready["http_status"] != 503:
    sys.exit(f"expected live 200 and ready 503, got {live['http_status']} {ready['http_status']}")
PY
start_mongo
wait_ready
echo "API error paths passed"
