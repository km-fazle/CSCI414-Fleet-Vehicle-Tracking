"""Generator and statistic tests. No network."""

import math

from fleetgen import track_points, workload_fingerprint
from stats import percentile, summarize


def test_track_is_deterministic_and_bounded() -> None:
    first = track_points(5, 20, 42)
    second = track_points(5, 20, 42)
    assert first == second
    assert workload_fingerprint(first) == workload_fingerprint(second)
    assert track_points(5, 20, 7) != first
    assert len(first) == 100
    assert len({(point.vehicle_id, point.sequence) for point in first}) == 100
    assert all(-90 <= point.lat <= 90 and -180 <= point.lon <= 180 for point in first)


def test_tracks_follow_the_street() -> None:
    points = [point for point in track_points(5, 40, 42) if point.vehicle_id == "demo-001"]
    assert len(points) == 40
    for previous, current in zip(points, points[1:]):
        lat = (previous.lat + current.lat) / 2
        dx = (current.lon - previous.lon) * 111_320 * math.cos(math.radians(lat))
        dy = (current.lat - previous.lat) * 110_540
        assert (dx * dx + dy * dy) ** 0.5 < 25
    assert all(40.70 <= point.lat <= 40.78 and -74.03 <= point.lon <= -73.96 for point in points)


def test_large_fixture_stays_in_range() -> None:
    points = track_points(20, 50, 42)
    assert len(points) == 1000
    assert all(-90 <= point.lat <= 90 and -180 <= point.lon <= 180 for point in points)


def test_percentile_nearest_rank() -> None:
    assert percentile([], 95) is None
    assert percentile([5], 95) == 5
    # 20 samples: rank ceil(0.95*20)-1 = 18, which is the 19th ordered value.
    values = list(range(1, 21))
    assert percentile(values, 95) == 19
    summary = summarize(values)
    assert summary["count"] == 20
    assert summary["p50"] == 10
    assert summary["max"] == 20
