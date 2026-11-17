# Experiment runner shared by baseline and impairment.

scenario_stamp() {
  if [[ -z "${FT_RUN_STAMP:-}" ]]; then
    if [[ -f "$ROOT/evidence/results/latest-run.txt" ]]; then
      FT_RUN_STAMP="$(tr -d '[:space:]' < "$ROOT/evidence/results/latest-run.txt")"
    else
      FT_RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
    fi
    export FT_RUN_STAMP
  fi
}

run_scenario() {
  local scenario="$1"
  local impairment="${2:-}"
  # shellcheck disable=SC1091
  source "$ROOT/network/experiment.env"
  scenario_stamp
  local out="$ROOT/evidence/results/${scenario}/${FT_RUN_STAMP}"
  mkdir -p "$out"
  printf '%s\n' "$impairment" >"$out/impairment.txt"
  if [[ -n "$impairment" ]]; then
    apply_netem "$impairment"
  else
    assert_no_netem
  fi
  measure_network "$out"
  local run_id="${scenario}-seed${FT_EXP_SEED}-${FT_RUN_STAMP}"
  # The workload must originate in the client namespace. The container root
  # has no route to 10.20.20.10, and giving it one would bypass the router.
  ip netns exec "$FT_CLIENT_NS" /opt/fleettrace-venv/bin/python3 "$ROOT/simulator/benchmark.py" run \
    --base-url "$(api_base)" \
    --ca "$(ca_file)" \
    --scenario "$scenario" \
    --run-id "$run_id" \
    --output-dir "$out" \
    --vehicles "$FT_EXP_VEHICLES" \
    --events-per-vehicle "$FT_EXP_EVENTS" \
    --interval-ms "$FT_EXP_INTERVAL_MS" \
    --seed "$FT_EXP_SEED" \
    --timeout "$FT_EXP_TIMEOUT" \
    --max-retries "$FT_EXP_RETRIES" \
    --query-every "$FT_EXP_QUERY_EVERY"
  python3 "$ROOT/simulator/benchmark.py" attach-network \
    --summary "$out/summary.json" \
    --ping "$out/ping.txt" \
    --iperf "$out/iperf.json" \
    --tc "$out/tc-client.txt" \
    --tc "$out/tc-router.txt" \
    --impairment "$impairment"
  echo "scenario ${scenario} written to ${out}"
}
