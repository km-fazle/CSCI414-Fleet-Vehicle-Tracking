#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
require_linux_root "$@"

pidfile=/var/lib/fleettrace/dashboard.pid
logfile=/var/lib/fleettrace/dashboard.log
mkdir -p /var/lib/fleettrace

if [[ -f "$pidfile" ]]; then
  pid="$(cat "$pidfile")"
  state="$(ps -o stat= -p "$pid" 2>/dev/null | awk '{print $1}' || true)"
  if [[ -n "$state" && "$state" != Z && "$state" != Z+ ]]; then
    echo "dashboard already running ($pid)"
    exit 0
  fi
fi
rm -f "$pidfile"
touch "$logfile"

python3 "$ROOT/simulator/daemon.py" \
  "$pidfile" \
  "$logfile" \
  python3 "$ROOT/dashboard/server.py" --host 0.0.0.0 --port 8787

for _ in $(seq 1 20); do
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "dashboard pid $(cat "$pidfile")"
    exit 0
  fi
  sleep 0.25
done

echo "dashboard did not stay up" >&2
tail -n 40 "$logfile" >&2 || true
exit 1
