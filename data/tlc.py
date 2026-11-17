"""Turn a small TLC-style trip table into synthetic position events.

Trip records are not continuous GPS. Intermediate points are interpolated and
labeled nyc_tlc_derived. This module does not download data.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable


def load_zone_lookup(path: str | Path) -> dict[str, tuple[float, float]]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    lookup = {}
    for zone_id, value in document["zones"].items():
        lookup[str(zone_id)] = (float(value["lat"]), float(value["lon"]))
    return lookup


def interpolate(start: tuple[float, float], end: tuple[float, float], count: int) -> list[tuple[float, float]]:
    if count < 2:
        raise ValueError("count must include both endpoints")
    points = []
    for index in range(count):
        fraction = index / (count - 1)
        lat = start[0] + (end[0] - start[0]) * fraction
        lon = start[1] + (end[1] - start[1]) * fraction
        points.append((round(lat, 7), round(lon, 7)))
    return points


def _endpoints(row: dict, zones: dict[str, tuple[float, float]] | None) -> tuple[tuple[float, float], tuple[float, float], str]:
    if row.get("pickup_latitude") and row.get("pickup_longitude") and row.get("dropoff_latitude") and row.get("dropoff_longitude"):
        start = (float(row["pickup_latitude"]), float(row["pickup_longitude"]))
        end = (float(row["dropoff_latitude"]), float(row["dropoff_longitude"]))
        return start, end, "trip_endpoint_or_linear_interpolation"
    if zones is None:
        raise ValueError("zone lookup is required when the file has location IDs instead of coordinates")
    start = zones[str(row["PULocationID"])]
    end = zones[str(row["DOLocationID"])]
    return start, end, "linear_interpolation_between_zone_centroids"


def convert_rows(
    rows: Iterable[dict],
    *,
    zones: dict[str, tuple[float, float]] | None,
    intermediates: int,
    seed: int,
    vehicle_id: str,
) -> list[dict]:
    """intermediates is the number of points strictly between the two endpoints."""
    events = []
    sequence = 1
    for row_index, row in enumerate(rows, start=1):
        start, end, method = _endpoints(row, zones)
        count = intermediates + 2
        for point_index, (lat, lon) in enumerate(interpolate(start, end, count)):
            point_method = "trip_endpoint" if point_index in {0, count - 1} else method
            record_id = row.get("record_id") or f"row-{row_index}"
            events.append(
                {
                    "event_id": f"{vehicle_id}-{sequence:06d}",
                    "vehicle_id": vehicle_id,
                    "sequence": sequence,
                    "lat": lat,
                    "lon": lon,
                    "source_type": "nyc_tlc_derived",
                    "source_record_id": record_id,
                    "generation_method": point_method,
                    "simulation_seed": seed,
                    "note": "Derived for the lab. Not a continuous GPS trace.",
                }
            )
            sequence += 1
    return events


def read_csv(path: str | Path, limit: int) -> list[dict]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return rows[:limit]
