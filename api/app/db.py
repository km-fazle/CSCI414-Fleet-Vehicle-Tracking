"""Vehicle and location persistence.

Latest-position order is event_time descending, then sequence descending,
then received_at descending. A late-arriving older event does not replace a
newer one. GeoJSON coordinates are [longitude, latitude].
"""

from __future__ import annotations

import copy
import threading
from datetime import datetime, timezone
from typing import Any

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.config import Settings
from app.errors import DatabaseUnavailable, DuplicateVehicle


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def same_event_payload(existing: dict[str, Any], incoming: dict[str, Any]) -> bool:
    if existing.get("vehicle_id") != incoming.get("vehicle_id"):
        return False
    if existing.get("sequence") != incoming.get("sequence"):
        return False
    if existing.get("simulation_run_id") != incoming.get("simulation_run_id"):
        return False
    if abs(float(existing["lat"]) - float(incoming["lat"])) > 1e-7:
        return False
    if abs(float(existing["lon"]) - float(incoming["lon"])) > 1e-7:
        return False
    delta = abs((_as_utc(existing["event_time"]) - _as_utc(incoming["event_time"])).total_seconds())
    return delta <= 0.001


def _public(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    copied = dict(doc)
    copied.pop("_id", None)
    return copied


class MemoryStore:
    """In-memory store used by unit tests. It follows the same ordering rules."""

    def __init__(self) -> None:
        self.available = True
        self.vehicles: dict[str, dict[str, Any]] = {}
        self.events: dict[str, dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def close(self) -> None:
        return None

    def ping(self) -> bool:
        return self.available

    def ensure_indexes(self) -> None:
        return None

    def _check(self) -> None:
        if not self.available:
            raise DatabaseUnavailable("unavailable")

    def create_vehicle(self, doc: dict[str, Any]) -> dict[str, Any]:
        self._check()
        with self._lock:
            if doc["vehicle_id"] in self.vehicles:
                raise DuplicateVehicle(doc["vehicle_id"])
            stored = copy.deepcopy(doc)
            self.vehicles[stored["vehicle_id"]] = stored
            return copy.deepcopy(stored)

    def get_vehicle(self, vehicle_id: str) -> dict[str, Any] | None:
        self._check()
        with self._lock:
            doc = self.vehicles.get(vehicle_id)
            return copy.deepcopy(doc) if doc else None

    def list_vehicles(self) -> list[dict[str, Any]]:
        self._check()
        with self._lock:
            return [copy.deepcopy(self.vehicles[key]) for key in sorted(self.vehicles)]

    def update_vehicle(self, vehicle_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        self._check()
        with self._lock:
            current = self.vehicles.get(vehicle_id)
            if current is None:
                return None
            for key, value in patch.items():
                if value is not None:
                    current[key] = copy.deepcopy(value)
            current["updated_at"] = datetime.now(timezone.utc)
            return copy.deepcopy(current)

    def insert_event(self, doc: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        self._check()
        with self._lock:
            existing = self.events.get(doc["event_id"])
            if existing is not None:
                kind = "duplicate" if same_event_payload(existing, doc) else "conflict"
                return kind, copy.deepcopy(existing)
            stored = copy.deepcopy(doc)
            stored["received_at"] = datetime.now(timezone.utc)
            self.events[stored["event_id"]] = stored
            return "created", copy.deepcopy(stored)

    def latest_event(self, vehicle_id: str) -> dict[str, Any] | None:
        self._check()
        with self._lock:
            rows = [doc for doc in self.events.values() if doc["vehicle_id"] == vehicle_id]
        if not rows:
            return None
        rows.sort(key=lambda doc: (_as_utc(doc["event_time"]), doc["sequence"], _as_utc(doc["received_at"])))
        return copy.deepcopy(rows[-1])

    def history(self, vehicle_id: str, limit: int) -> list[dict[str, Any]]:
        self._check()
        with self._lock:
            rows = [doc for doc in self.events.values() if doc["vehicle_id"] == vehicle_id]
        rows.sort(key=lambda doc: (_as_utc(doc["event_time"]), doc["sequence"], _as_utc(doc["received_at"])), reverse=True)
        chosen = list(reversed(rows[:limit]))
        return [copy.deepcopy(doc) for doc in chosen]

    def save_run(self, doc: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        self._check()
        with self._lock:
            existing = self.runs.get(doc["run_id"])
            stored = copy.deepcopy(doc)
            if existing is None:
                self.runs[stored["run_id"]] = stored
                return "created", copy.deepcopy(stored)
            existing.update(stored)
            return "updated", copy.deepcopy(existing)


class MongoStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = MongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=settings.mongo_timeout_ms,
            connectTimeoutMS=settings.mongo_timeout_ms,
            tz_aware=True,
            tzinfo=timezone.utc,
        )
        self.db = self.client[settings.mongodb_db]

    def close(self) -> None:
        self.client.close()

    def _guard(self, fn: Any) -> Any:
        try:
            return fn()
        except DuplicateVehicle:
            raise
        except PyMongoError as exc:
            raise DatabaseUnavailable(type(exc).__name__) from exc

    def ping(self) -> bool:
        try:
            self.client.admin.command("ping")
            return True
        except PyMongoError:
            return False

    def ensure_indexes(self) -> None:
        def op() -> None:
            self.db.vehicles.create_index("vehicle_id", unique=True)
            self.db.location_events.create_index("event_id", unique=True)
            self.db.location_events.create_index(
                [("vehicle_id", 1), ("event_time", -1), ("sequence", -1)]
            )
            self.db.location_events.create_index("simulation_run_id")
            self.db.simulation_runs.create_index("run_id", unique=True)

        self._guard(op)

    def drop_database(self) -> None:
        name = self.settings.mongodb_db
        if name in {"admin", "local", "config", "fleettrace"} or not name.endswith("_itest"):
            raise RuntimeError(f"refusing to drop database {name}")
        self.client.drop_database(name)

    def create_vehicle(self, doc: dict[str, Any]) -> dict[str, Any]:
        def op() -> dict[str, Any]:
            try:
                self.db.vehicles.insert_one(dict(doc))
            except DuplicateKeyError as exc:
                raise DuplicateVehicle(doc["vehicle_id"]) from exc
            return dict(doc)

        return self._guard(op)

    def get_vehicle(self, vehicle_id: str) -> dict[str, Any] | None:
        return self._guard(lambda: _public(self.db.vehicles.find_one({"vehicle_id": vehicle_id})))

    def list_vehicles(self) -> list[dict[str, Any]]:
        def op() -> list[dict[str, Any]]:
            rows = self.db.vehicles.find().sort("vehicle_id", 1)
            return [row for row in (_public(doc) for doc in rows) if row is not None]

        return self._guard(op)

    def update_vehicle(self, vehicle_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        def op() -> dict[str, Any] | None:
            changes = {key: value for key, value in patch.items() if value is not None}
            changes["updated_at"] = datetime.now(timezone.utc)
            result = self.db.vehicles.find_one_and_update(
                {"vehicle_id": vehicle_id},
                {"$set": changes},
            )
            if result is None:
                return None
            return _public(self.db.vehicles.find_one({"vehicle_id": vehicle_id}))

        return self._guard(op)

    def insert_event(self, doc: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        def op() -> tuple[str, dict[str, Any]]:
            stored = dict(doc)
            stored["received_at"] = datetime.now(timezone.utc)
            try:
                self.db.location_events.insert_one(stored)
            except DuplicateKeyError:
                existing = _public(self.db.location_events.find_one({"event_id": doc["event_id"]}))
                if existing is None:
                    raise DatabaseUnavailable("duplicate without existing document")
                kind = "duplicate" if same_event_payload(existing, doc) else "conflict"
                return kind, existing
            stored.pop("_id", None)
            return "created", stored

        return self._guard(op)

    def latest_event(self, vehicle_id: str) -> dict[str, Any] | None:
        def op() -> dict[str, Any] | None:
            doc = self.db.location_events.find_one(
                {"vehicle_id": vehicle_id},
                sort=[("event_time", -1), ("sequence", -1), ("received_at", -1)],
            )
            return _public(doc)

        return self._guard(op)

    def history(self, vehicle_id: str, limit: int) -> list[dict[str, Any]]:
        def op() -> list[dict[str, Any]]:
            cursor = (
                self.db.location_events.find({"vehicle_id": vehicle_id})
                .sort([("event_time", -1), ("sequence", -1), ("received_at", -1)])
                .limit(limit)
            )
            rows = [row for row in (_public(doc) for doc in cursor) if row is not None]
            rows.reverse()
            return rows

        return self._guard(op)

    def save_run(self, doc: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        def op() -> tuple[str, dict[str, Any]]:
            result = self.db.simulation_runs.update_one(
                {"run_id": doc["run_id"]},
                {"$set": dict(doc)},
                upsert=True,
            )
            saved = _public(self.db.simulation_runs.find_one({"run_id": doc["run_id"]}))
            if saved is None:
                raise DatabaseUnavailable("run was not stored")
            kind = "created" if result.upserted_id is not None else "updated"
            return kind, saved

        return self._guard(op)
