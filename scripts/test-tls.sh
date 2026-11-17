#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
require_linux_root "$@"
mkdir -p "$ROOT/evidence/security"
ip netns exec "$FT_CLIENT_NS" curl -fsS --max-time 10 --cacert "$(ca_file)" \
  "$(api_base)/health/live" | tee "$ROOT/evidence/security/tls-curl.txt"
echo
set +e
ip netns exec "$FT_CLIENT_NS" curl -fsS --max-time 10 "$(api_base)/health/live" \
  >"$ROOT/evidence/security/tls-untrusted.txt" 2>&1
untrusted_rc=$?
set -e
if [[ "$untrusted_rc" -eq 0 ]]; then
  echo "curl trusted the server without the lab CA; that is not a valid TLS proof" >&2
  exit 1
fi
echo "curl without the lab CA failed as expected (rc=${untrusted_rc})"
ip netns exec "$FT_CLIENT_NS" openssl s_client \
  -connect "${FT_SERVICE_IP}:${FT_API_PORT}" \
  -servername fleettrace-api.lab \
  -CAfile "$(ca_file)" \
  -verify_return_error </dev/null >"$ROOT/evidence/security/tls-openssl.txt" 2>&1
grep -q "Verify return code: 0 (ok)" "$ROOT/evidence/security/tls-openssl.txt"
echo "TLS certificate verification passed"
