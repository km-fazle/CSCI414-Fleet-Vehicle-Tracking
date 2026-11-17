"""Create, update, and read two lab vehicles. One position is fresh and one is old."""

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

from netclient import iso, open_client, perform, utc_now


def _save(directory: Path, name: str, attempt) -> dict:
    document = {
        "operation": attempt.operation,
        "http_status": attempt.http_status,
        "error": attempt.error,
        "latency_ms": None if attempt.latency_ms is None else round(attempt.latency_ms, 3),
        "body": attempt.body,
    }
    (directory / name).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return document


def _require(document: dict, status: int, name: str) -> None:
    if document["http_status"] != status:
        raise SystemExit(f"{name} expected {status}, got {document['http_status']} {document['error']}")


def run(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    with open_client(args.base_url, args.ca, args.timeout) as client:
        created = perform(
            client,
            "POST",
            "/api/v1/vehicles",
            operation="create_vehicle",
            vehicle_id="lab-fresh",
            json_body={"vehicle_id": "lab-fresh", "label": "Fresh lab vehicle", "type": "simulated"},
            timeout=args.timeout,
        )
        created_doc = _save(out, "create-fresh.json", created)
        if created_doc["http_status"] not in (201, 409):
            raise SystemExit(f"create lab-fresh failed: {created_doc}")
        stale_vehicle = perform(
            client,
            "POST",
            "/api/v1/vehicles",
            operation="create_vehicle",
            vehicle_id="lab-stale",
            json_body={"vehicle_id": "lab-stale", "label": "Stale lab vehicle", "type": "simulated"},
            timeout=args.timeout,
        )
        stale_vehicle_doc = _save(out, "create-stale.json", stale_vehicle)
        if stale_vehicle_doc["http_status"] not in (201, 409):
            raise SystemExit(f"create lab-stale failed: {stale_vehicle_doc}")

        patched = perform(
            client,
            "PATCH",
            "/api/v1/vehicles/lab-fresh",
            operation="patch_vehicle",
            vehicle_id="lab-fresh",
            json_body={"label": "Fresh lab vehicle updated", "metadata": {"role": "crud-demo"}},
            timeout=args.timeout,
        )
        patched_doc = _save(out, "patch-fresh.json", patched)
        _require(patched_doc, 200, "patch")
        if patched_doc["body"]["label"] != "Fresh lab vehicle updated":
            raise SystemExit("patch did not update the label")

        fresh_body = {
            "event_id": args.fresh_event_id,
            "vehicle_id": "lab-fresh",
            "event_time": iso(now),
            "lat": 40.7543219,
            "lon": -73.9808123,
            "sequence": 1,
            "simulation_run_id": args.run_id,
            "source_type": "synthetic",
            "generation_method": "deterministic_linear_track",
            "simulation_seed": 42,
        }
        posted = perform(
            client,
            "POST",
            "/api/v1/telemetry",
            operation="post_telemetry",
            event_id=args.fresh_event_id,
            vehicle_id="lab-fresh",
            json_body=fresh_body,
            timeout=args.timeout,
            generated_event_ts=now,
        )
        posted_doc = _save(out, "post-fresh.json", posted)
        _require(posted_doc, 201, "post fresh")

        old_time = now - timedelta(seconds=60)
        stale_body = {
            "event_id": args.stale_event_id,
            "vehicle_id": "lab-stale",
            "event_time": iso(old_time),
            "lat": 40.7301,
            "lon": -73.9902,
            "sequence": 1,
            "simulation_run_id": args.run_id,
            "source_type": "synthetic",
            "generation_method": "deterministic_linear_track",
            "simulation_seed": 42,
        }
        stale_post = perform(
            client,
            "POST",
            "/api/v1/telemetry",
            operation="post_telemetry",
            event_id=args.stale_event_id,
            vehicle_id="lab-stale",
            json_body=stale_body,
            timeout=args.timeout,
            generated_event_ts=old_time,
        )
        stale_post_doc = _save(out, "post-stale.json", stale_post)
        _require(stale_post_doc, 201, "post stale")
        (out / "bodies.json").write_text(
            json.dumps({"fresh": fresh_body, "stale": stale_body}, indent=2) + "\n",
            encoding="utf-8",
        )

    verify(args)


def verify(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open_client(args.base_url, args.ca, args.timeout) as client:
        fresh = perform(
            client,
            "GET",
            "/api/v1/vehicles/lab-fresh/latest",
            operation="get_latest",
            vehicle_id="lab-fresh",
            timeout=args.timeout,
        )
        fresh_doc = _save(out, "latest-fresh.json", fresh)
        _require(fresh_doc, 200, "latest fresh")
        if fresh_doc["body"]["latest"]["event_id"] != args.fresh_event_id:
            raise SystemExit("fresh latest event id did not match")
        if fresh_doc["body"]["stale"] is not False:
            raise SystemExit(f"expected fresh position to be stale=false, body={fresh_doc['body']}")

        stale = perform(
            client,
            "GET",
            "/api/v1/vehicles/lab-stale/latest",
            operation="get_latest",
            vehicle_id="lab-stale",
            timeout=args.timeout,
        )
        stale_doc = _save(out, "latest-stale.json", stale)
        _require(stale_doc, 200, "latest stale")
        if stale_doc["body"]["stale"] is not True:
            raise SystemExit(f"expected old position to be stale=true, body={stale_doc['body']}")

        history = perform(
            client,
            "GET",
            "/api/v1/vehicles/lab-fresh/history?limit=10",
            operation="get_history",
            vehicle_id="lab-fresh",
            timeout=args.timeout,
        )
        history_doc = _save(out, "history-fresh.json", history)
        _require(history_doc, 200, "history")
        ids = [event["event_id"] for event in history_doc["body"]["events"]]
        if args.fresh_event_id not in ids:
            raise SystemExit("history is missing the fresh event")
    print(json.dumps({"crud": "ok", "fresh_event_id": args.fresh_event_id, "stale_event_id": args.stale_event_id}))


def main() -> None:
    parser = argparse.ArgumentParser(description="Exercise vehicle create, update, and telemetry readback")
    parser.add_argument("phase", choices=["run", "verify"])
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--ca", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--run-id", default="crud-demo")
    parser.add_argument("--fresh-event-id", required=True)
    parser.add_argument("--stale-event-id", required=True)
    args = parser.parse_args()
    if args.phase == "run":
        run(args)
    else:
        verify(args)


if __name__ == "__main__":
    main()
