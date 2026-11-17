"""One HTTPS call, written as JSON. Used by the recovery and security scripts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from netclient import open_client, perform


def main() -> None:
    parser = argparse.ArgumentParser(description="Send one FleetTrace request and record it")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--ca", required=True)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--method", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--body-file")
    parser.add_argument("--operation", default="probe")
    parser.add_argument("--event-id", default="")
    parser.add_argument("--vehicle-id", default="")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    body = None
    if args.body_file:
        body = json.loads(Path(args.body_file).read_text(encoding="utf-8"))
    with open_client(args.base_url, args.ca, args.timeout) as client:
        result = perform(
            client,
            args.method,
            args.path,
            operation=args.operation,
            event_id=args.event_id,
            vehicle_id=args.vehicle_id,
            json_body=body,
            timeout=args.timeout,
        )
    document = {
        "operation": result.operation,
        "event_id": result.event_id,
        "vehicle_id": result.vehicle_id,
        "send_ts_utc": result.send_ts_utc,
        "response_ts_utc": result.response_ts_utc,
        "http_status": result.http_status,
        "latency_ms": None if result.latency_ms is None else round(result.latency_ms, 3),
        "timeout": result.timeout,
        "error": result.error,
        "body": result.body,
        "ok": result.http_status is not None and 200 <= result.http_status < 300,
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(document))


if __name__ == "__main__":
    main()
