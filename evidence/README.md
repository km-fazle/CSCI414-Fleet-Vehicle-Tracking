# Evidence index

Lab run `20261113T170217Z` finished with exit 0 on November 13, 2026. `evidence/results/latest-run.txt` contains that stamp. An earlier attempt, `20261113T170058Z`, stopped during the baseline because the workload ran outside `ft-client`. Its partial result directory was removed. The log of both attempts is `evidence/logs/run-lab.log`.

| Path | Test |
|---|---|
| `evidence/topology/versions.txt` | T-Z01 tool versions |
| `evidence/topology/ip-addr.txt` | T-A01 |
| `evidence/topology/ip-route.txt` | T-A01 |
| `evidence/topology/ip-forward.txt` | T-A01 |
| `evidence/topology/traceroute.txt` | T-A02. Hop 1 `10.10.10.1`, hop 2 `10.20.20.10` |
| `evidence/security/nft-ruleset.txt` | T-A03, T-C02. Verification snapshot: 7 packets dropped client to data, 7 accepted client to API |
| `evidence/security/deny-mongo.txt` | T-A03. Body is `timeout` |
| `evidence/security/allow-api.txt` | T-C02. Body is `{"status":"live"}` |
| `evidence/security/tls-curl.txt` | T-C01 |
| `evidence/security/tls-openssl.txt` | T-C01. `Verify return code: 0 (ok)` |
| `evidence/security/tls-untrusted.txt` | T-C01 negative. curl error 60 |
| `evidence/logs/crud/` | T-B01, T-B02, FR-04, FR-05 |
| `evidence/logs/api-errors/` | T-B03 |
| `evidence/pcap/client-router.pcap` | T-D01 client side of the TLS post |
| `evidence/pcap/router-service.pcap` | T-D01 service side of the same post |
| `evidence/pcap/router-data.pcap` | T-D01 API to MongoDB. BSON, not TLS |
| `evidence/results/baseline/20261113T170217Z/summary.json` | T-E01, T-D02 |
| `evidence/results/delay/20261113T170217Z/summary.json` | T-E02 |
| `evidence/results/workload-match.json` | same coordinate hash, 200 posts each |
| `evidence/results/failure/20261113T170217Z/timeline.json` | T-F01, T-F02 |
| `evidence/logs/api.log` | API request log |
| `evidence/logs/mongod.log` | MongoDB log |
| `evidence/manifest.txt` | files present after the run |

Measured comparison for this stamp:

| Metric | Baseline | Delay 150 ms ± 20 ms |
|---|---:|---:|
| Posts | 200/200 | 200/200 |
| HTTP latency p50 | 1.323 ms | 324.061 ms |
| Delivery lag p50 | 1 ms | 166 ms |
| Location age p50 | 3 ms | 487 ms |
| Stale fraction (10 s) | 0/25 | 0/25 |
| Ping RTT average, loss | 0.109 ms, 0% | 313.376 ms, 0% |

`recovery_duration_ms` is 6034. `restart_to_ready_ms` is 1138. The timeline is `evidence/results/failure/20261113T170217Z/timeline.json`.
