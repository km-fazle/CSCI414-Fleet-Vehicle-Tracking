#!/usr/bin/env bash
# Capture a short window around one HTTPS post. Refuses to listen on other interfaces.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
require_linux_root "$@"
source "$ROOT/scripts/lib/scenario.sh"
scenario_stamp
out="$ROOT/evidence/pcap"
mkdir -p "$out"
assert_capture_iface() {
  case "$1" in
    c-rt|s-rt|d-rt) ;;
    *) echo "refusing capture on $1" >&2; exit 1 ;;
  esac
}
assert_capture_iface "$FT_IF_CLIENT_RT"
assert_capture_iface "$FT_IF_SERVICE_RT"
assert_capture_iface "$FT_IF_DATA_RT"
rm -f "$out/client-router.pcap" "$out/router-service.pcap" "$out/router-data.pcap"
ip netns exec "$FT_ROUTER_NS" timeout 20 tcpdump -U -n -i "$FT_IF_CLIENT_RT" -c 60 -w "$out/client-router.pcap" "tcp port ${FT_API_PORT}" &
pid_c=$!
ip netns exec "$FT_ROUTER_NS" timeout 20 tcpdump -U -n -i "$FT_IF_SERVICE_RT" -c 60 -w "$out/router-service.pcap" "tcp port ${FT_API_PORT}" &
pid_s=$!
ip netns exec "$FT_ROUTER_NS" timeout 20 tcpdump -U -n -i "$FT_IF_DATA_RT" -c 40 -w "$out/router-data.pcap" "tcp port ${FT_MONGO_PORT}" &
pid_d=$!
sleep 1
event_id="cap-${FT_RUN_STAMP}-000001"
python3 - <<PY >"$out/event.json"
from datetime import datetime, timezone
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
print("""{
  "event_id": "${event_id}",
  "vehicle_id": "demo-001",
  "event_time": "%s",
  "lat": 40.7543219,
  "lon": -73.9808123,
  "sequence": 900001,
  "simulation_run_id": "capture-${FT_RUN_STAMP}",
  "source_type": "synthetic",
  "generation_method": "deterministic_linear_track",
  "simulation_seed": 42
}""" % now)
PY
ip netns exec "$FT_CLIENT_NS" python3 "$ROOT/simulator/probe.py" \
  --base-url "$(api_base)" --ca "$(ca_file)" --timeout 8 \
  --method POST --path /api/v1/telemetry --body-file "$out/event.json" \
  --operation post_telemetry --event-id "$event_id" --vehicle-id demo-001 \
  --out "$out/post.json"
python3 - <<PY
import json, sys
doc = json.load(open("$out/post.json"))
if doc["http_status"] not in (200, 201):
    sys.exit(f"capture post failed: {doc}")
PY
sleep 1
kill "$pid_c" "$pid_s" "$pid_d" 2>/dev/null || true
wait "$pid_c" || true
wait "$pid_s" || true
wait "$pid_d" || true
tcpdump -nn -r "$out/client-router.pcap" >"$out/client-router.txt" 2>&1 || true
tcpdump -nn -r "$out/router-service.pcap" >"$out/router-service.txt" 2>&1 || true
tcpdump -nn -r "$out/router-data.pcap" >"$out/router-data.txt" 2>&1 || true
python3 - <<PY
from pathlib import Path
secret = b"40.7543219"
for name in ("client-router.pcap", "router-service.pcap"):
    blob = Path("$out") .joinpath(name).read_bytes()
    if len(blob) < 24:
        raise SystemExit(f"{name} is empty")
    if secret in blob:
        raise SystemExit(f"plaintext latitude found in {name}")
    print(f"{name}: {len(blob)} bytes, plaintext latitude absent")
data = Path("$out/router-data.pcap").read_bytes()
print(f"router-data.pcap: {len(data)} bytes; coordinate visible on data path: {secret in data}")
PY
echo "packet capture checks passed"
