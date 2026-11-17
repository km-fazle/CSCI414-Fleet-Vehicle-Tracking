#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
require_linux_root "$@"
cd "$ROOT"
mkdir -p "$ROOT/evidence/logs" "$ROOT/evidence/results" "$ROOT/evidence/pcap" "$ROOT/evidence/security" "$ROOT/evidence/topology"
export FT_RUN_STAMP
FT_RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
printf '%s\n' "$FT_RUN_STAMP" >"$ROOT/evidence/results/latest-run.txt"
exec > >(tee -a "$ROOT/evidence/logs/run-lab.log") 2>&1
echo "FleetTrace lab run ${FT_RUN_STAMP}"
bash "$ROOT/scripts/doctor.sh"
pytest "$ROOT/tests/unit" -q
bash "$ROOT/scripts/setup-network.sh"
bash "$ROOT/scripts/generate-certs.sh"
bash "$ROOT/scripts/start-services.sh"
ip netns exec "$FT_SERVICE_NS" env FLEETTRACE_INTEGRATION=1 \
  MONGODB_URI="mongodb://${FT_DATA_IP}:${FT_MONGO_PORT}" \
  pytest "$ROOT/tests/integration" -q
bash "$ROOT/scripts/seed-data.sh"
bash "$ROOT/scripts/verify-network.sh"
bash "$ROOT/scripts/test-tls.sh"
bash "$ROOT/scripts/demo-crud.sh"
bash "$ROOT/scripts/test-api-errors.sh"
bash "$ROOT/scripts/capture-evidence.sh"
bash "$ROOT/scripts/run-baseline.sh"
bash "$ROOT/scripts/run-impairment.sh"
python3 "$ROOT/simulator/benchmark.py" compare-fingerprints \
  --left "$ROOT/evidence/results/baseline/${FT_RUN_STAMP}/summary.json" \
  --right "$ROOT/evidence/results/delay/${FT_RUN_STAMP}/summary.json" \
  | tee "$ROOT/evidence/results/workload-match.json"
bash "$ROOT/scripts/test-recovery.sh"
cp /var/lib/fleettrace/api.log "$ROOT/evidence/logs/api.log" || true
cp /var/lib/fleettrace/mongod.log "$ROOT/evidence/logs/mongod.log" || true
find "$ROOT/evidence" -type f | sort >"$ROOT/evidence/manifest.txt"
echo "lab run ${FT_RUN_STAMP} finished"
