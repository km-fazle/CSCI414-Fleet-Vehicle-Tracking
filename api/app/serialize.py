"""JSON shapes shared by the HTTP routes."""

from datetime import datetime, timezone
from typing import Any


def iso(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    millis = utc.microsecond // 1000
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{millis:03d}Z"


def event_view(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": doc["event_id"],
        "vehicle_id": doc["vehicle_id"],
        "sequence": doc["sequence"],
        "event_time": iso(doc["event_time"]),
        "received_at": iso(doc["received_at"]),
        "lat": doc["lat"],
        "lon": doc["lon"],
        "simulation_run_id": doc.get("simulation_run_id"),
        "source_type": doc.get("source_type"),
        "source_record_id": doc.get("source_record_id"),
        "generation_method": doc.get("generation_method"),
        "simulation_seed": doc.get("simulation_seed"),
    }


def vehicle_view(doc: dict[str, Any], last: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "vehicle_id": doc["vehicle_id"],
        "label": doc["label"],
        "type": doc.get("type", "simulated"),
        "active": doc.get("active", True),
        "metadata": doc.get("metadata") or {},
        "created_at": iso(doc["created_at"]),
        "updated_at": iso(doc["updated_at"]),
        "last_known": last,
    }
