"""MongoDB integration. Skipped unless the lab script starts mongod and opts in."""

import os
from datetime import datetime, timezone

import pytest

from app.config import Settings
from app.db import MongoStore


pytestmark = pytest.mark.skipif(
    os.environ.get("FLEETTRACE_INTEGRATION") != "1",
    reason="set FLEETTRACE_INTEGRATION=1 and MONGODB_URI to run against MongoDB",
)


@pytest.fixture
def store() -> MongoStore:
    settings = Settings(
        mongodb_uri=os.environ.get("MONGODB_URI", "mongodb://10.30.30.10:27017"),
        mongodb_db="fleettrace_itest",
        mongo_timeout_ms=3000,
    )
    opened = MongoStore(settings)
    opened.drop_database()
    opened.ensure_indexes()
    try:
        yield opened
    finally:
        opened.drop_database()
        opened.close()


def test_records_survive_a_new_client(store: MongoStore) -> None:
    now = datetime.now(timezone.utc)
    store.create_vehicle(
        {
            "vehicle_id": "itest-001",
            "label": "Integration",
            "type": "simulated",
            "active": True,
            "metadata": {},
            "created_at": now,
            "updated_at": now,
        }
    )
    kind, saved = store.insert_event(
        {
            "event_id": "itest-001-000001",
            "vehicle_id": "itest-001",
            "simulation_run_id": "itest",
            "sequence": 1,
            "event_time": now,
            "location": {"type": "Point", "coordinates": [-73.98, 40.75]},
            "lat": 40.75,
            "lon": -73.98,
            "source_type": "synthetic",
            "generation_method": "deterministic_linear_track",
            "simulation_seed": 42,
        }
    )
    assert kind == "created"
    again = MongoStore(store.settings)
    try:
        latest = again.latest_event("itest-001")
        assert latest is not None
        assert latest["event_id"] == saved["event_id"]
        duplicate, _ = again.insert_event(
            {
                "event_id": "itest-001-000001",
                "vehicle_id": "itest-001",
                "simulation_run_id": "itest",
                "sequence": 1,
                "event_time": now,
                "lat": 40.75,
                "lon": -73.98,
                "source_type": "synthetic",
                "generation_method": "deterministic_linear_track",
                "simulation_seed": 42,
            }
        )
        assert duplicate == "duplicate"
        assert again.db.location_events.count_documents({"event_id": "itest-001-000001"}) == 1
    finally:
        again.close()
