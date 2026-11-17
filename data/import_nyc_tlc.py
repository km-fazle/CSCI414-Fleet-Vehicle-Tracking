"""Import a local TLC-style CSV into synthetic telemetry JSON.

The NYC TLC trip files are large and are not committed. Download a file yourself
and pass its path. See data/README.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tlc import convert_rows, load_zone_lookup, read_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a small TLC-style CSV into derived position events")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--zone-lookup")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--intermediates", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--vehicle-id", default="tlc-derived-001")
    args = parser.parse_args()
    zones = load_zone_lookup(args.zone_lookup) if args.zone_lookup else None
    events = convert_rows(
        read_csv(args.csv, args.limit),
        zones=zones,
        intermediates=args.intermediates,
        seed=args.seed,
        vehicle_id=args.vehicle_id,
    )
    document = {
        "source_type": "nyc_tlc_derived",
        "vehicle_id": args.vehicle_id,
        "seed": args.seed,
        "events": events,
        "warning": "Interpolated points are synthetic. Do not describe them as taxi GPS tracks.",
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(events)} derived events to {path}")


if __name__ == "__main__":
    main()
