"""Move stored positions onto the avenue traces. Event times stay as they are."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pymongo import MongoClient, UpdateOne

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fleetgen import street_positions


def main() -> None:
    uri = os.environ.get("MONGODB_URI", "mongodb://10.30.30.10:27017")
    database = os.environ.get("MONGODB_DB", "fleettrace")
    collection = MongoClient(uri, serverSelectionTimeoutMS=4000)[database].location_events
    updates = []
    for vehicle_id in collection.distinct("vehicle_id"):
        rows = list(collection.find({"vehicle_id": vehicle_id}).sort([
            ("event_time", 1),
            ("sequence", 1),
            ("_id", 1),
        ]))
        spots = street_positions(vehicle_id, len(rows), 42)
        for row, (lat, lon) in zip(rows, spots):
            lat = round(lat, 7)
            lon = round(lon, 7)
            updates.append(UpdateOne(
                {"_id": row["_id"]},
                {"$set": {
                    "lat": lat,
                    "lon": lon,
                    "location": {"type": "Point", "coordinates": [lon, lat]},
                }},
            ))
    if not updates:
        print("no events")
        return
    result = collection.bulk_write(updates, ordered=False)
    print(f"updated {result.modified_count} of {len(updates)} events")


if __name__ == "__main__":
    main()
