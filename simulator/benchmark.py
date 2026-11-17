"""Run a fixed synthetic workload and write CSV plus summary JSON.

Coordinates come from the seed. event_time is the emission time on this host,
which is the same clock domain as the API when both run in the lab container.
event_id includes the run id so a repeated scenario inserts new rows instead of
hitting the idempotent duplicate path.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from fleetgen import track_points, vehicle_specs, workload_fingerprint
from netclient import RetryQueue, iso, open_client, request_with_retries, utc_now
from stats import summarize


CSV_FIELDS = [
    "run_id",
    "scenario",
    "operation",
    "event_id",
    "vehicle_id",
    "attempt",
    "send_ts_utc",
    "response_ts_utc",
    "http_status",
    "latency_ms",
    "timeout",
    "error",
    "generated_event_ts_utc",
    "age_ms",
    "stale",
    "duplicate",
]


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _delivery_lag_ms(attempt) -> float | None:
    body = attempt.body or {}
    received = body.get("received_at")
    if not received or not attempt.generated_event_ts_utc:
        return None
    try:
        lag = (_parse_time(received) - _parse_time(attempt.generated_event_ts_utc)).total_seconds() * 1000
    except ValueError:
        return None
    return lag


def register_vehicles(client, vehicles: int, timeout: float) -> None:
    for spec in vehicle_specs(vehicles):
        attempts = request_with_retries(
            client,
            "POST",
            "/api/v1/vehicles",
            operation="create_vehicle",
            vehicle_id=spec.vehicle_id,
            json_body={"vehicle_id": spec.vehicle_id, "label": spec.label, "type": "simulated"},
            timeout=timeout,
            max_attempts=1,
        )
        status = attempts[-1].http_status
        if status not in (201, 409):
            raise SystemExit(f"failed to register {spec.vehicle_id}: {status} {attempts[-1].error}")


def run_workload(args: argparse.Namespace) -> None:
    points = track_points(args.vehicles, args.events_per_vehicle, args.seed)
    fingerprint = workload_fingerprint(points)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    rows = []
    queue = RetryQueue(maxlen=args.queue_size)
    logical = []

    with open_client(args.base_url, args.ca, args.timeout) as client:
        warmup = request_with_retries(
            client,
            "GET",
            "/health/live",
            operation="warmup",
            timeout=args.timeout,
            max_attempts=1,
        )
        if warmup[-1].http_status != 200:
            raise SystemExit(f"API liveness check failed: {warmup[-1].http_status} {warmup[-1].error}")
        register_vehicles(client, args.vehicles, args.timeout)

        for index, point in enumerate(points, start=1):
            generated = utc_now()
            event_id = f"{args.run_id}-{point.vehicle_id}-{point.sequence:06d}"
            body = {
                "event_id": event_id,
                "vehicle_id": point.vehicle_id,
                "event_time": iso(generated),
                "lat": point.lat,
                "lon": point.lon,
                "sequence": point.sequence,
                "simulation_run_id": args.run_id,
                "source_type": "synthetic",
                "generation_method": "deterministic_linear_track",
                "simulation_seed": args.seed,
            }
            attempts = request_with_retries(
                client,
                "POST",
                "/api/v1/telemetry",
                operation="post_telemetry",
                event_id=event_id,
                vehicle_id=point.vehicle_id,
                json_body=body,
                timeout=args.timeout,
                generated_event_ts=generated,
                max_attempts=args.max_retries,
                headers={"X-Request-ID": event_id},
            )
            rows.extend(attempts)
            final = attempts[-1]
            if final.http_status not in (200, 201):
                queue.add({"body": body, "generated": iso(generated), "event_id": event_id, "vehicle_id": point.vehicle_id})
            logical.append(final)
            if args.interval_ms > 0 and index != len(points):
                time.sleep(args.interval_ms / 1000.0)
            if args.query_every and index % args.query_every == 0:
                query = request_with_retries(
                    client,
                    "GET",
                    f"/api/v1/vehicles/{point.vehicle_id}/latest",
                    operation="get_latest",
                    event_id=event_id,
                    vehicle_id=point.vehicle_id,
                    timeout=args.timeout,
                    max_attempts=1,
                )
                rows.extend(query)

        flushed = 0
        for item in queue.drain():
            attempts = request_with_retries(
                client,
                "POST",
                "/api/v1/telemetry",
                operation="flush_telemetry",
                event_id=item["event_id"],
                vehicle_id=item["vehicle_id"],
                json_body=item["body"],
                timeout=args.timeout,
                generated_event_ts=_parse_time(item["generated"]),
                max_attempts=1,
                headers={"X-Request-ID": item["event_id"]},
            )
            rows.extend(attempts)
            flushed += 1
            if attempts[-1].http_status in (200, 201):
                logical.append(attempts[-1])

        age_rows = []
        for spec in vehicle_specs(args.vehicles):
            query = request_with_retries(
                client,
                "GET",
                f"/api/v1/vehicles/{spec.vehicle_id}/latest",
                operation="get_latest",
                vehicle_id=spec.vehicle_id,
                timeout=args.timeout,
                max_attempts=1,
            )
            rows.extend(query)
            age_rows.extend(query)
            history = request_with_retries(
                client,
                "GET",
                f"/api/v1/vehicles/{spec.vehicle_id}/history?limit=5",
                operation="get_history",
                vehicle_id=spec.vehicle_id,
                timeout=args.timeout,
                max_attempts=1,
            )
            rows.extend(history)

        finished = utc_now()
        duration_s = max((finished - started).total_seconds(), 0.001)
        post_success = [row for row in rows if row.operation == "post_telemetry" and row.http_status in (200, 201)]
        post_attempts = [row for row in rows if row.operation == "post_telemetry"]
        timeouts = [row for row in rows if row.timeout]
        succeeded_ids = {row.event_id for row in rows if row.operation in {"post_telemetry", "flush_telemetry"} and row.http_status in (200, 201)}
        logical_posts = len(points)
        post_failures = logical_posts - len(succeeded_ids)
        age_values = [float(row.age_ms) for row in rows if row.operation == "get_latest" and row.http_status == 200 and row.age_ms is not None]
        stale_rows = [row for row in rows if row.operation == "get_latest" and row.http_status == 200 and row.stale is not None]
        stale_count = sum(1 for row in stale_rows if row.stale)
        fresh_count = sum(1 for row in stale_rows if not row.stale)
        lags = [lag for lag in (_delivery_lag_ms(row) for row in post_success) if lag is not None]
        latency_values = [row.latency_ms for row in post_success if row.latency_ms is not None]
        threshold = None
        for row in age_rows:
            if row.body and isinstance(row.body.get("freshness_threshold_ms"), int):
                threshold = row.body["freshness_threshold_ms"]
                break
        summary = {
            "run_id": args.run_id,
            "scenario": args.scenario,
            "seed": args.seed,
            "vehicles": args.vehicles,
            "events_per_vehicle": args.events_per_vehicle,
            "interval_ms": args.interval_ms,
            "workload_sha256": fingerprint,
            "percentile_method": "nearest_rank",
            "clock_domain": "client and API share the lab container clock; event_time is emission time, not a historical taxi timestamp",
            "started_at": iso(started),
            "finished_at": iso(finished),
            "duration_s": round(duration_s, 3),
            "freshness_threshold_ms": threshold,
            "logical_posts": logical_posts,
            "post_successes": len(succeeded_ids),
            "post_failures": post_failures,
            "attempts": len(post_attempts),
            "timeouts": len(timeouts),
            "success_rate": round(len(succeeded_ids) / logical_posts, 4) if logical_posts else None,
            "error_rate": round(post_failures / logical_posts, 4) if logical_posts else None,
            "retry_queue_dropped": queue.dropped,
            "flush_attempts": flushed,
            "http_latency_ms": summarize(latency_values),
            "delivery_lag_ms": summarize(lags),
            "location_age_ms": summarize(age_values),
            "fresh_queries": fresh_count,
            "stale_queries": stale_count,
            "stale_fraction": round(stale_count / len(stale_rows), 4) if stale_rows else None,
            "events_per_second": round(len(succeeded_ids) / duration_s, 3),
            "runtime": {
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
            "notes": [
                "http_latency_ms is client monotonic time for successful POST attempts and includes network RTT plus server time.",
                "delivery_lag_ms is API received_at minus client emission time. Both clocks are this container's UTC clock.",
                "location_age_ms comes from GET /latest and uses the event's generated event_time.",
                "A 10 second freshness threshold often stays fresh under a few hundred milliseconds of delay. Compare location_age_ms, not only stale_fraction.",
                "Failed posts are retried, then one flush pass runs. success_rate is after that flush.",
            ],
        }
        run_doc = {
            "run_id": args.run_id,
            "mode": args.scenario if args.scenario in {"baseline", "delay", "loss", "failure"} else "demo",
            "seed": args.seed,
            "vehicle_count": args.vehicles,
            "send_interval_ms": args.interval_ms,
            "impairment": {},
            "result_artifact_path": str(out),
            "started_at": iso(started),
            "finished_at": iso(finished),
        }
        meta = request_with_retries(
            client,
            "POST",
            "/api/v1/simulation-runs",
            operation="save_run",
            json_body=run_doc,
            timeout=args.timeout,
            max_attempts=1,
        )
        summary["simulation_run_post_status"] = meta[-1].http_status
        rows.extend(meta)

    _write_csv(out / "requests.csv", rows, args.run_id, args.scenario)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(out), "success_rate": summary["success_rate"], "workload_sha256": fingerprint}))


def _write_csv(path: Path, attempts, run_id: str, scenario: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for attempt in attempts:
            writer.writerow(attempt.csv_row(run_id, scenario))


def attach_network(args: argparse.Namespace) -> None:
    summary_path = Path(args.summary)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    network: dict[str, object] = {}
    if args.ping:
        raw = Path(args.ping).read_text(encoding="utf-8", errors="replace")
        network["ping_raw"] = raw
        network["ping"] = _parse_ping(raw)
    if args.iperf:
        iperf_path = Path(args.iperf)
        if iperf_path.exists() and iperf_path.stat().st_size:
            raw = iperf_path.read_text(encoding="utf-8", errors="replace")
            network["iperf_raw_path"] = str(iperf_path)
            network["iperf3"] = _parse_iperf(raw)
        else:
            network["iperf3"] = {"available": False, "reason": "iperf output missing"}
    tc_text = []
    for tc_path in args.tc or []:
        path = Path(tc_path)
        if path.exists():
            tc_text.append(f"# {path.name}\n" + path.read_text(encoding="utf-8", errors="replace"))
    network["tc"] = "\n".join(tc_text)
    if args.impairment:
        network["impairment"] = args.impairment
    summary["network"] = network
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def _parse_ping(raw: str) -> dict[str, object]:
    loss = re.search(r"(\d+(?:\.\d+)?)% packet loss", raw)
    rtt = re.search(r"rtt .* = ([0-9.]+)/([0-9.]+)/([0-9.]+)/([0-9.]+) ms", raw)
    parsed: dict[str, object] = {"available": False}
    if loss:
        parsed["packet_loss_percent"] = float(loss.group(1))
        parsed["available"] = True
    if rtt:
        parsed["rtt_ms"] = {
            "min": float(rtt.group(1)),
            "avg": float(rtt.group(2)),
            "max": float(rtt.group(3)),
            "mdev": float(rtt.group(4)),
        }
        parsed["available"] = True
    if not parsed["available"]:
        parsed["reason"] = "ping summary could not be parsed"
    return parsed


def _parse_iperf(raw: str) -> dict[str, object]:
    try:
        document = json.loads(raw)
    except json.JSONDecodeError:
        return {"available": False, "reason": "iperf output was not JSON"}
    if document.get("error"):
        return {"available": False, "reason": document["error"]}
    end = document.get("end", {})
    sent = end.get("sum_sent") or end.get("sum") or {}
    bps = sent.get("bits_per_second")
    if bps is None:
        return {"available": False, "reason": "bits_per_second missing"}
    return {
        "available": True,
        "bits_per_second": bps,
        "megabits_per_second": round(bps / 1_000_000, 3),
        "seconds": sent.get("seconds"),
        "retransmits": sent.get("retransmits"),
    }


def compare_fingerprints(args: argparse.Namespace) -> None:
    left = json.loads(Path(args.left).read_text(encoding="utf-8"))
    right = json.loads(Path(args.right).read_text(encoding="utf-8"))
    same = left.get("workload_sha256") == right.get("workload_sha256")
    report = {
        "left": args.left,
        "right": args.right,
        "left_sha256": left.get("workload_sha256"),
        "right_sha256": right.get("workload_sha256"),
        "same_coordinates": same,
        "left_logical_posts": left.get("logical_posts"),
        "right_logical_posts": right.get("logical_posts"),
    }
    print(json.dumps(report, indent=2))
    if not same or left.get("logical_posts") != right.get("logical_posts"):
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FleetTrace experiment workload")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run")
    run.add_argument("--base-url", required=True)
    run.add_argument("--ca", required=True)
    run.add_argument("--scenario", required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--output-dir", required=True)
    run.add_argument("--vehicles", type=int, default=5)
    run.add_argument("--events-per-vehicle", type=int, default=40)
    run.add_argument("--interval-ms", type=int, default=0)
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--timeout", type=float, default=8.0)
    run.add_argument("--max-retries", type=int, default=3)
    run.add_argument("--query-every", type=int, default=10)
    run.add_argument("--queue-size", type=int, default=100)
    run.set_defaults(func=run_workload)

    attach = sub.add_parser("attach-network")
    attach.add_argument("--summary", required=True)
    attach.add_argument("--ping")
    attach.add_argument("--iperf")
    attach.add_argument("--tc", action="append")
    attach.add_argument("--impairment", default="")
    attach.set_defaults(func=attach_network)

    compare = sub.add_parser("compare-fingerprints")
    compare.add_argument("--left", required=True)
    compare.add_argument("--right", required=True)
    compare.set_defaults(func=compare_fingerprints)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
