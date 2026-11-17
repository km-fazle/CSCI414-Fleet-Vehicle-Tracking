"""Replay a fixture file against the tracking API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from netclient import open_client, request_with_retries


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a FleetTrace fixture over HTTPS")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--ca", required=True)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--register-only", action="store_true")
    args = parser.parse_args()
    document = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    with open_client(args.base_url, args.ca, args.timeout) as client:
        for vehicle in document["vehicles"]:
            attempts = request_with_retries(
                client,
                "POST",
                "/api/v1/vehicles",
                operation="create_vehicle",
                vehicle_id=vehicle["vehicle_id"],
                json_body=vehicle,
                timeout=args.timeout,
                max_attempts=1,
            )
            status = attempts[-1].http_status
            if status not in (201, 409):
                raise SystemExit(f"vehicle {vehicle['vehicle_id']} failed with {status} {attempts[-1].error}")
            print(f"vehicle {vehicle['vehicle_id']} -> {status}")
        if args.register_only:
            return
        for event in document["events"]:
            body = dict(event)
            body.pop("label", None)
            attempts = request_with_retries(
                client,
                "POST",
                "/api/v1/telemetry",
                operation="post_telemetry",
                event_id=body["event_id"],
                vehicle_id=body["vehicle_id"],
                json_body=body,
                timeout=args.timeout,
                max_attempts=2,
            )
            status = attempts[-1].http_status
            print(f"event {body['event_id']} -> {status} {attempts[-1].error}")
            if status not in (200, 201):
                raise SystemExit(1)


if __name__ == "__main__":
    main()
