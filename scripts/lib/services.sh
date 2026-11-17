# MongoDB and API process helpers. Source after common.sh.

stop_pidfile() {
  local pidfile="$1"
  local pid
  if [[ ! -f "$pidfile" ]]; then
    return 0
  fi
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  if [[ -n "${pid}" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    local _
    for _ in $(seq 1 20); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.25
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  fi
  rm -f "$pidfile"
}

stop_api() {
  stop_pidfile /var/lib/fleettrace/api.pid
}

stop_mongo() {
  stop_pidfile /var/lib/fleettrace/mongod.pid
  sleep 0.5
  rm -f /var/lib/fleettrace/mongo/mongod.lock
}

start_mongo() {
  local pidfile=/var/lib/fleettrace/mongod.pid
  mkdir -p /var/lib/fleettrace/mongo
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "mongod already running ($(cat "$pidfile"))"
    return 0
  fi
  rm -f "$pidfile" /var/lib/fleettrace/mongo/mongod.lock
  ip netns exec "$FT_DATA_NS" mongod --config "$ROOT/network/mongod.conf"
  local _
  for _ in $(seq 1 20); do
    if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
      echo "mongod pid $(cat "$pidfile")"
      return 0
    fi
    sleep 0.25
  done
  echo "mongod did not stay up" >&2
  tail -n 40 /var/lib/fleettrace/mongod.log >&2 || true
  return 1
}

start_api() {
  local pidfile=/var/lib/fleettrace/api.pid
  local logfile=/var/lib/fleettrace/api.log
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "API already running ($(cat "$pidfile"))"
    return 0
  fi
  rm -f "$pidfile"
  touch "$logfile"
  ip netns exec "$FT_SERVICE_NS" \
    env MONGODB_URI="mongodb://${FT_DATA_IP}:${FT_MONGO_PORT}" \
        MONGODB_DB="${MONGODB_DB:-fleettrace}" \
        MONGO_TIMEOUT_MS="${MONGO_TIMEOUT_MS:-2000}" \
        FRESHNESS_THRESHOLD_SECONDS="${FRESHNESS_THRESHOLD_SECONDS:-$FT_FRESHNESS_SECONDS}" \
        LOG_LEVEL="${LOG_LEVEL:-INFO}" \
    python3 "$ROOT/simulator/daemon.py" \
      "$pidfile" \
      "$logfile" \
      /opt/fleettrace-venv/bin/uvicorn \
      app.main:create_app \
      --factory \
      --app-dir "$ROOT/api" \
      --host "$FT_SERVICE_IP" \
      --port "$FT_API_PORT" \
      --ssl-certfile "$ROOT/network/tls/certs/server.crt" \
      --ssl-keyfile "$ROOT/network/tls/private/server.key" \
      --no-access-log
  local _
  for _ in $(seq 1 20); do
    if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
      echo "API pid $(cat "$pidfile")"
      return 0
    fi
    sleep 0.25
  done
  echo "API process did not stay up" >&2
  tail -n 60 "$logfile" >&2 || true
  return 1
}

wait_ready() {
  local _
  for _ in $(seq 1 40); do
    if ip netns exec "$FT_CLIENT_NS" curl -fsS --max-time 3 --cacert "$(ca_file)" \
      "$(api_base)/health/ready" >/dev/null; then
      echo "API ready"
      return 0
    fi
    sleep 1
  done
  echo "API did not become ready" >&2
  tail -n 80 /var/lib/fleettrace/api.log >&2 || true
  tail -n 40 /var/lib/fleettrace/mongod.log >&2 || true
  return 1
}
