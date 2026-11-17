"""Write a small deterministic fixture. This file has no third-party imports."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fleetgen import track_points, vehicle_specs, workload_fingerprint


def build_fixture(
    vehicles: int,
    events_per_vehicle: int,
    seed: int,
    interval_ms: int,
    start: datetime,
    run_id: str,
) -> dict:
    points = track_points(vehicles, events_per_vehicle, seed)
    specs = {spec.vehicle_id: spec for spec in vehicle_specs(vehicles)}
    events = []
    for point in points:
        index = specs[point.vehicle_id].index
        event_time = start + timedelta(milliseconds=(point.sequence - 1) * interval_ms + (index - 1))
        events.append(
            {
                "event_id": f"{point.vehicle_id}-{point.sequence:06d}",
                "vehicle_id": point.vehicle_id,
                "label": point.label,
                "sequence": point.sequence,
                "event_time": event_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "lat": point.lat,
                "lon": point.lon,
                "simulation_run_id": run_id,
                "simulation_seed": seed,
                "source_type": "synthetic",
                "generation_method": "deterministic_linear_track",
            }
        )
    return {
        "seed": seed,
        "run_id": run_id,
        "interval_ms": interval_ms,
        "source_type": "synthetic",
        "generation_method": "deterministic_linear_track",
        "workload_sha256": workload_fingerprint(points),
        "note": "Synthetic positions. These are not GPS traces.",
        "vehicles": [{"vehicle_id": spec.vehicle_id, "label": spec.label, "type": "simulated"} for spec in vehicle_specs(vehicles)],
        "events": events,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a deterministic synthetic fleet fixture")
    parser.add_argument("--vehicles", type=int, default=2)
    parser.add_argument("--events-per-vehicle", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--interval-ms", type=int, default=1000)
    parser.add_argument("--start", default="2026-11-13T16:00:00Z")
    parser.add_argument("--run-id", default="fixture-seed42")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    start = datetime.fromisoformat(args.start.replace("Z", "+00:00"))
    document = build_fixture(
        args.vehicles,
        args.events_per_vehicle,
        args.seed,
        args.interval_ms,
        start,
        args.run_id,
    )
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path} events={len(document['events'])} sha256={document['workload_sha256']}")


if __name__ == "__main__":
    main()
