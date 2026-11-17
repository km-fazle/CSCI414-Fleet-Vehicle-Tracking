"""Build one snapshot of the lab for the dispatch board."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = os.environ.get("FLEETTRACE_PYTHON", "/opt/fleettrace-venv/bin/python3")
PACKET_RE = re.compile(r"packets (\d+)")


def now_iso() -> str:
    moment = datetime.now(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def sh(args: list[str], timeout: float = 6) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 124, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def packet_count(line: str) -> int | None:
    match = PACKET_RE.search(line)
    if match is None:
        return None
    return int(match.group(1))


def parse_nft(text: str) -> dict:
    api_accept = None
    client_data_drop = None
    established = None
    for line in text.splitlines():
        if "dport 8443" in line and "accept" in line:
            api_accept = packet_count(line)
        elif 'iifname "c-rt"' in line and "10.30.30.0/24" in line and "drop" in line:
            client_data_drop = packet_count(line)
        elif "ct state established,related" in line:
            established = packet_count(line)
    return {
        "api_accept": api_accept,
        "client_data_drop": client_data_drop,
        "established": established,
    }


def summarize_qdisc(text: str) -> str:
    flat = " ".join(text.split())
    if not flat:
        return "absent"
    if "netem" in flat:
        return flat[flat.find("netem"):]
    if "noqueue" in flat:
        return "noqueue"
    return flat[:80]


def _env_value(name: str, default: str) -> str:
    path = ROOT / "network" / "addresses.env"
    other = ROOT / "network" / "experiment.env"
    for file in (path, other):
        if not file.exists():
            continue
        for line in file.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"export {name}="):
                return line.split("=", 1)[1].strip().strip('"')
    return default


def freshness_ms() -> int:
    raw = _env_value("FT_FRESHNESS_SECONDS", "10")
    try:
        return int(raw) * 1000
    except ValueError:
        return 10000


def slim_summary(doc: dict) -> dict:
    http = doc.get("http_latency_ms") or {}
    lag = doc.get("delivery_lag_ms") or {}
    age = doc.get("location_age_ms") or {}
    ping = (doc.get("network") or {}).get("ping") or {}
    rtt = ping.get("rtt_ms") or {}
    return {
        "post_successes": doc.get("post_successes"),
        "logical_posts": doc.get("logical_posts"),
        "events_per_second": doc.get("events_per_second"),
        "duration_s": doc.get("duration_s"),
        "http_p50": http.get("p50"),
        "http_p95": http.get("p95"),
        "lag_p50": lag.get("p50"),
        "age_p50": age.get("p50"),
        "age_p95": age.get("p95"),
        "stale_fraction": doc.get("stale_fraction"),
        "ping_avg": rtt.get("avg"),
        "ping_loss": ping.get("packet_loss_percent"),
    }


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_experiment(root: Path | None = None) -> dict:
    root = root or ROOT
    stamp_path = root / "evidence" / "results" / "latest-run.txt"
    if not stamp_path.is_file():
        return {"available": False}
    stamp = stamp_path.read_text(encoding="utf-8").strip()
    baseline = _read_json(root / "evidence" / "results" / "baseline" / stamp / "summary.json")
    delay = _read_json(root / "evidence" / "results" / "delay" / stamp / "summary.json")
    match = _read_json(root / "evidence" / "results" / "workload-match.json") or {}
    timeline = _read_json(root / "evidence" / "results" / "failure" / stamp / "timeline.json")
    recovery = None
    if timeline:
        retry = timeline.get("retry_after_recovery") or {}
        failed = timeline.get("failed_post_during_outage") or {}
        recovery = {
            "hold_seconds": timeline.get("hold_seconds"),
            "detected_down_at": timeline.get("detected_down_at"),
            "error": failed.get("error"),
            "restart_to_ready_ms": timeline.get("restart_to_ready_ms"),
            "restart_to_successful_write_ms": timeline.get("restart_to_successful_write_ms"),
            "recovery_duration_ms": timeline.get("recovery_duration_ms"),
            "retry_ok": bool(retry.get("ok")),
            "retry_duplicate": retry.get("duplicate"),
            "definition": timeline.get("definition"),
        }
    return {
        "available": baseline is not None or delay is not None,
        "stamp": stamp,
        "impairment": _env_value("FT_NETEM_DELAY", "delay 150ms 20ms"),
        "same_coordinates": match.get("same_coordinates"),
        "workload_sha256": match.get("left_sha256"),
        "baseline": slim_summary(baseline) if baseline else None,
        "delay": slim_summary(delay) if delay else None,
        "recovery": recovery,
    }


def _namespaces() -> list[str]:
    code, out, _err = sh(["ip", "netns", "list"])
    if code != 0:
        return []
    return [line.split()[0] for line in out.splitlines() if line.strip()]


def _pull_api(namespaces: list[str]) -> dict:
    if "ft-client" not in namespaces:
        return {"ok": False, "error": "ft-client is not up", "vehicles": [], "tracks": {}}
    code, out, err = sh([
        "ip", "netns", "exec", "ft-client", PYTHON, str(ROOT / "dashboard" / "client_pull.py"),
    ], timeout=12)
    if code != 0 and not out.strip():
        return {"ok": False, "error": (err or "client read failed").strip()[:400], "vehicles": [], "tracks": {}}
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        return {"ok": False, "error": "client read was not JSON", "vehicles": [], "tracks": {}}
    payload.setdefault("vehicles", [])
    payload.setdefault("tracks", {})
    return payload


def _zone(name: str, address: str, namespace: str, namespaces: list[str], up: bool, note: str) -> dict:
    present = namespace in namespaces
    return {
        "name": name,
        "address": address,
        "namespace": namespace,
        "present": present,
        "up": present and up,
        "note": note,
    }


def build_board() -> dict:
    namespaces = _namespaces()
    api = _pull_api(namespaces)
    live = api.get("live") or {}
    ready = api.get("ready") or {}
    live_ok = live.get("status_code") == 200
    ready_ok = ready.get("status_code") == 200
    forward_code, forward_out, _err = sh(
        ["ip", "netns", "exec", "ft-router", "cat", "/proc/sys/net/ipv4/ip_forward"]
    )
    forwarding = forward_out.strip() == "1" if forward_code == 0 else False
    client_q_code, client_q, _err = sh(["ip", "netns", "exec", "ft-client", "tc", "qdisc", "show", "dev", "c-ns"])
    router_q_code, router_q, _err = sh(["ip", "netns", "exec", "ft-router", "tc", "qdisc", "show", "dev", "c-rt"])
    nft_code, nft_out, nft_err = sh(
        ["ip", "netns", "exec", "ft-router", "nft", "list", "chain", "inet", "fleettrace", "forward"]
    )
    vehicles = sorted(api.get("vehicles") or [], key=lambda row: row.get("vehicle_id") or "")
    return {
        "observed_at": now_iso(),
        "freshness_threshold_ms": freshness_ms(),
        "api": {
            "ok": bool(api.get("ok")),
            "live": live_ok,
            "ready": ready_ok,
            "warm_ms": api.get("warm_ms"),
            "error": api.get("error"),
            "vehicle_count": len(vehicles),
        },
        "vehicles": vehicles,
        "tracks": api.get("tracks") or {},
        "network": {
            "namespaces": namespaces,
            "forwarding": forwarding,
            "client_qdisc": summarize_qdisc(client_q) if client_q_code == 0 else "absent",
            "router_qdisc": summarize_qdisc(router_q) if router_q_code == 0 else "absent",
            "firewall": parse_nft(nft_out) if nft_code == 0 else None,
            "firewall_error": None if nft_code == 0 else (nft_err or "firewall not loaded").strip()[:200],
            "zones": [
                _zone("Client", "10.10.10.10", "ft-client", namespaces, True, "workload"),
                _zone("Router", "10.10.10.1", "ft-router", namespaces, forwarding, "forwarding on" if forwarding else "forwarding off"),
                _zone("API", "10.20.20.10:8443", "ft-service", namespaces, live_ok, "TLS" if live_ok else "not answering"),
                _zone("MongoDB", "10.30.30.10:27017", "ft-data", namespaces, ready_ok, "ready" if ready_ok else "not ready"),
            ],
        },
        "experiment": load_experiment(ROOT),
    }
