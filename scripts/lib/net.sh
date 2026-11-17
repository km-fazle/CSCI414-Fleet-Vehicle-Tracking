# Namespace, firewall, impairment, and measurement helpers.

assert_lab_iface() {
  case "$1" in
    c-ns|c-rt|s-ns|s-rt|d-ns|d-rt) ;;
    *)
      echo "refusing to touch unexpected interface: $1" >&2
      return 1
      ;;
  esac
}

assert_lab_ns() {
  case "$1" in
    ft-client|ft-router|ft-service|ft-data|ft-probe) ;;
    *)
      echo "refusing to touch unexpected namespace: $1" >&2
      return 1
      ;;
  esac
}

ns_alive() {
  ip netns list | awk '{print $1}' | grep -qx "$1"
}

clear_netem() {
  if ns_alive "$FT_CLIENT_NS"; then
    assert_lab_iface "$FT_IF_CLIENT"
    ip netns exec "$FT_CLIENT_NS" tc qdisc del dev "$FT_IF_CLIENT" root 2>/dev/null || true
  fi
  if ns_alive "$FT_ROUTER_NS"; then
    assert_lab_iface "$FT_IF_CLIENT_RT"
    ip netns exec "$FT_ROUTER_NS" tc qdisc del dev "$FT_IF_CLIENT_RT" root 2>/dev/null || true
  fi
  if ns_alive "$FT_ROUTER_NS" && ip netns exec "$FT_ROUTER_NS" tc qdisc show dev "$FT_IF_CLIENT_RT" | grep -q netem; then
    echo "netem is still installed on ${FT_IF_CLIENT_RT}" >&2
    return 1
  fi
  if ns_alive "$FT_CLIENT_NS" && ip netns exec "$FT_CLIENT_NS" tc qdisc show dev "$FT_IF_CLIENT" | grep -q netem; then
    echo "netem is still installed on ${FT_IF_CLIENT}" >&2
    return 1
  fi
}

assert_no_netem() {
  clear_netem
}

apply_netem() {
  local spec="$1"
  assert_lab_iface "$FT_IF_CLIENT"
  assert_lab_iface "$FT_IF_CLIENT_RT"
  # shellcheck disable=SC2086
  ip netns exec "$FT_CLIENT_NS" tc qdisc replace dev "$FT_IF_CLIENT" root netem $spec
  # shellcheck disable=SC2086
  ip netns exec "$FT_ROUTER_NS" tc qdisc replace dev "$FT_IF_CLIENT_RT" root netem $spec
  ip netns exec "$FT_CLIENT_NS" tc qdisc show dev "$FT_IF_CLIENT" | grep -q netem
  ip netns exec "$FT_ROUTER_NS" tc qdisc show dev "$FT_IF_CLIENT_RT" | grep -q netem
}

delete_project_namespaces() {
  local ns
  for ns in "$FT_CLIENT_NS" "$FT_ROUTER_NS" "$FT_SERVICE_NS" "$FT_DATA_NS" ft-probe; do
    assert_lab_ns "$ns"
    if ns_alive "$ns"; then
      ip netns del "$ns"
    fi
  done
  local ifc
  for ifc in "$FT_IF_CLIENT" "$FT_IF_CLIENT_RT" "$FT_IF_SERVICE" "$FT_IF_SERVICE_RT" "$FT_IF_DATA" "$FT_IF_DATA_RT" ft-probe; do
    if [[ "$ifc" != "ft-probe" ]]; then
      assert_lab_iface "$ifc"
    fi
    if ip link show "$ifc" >/dev/null 2>&1; then
      ip link del "$ifc"
    fi
  done
}

_add_veth() {
  local left="$1" left_ns="$2" right="$3" right_ns="$4"
  assert_lab_iface "$left"
  assert_lab_iface "$right"
  ip link add "$left" type veth peer name "$right"
  ip link set "$left" netns "$left_ns"
  ip link set "$right" netns "$right_ns"
}

_addr() {
  local ns="$1" ifc="$2" ipaddr="$3" prefix="$4" gateway="${5:-}"
  ip netns exec "$ns" ip addr add "${ipaddr}/${prefix}" dev "$ifc"
  ip netns exec "$ns" ip link set "$ifc" up
  ip netns exec "$ns" ip link set lo up
  if [[ -n "$gateway" ]]; then
    ip netns exec "$ns" ip route add default via "$gateway"
  fi
}

setup_network() {
  stop_api || true
  stop_mongo || true
  delete_project_namespaces
  ip netns add "$FT_CLIENT_NS"
  ip netns add "$FT_ROUTER_NS"
  ip netns add "$FT_SERVICE_NS"
  ip netns add "$FT_DATA_NS"
  _add_veth "$FT_IF_CLIENT" "$FT_CLIENT_NS" "$FT_IF_CLIENT_RT" "$FT_ROUTER_NS"
  _add_veth "$FT_IF_SERVICE" "$FT_SERVICE_NS" "$FT_IF_SERVICE_RT" "$FT_ROUTER_NS"
  _add_veth "$FT_IF_DATA" "$FT_DATA_NS" "$FT_IF_DATA_RT" "$FT_ROUTER_NS"
  _addr "$FT_CLIENT_NS" "$FT_IF_CLIENT" "$FT_CLIENT_IP" "$FT_CLIENT_PREFIX" "$FT_CLIENT_GW"
  _addr "$FT_SERVICE_NS" "$FT_IF_SERVICE" "$FT_SERVICE_IP" "$FT_SERVICE_PREFIX" "$FT_SERVICE_GW"
  _addr "$FT_DATA_NS" "$FT_IF_DATA" "$FT_DATA_IP" "$FT_DATA_PREFIX" "$FT_DATA_GW"
  _addr "$FT_ROUTER_NS" "$FT_IF_CLIENT_RT" "$FT_CLIENT_GW" "$FT_CLIENT_PREFIX"
  _addr "$FT_ROUTER_NS" "$FT_IF_SERVICE_RT" "$FT_SERVICE_GW" "$FT_SERVICE_PREFIX"
  _addr "$FT_ROUTER_NS" "$FT_IF_DATA_RT" "$FT_DATA_GW" "$FT_DATA_PREFIX"
  ip netns exec "$FT_ROUTER_NS" sysctl -w net.ipv4.ip_forward=1 >/dev/null
  ip netns exec "$FT_ROUTER_NS" sysctl -w net.ipv4.conf.all.rp_filter=0 >/dev/null
  ip netns exec "$FT_ROUTER_NS" sysctl -w net.ipv4.conf.default.rp_filter=0 >/dev/null
  local ifc
  for ifc in "$FT_IF_CLIENT_RT" "$FT_IF_SERVICE_RT" "$FT_IF_DATA_RT"; do
    ip netns exec "$FT_ROUTER_NS" sysctl -w "net.ipv4.conf.${ifc}.rp_filter=0" >/dev/null
  done
  ip netns exec "$FT_ROUTER_NS" nft delete table inet fleettrace 2>/dev/null || true
  ip netns exec "$FT_ROUTER_NS" nft -f "$ROOT/network/firewall.nft"
  if ip route | grep -E -q '10\.(10\.10|20\.20|30\.30)\.0/24'; then
    echo "container root namespace has a lab route; that would bypass the router" >&2
    ip route >&2
    return 1
  fi
  echo "network namespaces are up"
}

add_iperf_rule() {
  ip netns exec "$FT_ROUTER_NS" nft insert rule inet fleettrace forward \
    iifname "$FT_IF_CLIENT_RT" oifname "$FT_IF_SERVICE_RT" \
    ip saddr "$FT_CLIENT_NET" ip daddr "$FT_SERVICE_IP" tcp dport "$FT_IPERF_PORT" counter accept
}

del_iperf_rule() {
  local handle
  handle="$(ip netns exec "$FT_ROUTER_NS" nft -a list chain inet fleettrace forward \
    | awk -v port="$FT_IPERF_PORT" '$0 ~ ("dport " port) {for (i = 1; i <= NF; i++) if ($i == "handle") print $(i + 1)}' \
    | head -1)"
  if [[ -n "${handle}" ]]; then
    ip netns exec "$FT_ROUTER_NS" nft delete rule inet fleettrace forward handle "$handle"
  fi
  if ip netns exec "$FT_ROUTER_NS" nft list chain inet fleettrace forward | grep -q "dport ${FT_IPERF_PORT}"; then
    echo "temporary iperf rule is still installed" >&2
    return 1
  fi
}

measure_network() {
  local outdir="$1"
  mkdir -p "$outdir"
  ip netns exec "$FT_CLIENT_NS" ping -n -c 20 -i 0.2 -W 2 "$FT_SERVICE_IP" >"$outdir/ping.txt" 2>&1 || true
  ip netns exec "$FT_CLIENT_NS" tc qdisc show dev "$FT_IF_CLIENT" >"$outdir/tc-client.txt" 2>&1 || true
  ip netns exec "$FT_ROUTER_NS" tc qdisc show dev "$FT_IF_CLIENT_RT" >"$outdir/tc-router.txt" 2>&1 || true
  add_iperf_rule
  ip netns exec "$FT_SERVICE_NS" iperf3 -s -1 -B "$FT_SERVICE_IP" -p "$FT_IPERF_PORT" >"$outdir/iperf-server.txt" 2>&1 &
  local server_pid=$!
  sleep 0.5
  ip netns exec "$FT_CLIENT_NS" iperf3 -c "$FT_SERVICE_IP" -p "$FT_IPERF_PORT" -t 3 -J >"$outdir/iperf.json" 2>"$outdir/iperf.err" || true
  wait "$server_pid" || true
  del_iperf_rule
}
