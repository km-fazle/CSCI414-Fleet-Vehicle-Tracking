#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
require_linux_root "$@"
source "$ROOT/scripts/lib/services.sh"
source "$ROOT/scripts/lib/net.sh"
setup_network
mkdir -p "$ROOT/evidence/topology"
{
  echo "# $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  ip netns list
  echo
  echo "# client"
  ip netns exec "$FT_CLIENT_NS" ip addr
  echo
  echo "# router"
  ip netns exec "$FT_ROUTER_NS" ip addr
  echo
  echo "# service"
  ip netns exec "$FT_SERVICE_NS" ip addr
  echo
  echo "# data"
  ip netns exec "$FT_DATA_NS" ip addr
} | tee "$ROOT/evidence/topology/ip-addr.txt"
{
  for ns in "$FT_CLIENT_NS" "$FT_ROUTER_NS" "$FT_SERVICE_NS" "$FT_DATA_NS"; do
    echo "# $ns"
    ip netns exec "$ns" ip route
    echo
  done
} | tee "$ROOT/evidence/topology/ip-route.txt"
ip netns exec "$FT_ROUTER_NS" sysctl net.ipv4.ip_forward | tee "$ROOT/evidence/topology/ip-forward.txt"
