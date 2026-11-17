"""Sample statistics. Percentiles use the nearest-rank method."""

from __future__ import annotations

import math


def mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = math.ceil((pct / 100.0) * len(ordered)) - 1
    rank = max(0, min(rank, len(ordered) - 1))
    return ordered[rank]


def summarize(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "mean": _round(mean(values)),
        "p50": _round(percentile(values, 50)),
        "p95": _round(percentile(values, 95)),
        "max": _round(max(values) if values else None),
    }


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 3)
