#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
require_linux_root "$@"
mkdir -p "$ROOT/evidence/topology" "$ROOT/evidence/security"

{
  echo "# $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  ip netns exec "$FT_CLIENT_NS" traceroute -T -n -p "$FT_API_PORT" -w 2 -q 1 -m 4 "$FT_SERVICE_IP"
} | tee "$ROOT/evidence/topology/traceroute.txt"
grep -q "$FT_CLIENT_GW" "$ROOT/evidence/topology/traceroute.txt"
grep -q "$FT_SERVICE_IP" "$ROOT/evidence/topology/traceroute.txt"

ip netns exec "$FT_CLIENT_NS" ping -n -c 2 -W 2 "$FT_SERVICE_IP" \
  | tee "$ROOT/evidence/topology/ping-client-service.txt"
grep -q " 0% packet loss" "$ROOT/evidence/topology/ping-client-service.txt"

set +e
ip netns exec "$FT_CLIENT_NS" ping -n -c 2 -W 2 "$FT_DATA_IP" \
  >"$ROOT/evidence/security/ping-client-data.txt" 2>&1
ping_rc=$?
set -e
if [[ "$ping_rc" -eq 0 ]]; then
  echo "client was able to ping the data zone" >&2
  exit 1
fi
echo "client to data ping blocked (rc=${ping_rc})"

set +e
ip netns exec "$FT_SERVICE_NS" python3 "$ROOT/simulator/tcpcheck.py" \
  "$FT_DATA_IP" "$FT_MONGO_PORT" 3 >"$ROOT/evidence/security/allow-mongo.txt" 2>&1
allow_rc=$?
set -e
if [[ "$allow_rc" -ne 0 ]]; then
  echo "service zone could not reach MongoDB" >&2
  cat "$ROOT/evidence/security/allow-mongo.txt" >&2
  exit 1
fi

set +e
ip netns exec "$FT_CLIENT_NS" python3 "$ROOT/simulator/tcpcheck.py" \
  "$FT_DATA_IP" "$FT_MONGO_PORT" "$FT_DENY_TIMEOUT" >"$ROOT/evidence/security/deny-mongo.txt" 2>&1
deny_rc=$?
set -e
if [[ "$deny_rc" -ne 124 ]]; then
  echo "expected a timeout (124) for client to MongoDB, got ${deny_rc}" >&2
  cat "$ROOT/evidence/security/deny-mongo.txt" >&2
  exit 1
fi

ip netns exec "$FT_CLIENT_NS" curl -fsS --max-time 10 --cacert "$(ca_file)" \
  "$(api_base)/health/live" | tee "$ROOT/evidence/security/allow-api.txt"
echo
ip netns exec "$FT_ROUTER_NS" nft list ruleset | tee "$ROOT/evidence/security/nft-ruleset.txt"
python3 - "$ROOT/evidence/security/nft-ruleset.txt" <<'PY'
import re
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r"10\.30\.30\.0/24 counter packets (\d+)", text)
if not match or int(match.group(1)) < 1:
    sys.exit("client-to-data drop counter did not increase")
print(f"client-to-data drop counter packets={match.group(1)}")
PY
echo "network verification passed"
