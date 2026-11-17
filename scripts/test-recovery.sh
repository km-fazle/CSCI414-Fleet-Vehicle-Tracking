#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
require_linux_root "$@"
source "$ROOT/scripts/lib/services.sh"
source "$ROOT/scripts/lib/scenario.sh"
# shellcheck disable=SC1091
source "$ROOT/network/experiment.env"
scenario_stamp
out="$ROOT/evidence/results/failure/${FT_RUN_STAMP}"
mkdir -p "$out"
stamp_now() {
  python3 - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z")
PY
}
cat >"$out/vehicle.json" <<EOF
{"vehicle_id":"lab-recovery","label":"Recovery"}
EOF
ip netns exec "$FT_CLIENT_NS" python3 "$ROOT/simulator/probe.py" \
  --base-url "$(api_base)" --ca "$(ca_file)" --timeout 8 \
  --method POST --path /api/v1/vehicles --body-file "$out/vehicle.json" \
  --operation create_vehicle --vehicle-id lab-recovery --out "$out/create.json"
lost_id="recovery-${FT_RUN_STAMP}-lost"
new_id="recovery-${FT_RUN_STAMP}-new"
python3 - <<PY
from datetime import datetime, timezone
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
open("$out/lost-body.json", "w", encoding="utf-8").write("""{
  "event_id": "${lost_id}",
  "vehicle_id": "lab-recovery",
  "event_time": "%s",
  "lat": 40.76,
  "lon": -73.97,
  "sequence": 1,
  "simulation_run_id": "failure-${FT_RUN_STAMP}",
  "source_type": "synthetic",
  "generation_method": "deterministic_linear_track",
  "simulation_seed": 42
}""" % now)
PY
stamp_now >"$out/outage-started.txt"
stop_api
ip netns exec "$FT_CLIENT_NS" python3 "$ROOT/simulator/probe.py" \
  --base-url "$(api_base)" --ca "$(ca_file)" --timeout 3 \
  --method GET --path /health/ready --operation ready --out "$out/detected.json"
ip netns exec "$FT_CLIENT_NS" python3 "$ROOT/simulator/probe.py" \
  --base-url "$(api_base)" --ca "$(ca_file)" --timeout 3 \
  --method POST --path /api/v1/telemetry --body-file "$out/lost-body.json" \
  --operation post_telemetry --event-id "$lost_id" --vehicle-id lab-recovery \
  --out "$out/failed-post.json"
python3 - <<PY
import json, time
from datetime import datetime, timezone
started = datetime.fromisoformat(open("$out/outage-started.txt").read().strip().replace("Z", "+00:00"))
remain = $FT_RECOVERY_HOLD_SECONDS - (datetime.now(timezone.utc) - started).total_seconds()
if remain > 0:
    time.sleep(remain)
PY
stamp_now >"$out/restart-invoked.txt"
start_api
wait_ready
ip netns exec "$FT_CLIENT_NS" python3 "$ROOT/simulator/probe.py" \
  --base-url "$(api_base)" --ca "$(ca_file)" --timeout 8 \
  --method GET --path /health/ready --operation ready --out "$out/ready.json"
python3 - <<PY
from datetime import datetime, timezone
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
open("$out/new-body.json", "w", encoding="utf-8").write("""{
  "event_id": "${new_id}",
  "vehicle_id": "lab-recovery",
  "event_time": "%s",
  "lat": 40.761,
  "lon": -73.971,
  "sequence": 2,
  "simulation_run_id": "failure-${FT_RUN_STAMP}",
  "source_type": "synthetic",
  "generation_method": "deterministic_linear_track",
  "simulation_seed": 42
}""" % now)
PY
ip netns exec "$FT_CLIENT_NS" python3 "$ROOT/simulator/probe.py" \
  --base-url "$(api_base)" --ca "$(ca_file)" --timeout 8 \
  --method POST --path /api/v1/telemetry --body-file "$out/new-body.json" \
  --operation post_telemetry --event-id "$new_id" --vehicle-id lab-recovery \
  --out "$out/success-post.json"
ip netns exec "$FT_CLIENT_NS" python3 "$ROOT/simulator/probe.py" \
  --base-url "$(api_base)" --ca "$(ca_file)" --timeout 8 \
  --method GET --path /api/v1/vehicles/lab-recovery/latest \
  --operation get_latest --vehicle-id lab-recovery --out "$out/success-get.json"
ip netns exec "$FT_CLIENT_NS" python3 "$ROOT/simulator/probe.py" \
  --base-url "$(api_base)" --ca "$(ca_file)" --timeout 8 \
  --method POST --path /api/v1/telemetry --body-file "$out/lost-body.json" \
  --operation post_telemetry --event-id "$lost_id" --vehicle-id lab-recovery \
  --out "$out/retry-post.json"
python3 "$ROOT/simulator/recovery_report.py" \
  --out "$out/timeline.json" \
  --detected "$out/detected.json" \
  --failed-post "$out/failed-post.json" \
  --ready "$out/ready.json" \
  --success-post "$out/success-post.json" \
  --success-get "$out/success-get.json" \
  --retry-post "$out/retry-post.json" \
  --restart-invoked "$out/restart-invoked.txt" \
  --hold-seconds "$FT_RECOVERY_HOLD_SECONDS"
echo "recovery evidence written to $out"
