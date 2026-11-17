"""Parsers for the dispatch board. They do not open a network namespace."""

import json
from pathlib import Path

from dashboard.collect import load_experiment, parse_nft, slim_summary, summarize_qdisc

NFT = """
\t\tct state established,related counter packets 225 bytes 40500 accept
\t\tiifname "c-rt" oifname "s-rt" ip saddr 10.10.10.0/24 ip daddr 10.20.20.10 tcp dport 8443 counter packets 7 bytes 420 accept
\t\tiifname "c-rt" oifname "d-rt" ip daddr 10.30.30.0/24 counter packets 4 bytes 240 drop
"""


def test_parse_nft_counts_allow_and_drop():
    parsed = parse_nft(NFT)
    assert parsed["established"] == 225
    assert parsed["api_accept"] == 7
    assert parsed["client_data_drop"] == 4


def test_summarize_qdisc_names_the_impairment():
    assert summarize_qdisc("qdisc noqueue 0: root refcnt 2") == "noqueue"
    assert summarize_qdisc("qdisc netem 1: root refcnt 2 limit 1000 delay 150ms 20ms") == "netem 1: root refcnt 2 limit 1000 delay 150ms 20ms"
    assert summarize_qdisc("") == "absent"


def test_slim_summary_drops_raw_ping_text():
    slim = slim_summary({
        "post_successes": 200,
        "logical_posts": 200,
        "events_per_second": 2.5,
        "http_latency_ms": {"p50": 1.25, "p95": 2.0},
        "delivery_lag_ms": {"p50": 1.0},
        "location_age_ms": {"p50": 3.0, "p95": 28.0},
        "stale_fraction": 0.0,
        "network": {"ping_raw": "PING should not be copied", "ping": {"packet_loss_percent": 0.0, "rtt_ms": {"avg": 0.2}}},
    })
    assert "ping_raw" not in json.dumps(slim)
    assert slim["http_p50"] == 1.25
    assert slim["ping_avg"] == 0.2


def test_recorded_run_is_readable():
    root = Path(__file__).resolve().parents[2]
    stamp_path = root / "evidence" / "results" / "latest-run.txt"
    if not stamp_path.is_file():
        return
    loaded = load_experiment(root)
    assert loaded["stamp"] == stamp_path.read_text(encoding="utf-8").strip()
    assert loaded["same_coordinates"] is True
    assert loaded["baseline"]["logical_posts"] == 200
    assert loaded["delay"]["logical_posts"] == 200
