"""Unit tests for the tracking API against the in-memory store."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import MemoryStore
from app.main import create_app


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def client(store: MemoryStore) -> TestClient:
    app = create_app(Settings(freshness_threshold_seconds=10, log_level="WARNING"), store)
    with TestClient(app) as test_client:
        yield test_client


def _vehicle(client: TestClient, vehicle_id: str = "demo-001") -> None:
    response = client.post("/api/v1/vehicles", json={"vehicle_id": vehicle_id, "label": "Vehicle 001"})
    assert response.status_code == 201


def _event(vehicle_id: str = "demo-001", event_id: str = "demo-001-000001", **overrides) -> dict:
    now = datetime.now(timezone.utc)
    body = {
        "event_id": event_id,
        "vehicle_id": vehicle_id,
        "event_time": now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "lat": 40.7545,
        "lon": -73.9808,
        "sequence": 1,
        "simulation_run_id": "test",
        "simulation_seed": 42,
    }
    body.update(overrides)
    return body


def test_create_update_and_read_vehicle(client: TestClient) -> None:
    _vehicle(client)
    duplicate = client.post("/api/v1/vehicles", json={"vehicle_id": "demo-001", "label": "again"})
    assert duplicate.status_code == 409

    patched = client.patch("/api/v1/vehicles/demo-001", json={"label": "Renamed", "metadata": {"color": "blue"}})
    assert patched.status_code == 200
    assert patched.json()["label"] == "Renamed"
    assert patched.json()["metadata"]["color"] == "blue"

    fetched = client.get("/api/v1/vehicles/demo-001")
    assert fetched.status_code == 200
    assert fetched.json()["label"] == "Renamed"
    missing = client.get("/api/v1/vehicles/missing")
    assert missing.status_code == 404
    empty = client.patch("/api/v1/vehicles/demo-001", json={})
    assert empty.status_code == 422


def test_telemetry_history_and_idempotency(client: TestClient, store: MemoryStore) -> None:
    _vehicle(client)
    body = _event()
    first = client.post("/api/v1/telemetry", json=body)
    assert first.status_code == 201
    assert first.json()["duplicate"] is False
    stored = store.events["demo-001-000001"]
    assert stored["location"]["coordinates"] == [-73.9808, 40.7545]

    again = client.post("/api/v1/telemetry", json=body)
    assert again.status_code == 200
    assert again.json()["duplicate"] is True
    assert len(store.events) == 1

    conflict_body = dict(body)
    conflict_body["lat"] = 41.0
    conflict = client.post("/api/v1/telemetry", json=conflict_body)
    assert conflict.status_code == 409
    assert len(store.events) == 1

    history = client.get("/api/v1/vehicles/demo-001/history")
    assert history.status_code == 200
    assert [row["event_id"] for row in history.json()["events"]] == ["demo-001-000001"]


def test_older_event_does_not_replace_latest(client: TestClient) -> None:
    _vehicle(client)
    now = datetime.now(timezone.utc)
    newer = _event(event_id="demo-001-000002", sequence=2, event_time=_stamp(now))
    older = _event(event_id="demo-001-000001", sequence=1, event_time=_stamp(now - timedelta(seconds=5)), lat=40.1)
    assert client.post("/api/v1/telemetry", json=newer).status_code == 201
    assert client.post("/api/v1/telemetry", json=older).status_code == 201
    latest = client.get("/api/v1/vehicles/demo-001/latest")
    assert latest.status_code == 200
    assert latest.json()["latest"]["event_id"] == "demo-001-000002"
    history = client.get("/api/v1/vehicles/demo-001/history")
    assert [row["sequence"] for row in history.json()["events"]] == [1, 2]


def test_freshness_uses_event_time(client: TestClient) -> None:
    _vehicle(client, "demo-fresh")
    _vehicle(client, "demo-old")
    now = datetime.now(timezone.utc)
    assert client.post("/api/v1/telemetry", json=_event(vehicle_id="demo-fresh", event_id="fresh-1", event_time=_stamp(now))).status_code == 201
    assert client.post(
        "/api/v1/telemetry",
        json=_event(vehicle_id="demo-old", event_id="old-1", event_time=_stamp(now - timedelta(seconds=60))),
    ).status_code == 201
    fresh = client.get("/api/v1/vehicles/demo-fresh/latest").json()
    old = client.get("/api/v1/vehicles/demo-old/latest").json()
    assert fresh["stale"] is False
    assert fresh["freshness_threshold_ms"] == 10000
    assert old["stale"] is True
    assert old["age_ms"] >= 59000


def test_validation_and_unknown_vehicle(client: TestClient) -> None:
    _vehicle(client)
    bad_lat = client.post("/api/v1/telemetry", json=_event(lat=91))
    assert bad_lat.status_code == 422
    naive = client.post("/api/v1/telemetry", json=_event(event_time="2026-11-13T16:00:00"))
    assert naive.status_code == 422
    missing = client.post("/api/v1/telemetry", json=_event(vehicle_id="nope", event_id="nope-1"))
    assert missing.status_code == 404
    assert client.get("/api/v1/vehicles/demo-001/history?limit=0").status_code == 422


def test_health_and_database_outage(client: TestClient, store: MemoryStore) -> None:
    assert client.get("/health/live").status_code == 200
    assert client.get("/api/v1/health/ready").status_code == 200
    _vehicle(client)
    store.available = False
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 503
    failed = client.post("/api/v1/telemetry", json=_event(event_id="not-stored"))
    assert failed.status_code == 503
    assert "mongodb://" not in failed.text
    store.available = True
    assert "not-stored" not in store.events


def test_request_id_header(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "req-123"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-123"


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
