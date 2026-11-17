#!/usr/bin/env bash
# Check that this container can build namespaces, nftables, and netem.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
require_linux_root "$@"

cleanup() {
  tc qdisc del dev ft-probe root 2>/dev/null || true
  ip link del ft-probe 2>/dev/null || true
  ip netns del ft-probe 2>/dev/null || true
}
trap cleanup EXIT

mkdir -p "$ROOT/evidence/topology" "$ROOT/evidence/logs"
{
  echo "date_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  uname -a
  cat /etc/os-release
  python3 --version
  mongod --version | head -n 2
  nft --version
  ip -V
  tc -V
  tcpdump --version 2>&1 | head -n 1
  iperf3 --version | head -n 1
  traceroute --version 2>&1 | head -n 1
  openssl version
} | tee "$ROOT/evidence/topology/versions.txt"

missing=0
for cmd in ip sysctl nft tc tcpdump ping curl python3 openssl mongod mongosh iperf3 traceroute uvicorn; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "missing command: $cmd" >&2
    missing=1
  fi
done
if [[ "$missing" -ne 0 ]]; then
  exit 1
fi
python3 -c "import fastapi, pymongo, httpx"

modprobe nf_conntrack 2>/dev/null || true
modprobe sch_netem 2>/dev/null || true

ip netns add ft-probe
ip netns exec ft-probe nft add table inet ft_probe
ip netns exec ft-probe nft delete table inet ft_probe
ip link add ft-probe type dummy
ip link set ft-probe up
tc qdisc replace dev ft-probe root netem delay 1ms
tc qdisc show dev ft-probe | grep -q netem
echo "doctor: namespaces, nftables, and netem are available"
