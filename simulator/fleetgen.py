"""Deterministic synthetic tracks that follow real Manhattan avenues.

Coordinates and sequence numbers are a pure function of the vehicle count,
events per vehicle, and seed. The path is sampled every few meters along a
fixed driving trace, then turns around at the end of the avenue, so a drawn
track stays on the street. Event timestamps and event IDs are applied by the
caller so a live run can stamp the actual emission time.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VehicleSpec:
    vehicle_id: str
    label: str
    index: int


@dataclass(frozen=True)
class TrackPoint:
    vehicle_id: str
    label: str
    sequence: int
    lat: float
    lon: float


def vehicle_specs(count: int) -> list[VehicleSpec]:
    if count < 1 or count > 100:
        raise ValueError("vehicle count must be between 1 and 100")
    return [
        VehicleSpec(vehicle_id=f"demo-{index:03d}", label=f"Vehicle {index:03d}", index=index)
        for index in range(1, count + 1)
    ]


_STREETS = json.loads((Path(__file__).with_name("streets.json")).read_text(encoding="utf-8"))
STREET_STEP_M = float(_STREETS["step_m"])
_ROUTES = _STREETS["routes"]


def _meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat = math.radians((a[1] + b[1]) / 2)
    dx = math.radians(b[0] - a[0]) * math.cos(lat) * 6_371_000
    dy = math.radians(b[1] - a[1]) * 6_371_000
    return math.hypot(dx, dy)


def _cumulative(coords: list[list[float]]) -> list[float]:
    totals = [0.0]
    for start, end in zip(coords, coords[1:]):
        totals.append(totals[-1] + _meters(tuple(start), tuple(end)))
    return totals


def _at_distance(coords: list[list[float]], totals: list[float], distance: float) -> tuple[float, float]:
    length = totals[-1]
    if length <= 0:
        lon, lat = coords[0]
        return lat, lon
    span = length * 2
    walked = distance % span
    if walked > length:
        walked = span - walked
    for index in range(1, len(totals)):
        if totals[index] >= walked:
            span_m = totals[index] - totals[index - 1]
            frac = 0 if span_m == 0 else (walked - totals[index - 1]) / span_m
            lon0, lat0 = coords[index - 1]
            lon1, lat1 = coords[index]
            lon = lon0 + (lon1 - lon0) * frac
            lat = lat0 + (lat1 - lat0) * frac
            return lat, lon
    lon, lat = coords[-1]
    return lat, lon


def _route_for(vehicle_id: str, seed: int) -> tuple[dict, float]:
    if vehicle_id.startswith("demo-") and vehicle_id[5:].isdigit():
        index = int(vehicle_id[5:])
    else:
        index = int(hashlib.sha256(vehicle_id.encode()).hexdigest()[:6], 16)
    route = _ROUTES[(index - 1) % len(_ROUTES)]
    lane = (index - 1) // len(_ROUTES)
    length = _cumulative(route["coordinates"])[-1]
    start = (lane * 220 + (seed % 29) * 15) % max(length * 0.5, 1)
    return route, start


def _sample(coords: list[list[float]], count: int, start_m: float) -> list[tuple[float, float]]:
    totals = _cumulative(coords)
    return [
        _at_distance(coords, totals, start_m + step * STREET_STEP_M)
        for step in range(count)
    ]


def street_positions(vehicle_id: str, count: int, seed: int = 42) -> list[tuple[float, float]]:
    """`count` positions along one avenue, in sequence order, about 18 m apart."""
    if count < 1:
        return []
    route, start = _route_for(vehicle_id, seed)
    return _sample(route["coordinates"], count, start)


def national_routes() -> list[dict]:
    return list(_STREETS.get("national") or [])


def positions_on_route(name: str, count: int, start_m: float = 80) -> list[tuple[float, float]]:
    """Positions along one named city route. The Manhattan lab routes are separate."""
    match = next((route for route in national_routes() if route["name"] == name), None)
    if match is None:
        raise KeyError(name)
    return _sample(match["coordinates"], count, start_m)


def track_points(vehicles: int, events_per_vehicle: int, seed: int) -> list[TrackPoint]:
    if events_per_vehicle < 1 or events_per_vehicle > 10000:
        raise ValueError("events_per_vehicle must be between 1 and 10000")
    specs = vehicle_specs(vehicles)
    by_vehicle = {
        spec.vehicle_id: street_positions(spec.vehicle_id, events_per_vehicle, seed)
        for spec in specs
    }
    points: list[TrackPoint] = []
    for sequence in range(1, events_per_vehicle + 1):
        for spec in specs:
            lat, lon = by_vehicle[spec.vehicle_id][sequence - 1]
            lat = round(lat, 7)
            lon = round(lon, 7)
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                raise ValueError(f"generated coordinate out of range: {lat}, {lon}")
            points.append(
                TrackPoint(
                    vehicle_id=spec.vehicle_id,
                    label=spec.label,
                    sequence=sequence,
                    lat=lat,
                    lon=lon,
                )
            )
    return points


def workload_fingerprint(points: list[TrackPoint]) -> str:
    """Hash of positions only, so two runs can prove they sent the same track."""
    payload = "\n".join(
        f"{point.vehicle_id},{point.sequence},{point.lat:.7f},{point.lon:.7f}" for point in points
    )
    return hashlib.sha256(payload.encode()).hexdigest()
