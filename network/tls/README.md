# TLS material

`scripts/generate-certs.sh` creates a lab CA and a server certificate. The server certificate has a SAN for `10.20.20.10` and `fleettrace-api.lab`.

Private keys stay in `network/tls/private/` and are gitignored. Run the script inside the lab container; do not commit the keys. Clients must pass `network/tls/certs/ca.crt` to curl or httpx. A successful `curl -k` is not evidence.
