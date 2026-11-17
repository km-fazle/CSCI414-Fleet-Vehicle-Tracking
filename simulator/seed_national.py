"""Add one synthetic vehicle on a real street in each stored US city.

Existing lab vehicles are left alone. Running this again replaces only the
`us-streets` run.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fleetgen import national_routes, positions_on_route

RUN_ID = "us-streets"
EVENTS = 40


def vehicle_id_for(city: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in city).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return f"us-{slug}"


def main() -> None:
    uri = os.environ.get("MONGODB_URI", "mongodb://10.30.30.10:27017")
    database = os.environ.get("MONGODB_DB", "fleettrace")
    db = MongoClient(uri, serverSelectionTimeoutMS=4000)[database]
    routes = national_routes()
    ids = [vehicle_id_for(route["name"]) for route in routes]
    db.location_events.delete_many({"simulation_run_id": RUN_ID})
    db.vehicles.delete_many({"vehicle_id": {"$in": ids}})

    now = datetime.now(timezone.utc)
    vehicles = []
    events = []
    for route in routes:
        city = route["name"]
        vehicle_id = vehicle_id_for(city)
        vehicles.append({
            "vehicle_id": vehicle_id,
            "label": city,
            "type": "simulated",
            "active": True,
            "metadata": {"city": city, "country": "US"},
            "created_at": now,
            "updated_at": now,
        })
        spots = positions_on_route(city, EVENTS, start_m=80)
        for sequence, (lat, lon) in enumerate(spots, start=1):
            lat = round(lat, 7)
            lon = round(lon, 7)
            event_time = now - timedelta(seconds=(EVENTS - sequence) * 2)
            events.append({
                "event_id": f"{vehicle_id}-{sequence:04d}",
                "vehicle_id": vehicle_id,
                "simulation_run_id": RUN_ID,
                "sequence": sequence,
                "event_time": event_time,
                "received_at": event_time + timedelta(milliseconds=80),
                "location": {"type": "Point", "coordinates": [lon, lat]},
                "lat": lat,
                "lon": lon,
                "source_type": "synthetic",
                "source_record_id": None,
                "generation_method": "street_trace",
                "simulation_seed": 42,
            })
    if vehicles:
        db.vehicles.insert_many(vehicles)
        db.location_events.insert_many(events)
    print(f"stored {len(vehicles)} vehicles and {len(events)} street positions")


if __name__ == "__main__":
    main()
