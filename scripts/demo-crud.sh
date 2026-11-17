#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
require_linux_root "$@"
source "$ROOT/scripts/lib/services.sh"
source "$ROOT/scripts/lib/scenario.sh"
scenario_stamp
out="$ROOT/evidence/logs/crud"
fresh="crud-${FT_RUN_STAMP}-fresh"
stale="crud-${FT_RUN_STAMP}-stale"
ip netns exec "$FT_CLIENT_NS" python3 "$ROOT/simulator/demo_crud.py" run \
  --base-url "$(api_base)" \
  --ca "$(ca_file)" \
  --out "$out/before" \
  --run-id "crud-${FT_RUN_STAMP}" \
  --fresh-event-id "$fresh" \
  --stale-event-id "$stale"
stop_api
start_api
wait_ready
ip netns exec "$FT_CLIENT_NS" python3 "$ROOT/simulator/demo_crud.py" verify \
  --base-url "$(api_base)" \
  --ca "$(ca_file)" \
  --out "$out/after-restart" \
  --run-id "crud-${FT_RUN_STAMP}" \
  --fresh-event-id "$fresh" \
  --stale-event-id "$stale"
ip netns exec "$FT_SERVICE_NS" mongosh --quiet --host "$FT_DATA_IP" --port "$FT_MONGO_PORT" \
  --eval "db.getSiblingDB('fleettrace').location_events.find({event_id: '${fresh}'}, {_id: 0, event_id: 1, location: 1, event_time: 1, received_at: 1}).toArray()" \
  | tee "$out/mongo-fresh.txt"
grep -q "$fresh" "$out/mongo-fresh.txt"
echo "create, update, persist, and MongoDB readback passed"
