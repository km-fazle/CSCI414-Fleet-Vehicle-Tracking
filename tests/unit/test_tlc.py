"""Derived TLC events stay labeled as synthetic interpolation."""

from tlc import convert_rows, load_zone_lookup


def test_coordinate_rows_mark_intermediate_points_as_derived(tmp_path) -> None:
    rows = [
        {
            "record_id": "trip-1",
            "pickup_latitude": "40.70",
            "pickup_longitude": "-74.00",
            "dropoff_latitude": "40.80",
            "dropoff_longitude": "-73.90",
        }
    ]
    events = convert_rows(rows, zones=None, intermediates=2, seed=42, vehicle_id="tlc-derived-001")
    assert len(events) == 4
    assert events[0]["generation_method"] == "trip_endpoint"
    assert events[1]["generation_method"] != "trip_endpoint"
    assert events[-1]["lat"] == 40.8
    assert {event["source_type"] for event in events} == {"nyc_tlc_derived"}
    assert all("Not a continuous GPS trace" in event["note"] for event in events)


def test_zone_lookup_file(tmp_path) -> None:
    path = tmp_path / "zones.json"
    path.write_text(
        '{"zones": {"1": {"lat": 40.7, "lon": -74.0}, "2": {"lat": 40.8, "lon": -73.9}}}',
        encoding="utf-8",
    )
    zones = load_zone_lookup(path)
    events = convert_rows(
        [{"record_id": "z", "PULocationID": "1", "DOLocationID": "2"}],
        zones=zones,
        intermediates=1,
        seed=1,
        vehicle_id="tlc-derived-001",
    )
    assert len(events) == 3
    assert events[1]["generation_method"] == "linear_interpolation_between_zone_centroids"
