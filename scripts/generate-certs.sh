#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
require_linux_root "$@"

umask 077
mkdir -p "$ROOT/network/tls/private" "$ROOT/network/tls/certs" "$ROOT/evidence/security"
cat >"$ROOT/network/tls/private/ca.cnf" <<'EOF'
[req]
distinguished_name = dn
x509_extensions = v3_ca
prompt = no
[dn]
CN = FleetTrace Lab CA
[v3_ca]
basicConstraints = critical,CA:TRUE
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
EOF
cat >"$ROOT/network/tls/private/server.cnf" <<EOF
[req]
distinguished_name = dn
req_extensions = v3_req
prompt = no
[dn]
CN = fleettrace-api.lab
[v3_req]
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt
[alt]
IP.1 = ${FT_SERVICE_IP}
DNS.1 = fleettrace-api.lab
EOF
openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes \
  -keyout "$ROOT/network/tls/private/ca.key" \
  -out "$ROOT/network/tls/certs/ca.crt" \
  -config "$ROOT/network/tls/private/ca.cnf" >/dev/null 2>&1
openssl req -newkey rsa:2048 -sha256 -nodes \
  -keyout "$ROOT/network/tls/private/server.key" \
  -out "$ROOT/network/tls/private/server.csr" \
  -config "$ROOT/network/tls/private/server.cnf" >/dev/null 2>&1
openssl x509 -req \
  -in "$ROOT/network/tls/private/server.csr" \
  -CA "$ROOT/network/tls/certs/ca.crt" \
  -CAkey "$ROOT/network/tls/private/ca.key" \
  -CAcreateserial \
  -CAserial "$ROOT/network/tls/private/ca.srl" \
  -out "$ROOT/network/tls/certs/server.crt" \
  -days 365 -sha256 \
  -extensions v3_req \
  -extfile "$ROOT/network/tls/private/server.cnf" >/dev/null 2>&1
chmod 600 "$ROOT/network/tls/private/ca.key" "$ROOT/network/tls/private/server.key"
openssl verify -CAfile "$ROOT/network/tls/certs/ca.crt" "$ROOT/network/tls/certs/server.crt"
openssl x509 -in "$ROOT/network/tls/certs/server.crt" -noout -ext subjectAltName \
  | tee "$ROOT/evidence/security/server-san.txt"
grep -q "$FT_SERVICE_IP" "$ROOT/evidence/security/server-san.txt"
echo "certificate SAN includes ${FT_SERVICE_IP}"
