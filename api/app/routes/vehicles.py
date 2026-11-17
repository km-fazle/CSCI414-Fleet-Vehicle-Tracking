"""Vehicle registry routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from app.errors import DuplicateVehicle
from app.models import VehicleCreate, VehiclePatch
from app.routes.deps import call_store, settings_of, store_of
from app.serialize import event_view, iso, vehicle_view

router = APIRouter(tags=["vehicles"])


def _last_known(request: Request, vehicle_id: str) -> dict | None:
    store = store_of(request)
    settings = settings_of(request)
    latest = store.latest_event(vehicle_id)
    if latest is None:
        return None
    now = datetime.now(timezone.utc)
    age_ms = int((now - latest["event_time"]).total_seconds() * 1000)
    view = event_view(latest)
    view["age_ms"] = age_ms
    view["stale"] = age_ms > settings.freshness_threshold_ms
    return view


@router.post("/vehicles", status_code=201)
def create_vehicle(payload: VehicleCreate, request: Request) -> dict:
    now = datetime.now(timezone.utc)
    doc = payload.model_dump()
    doc["created_at"] = now
    doc["updated_at"] = now

    def op():
        try:
            return store_of(request).create_vehicle(doc)
        except DuplicateVehicle as exc:
            raise HTTPException(status_code=409, detail="vehicle_id already exists") from exc

    saved = call_store(request, op)
    return vehicle_view(saved, None)


@router.get("/vehicles")
def list_vehicles(request: Request) -> dict:
    vehicles = call_store(request, lambda: store_of(request).list_vehicles())
    items = []
    for vehicle in vehicles:
        last = call_store(request, lambda vehicle_id=vehicle["vehicle_id"]: _last_known(request, vehicle_id))
        items.append(vehicle_view(vehicle, last))
    return {"vehicles": items}


@router.get("/vehicles/{vehicle_id}")
def get_vehicle(vehicle_id: str, request: Request) -> dict:
    vehicle = call_store(request, lambda: store_of(request).get_vehicle(vehicle_id))
    if vehicle is None:
        raise HTTPException(status_code=404, detail="vehicle not found")
    last = call_store(request, lambda: _last_known(request, vehicle_id))
    return vehicle_view(vehicle, last)


@router.patch("/vehicles/{vehicle_id}")
def patch_vehicle(vehicle_id: str, payload: VehiclePatch, request: Request) -> dict:
    patch = payload.model_dump(exclude_unset=True)
    updated = call_store(request, lambda: store_of(request).update_vehicle(vehicle_id, patch))
    if updated is None:
        raise HTTPException(status_code=404, detail="vehicle not found")
    last = call_store(request, lambda: _last_known(request, vehicle_id))
    return vehicle_view(updated, last)


@router.get("/vehicles/{vehicle_id}/latest")
def latest(vehicle_id: str, request: Request) -> dict:
    vehicle = call_store(request, lambda: store_of(request).get_vehicle(vehicle_id))
    if vehicle is None:
        raise HTTPException(status_code=404, detail="vehicle not found")
    settings = settings_of(request)
    doc = call_store(request, lambda: store_of(request).latest_event(vehicle_id))
    if doc is None:
        return {
            "vehicle_id": vehicle_id,
            "latest": None,
            "age_ms": None,
            "stale": True,
            "freshness_threshold_ms": settings.freshness_threshold_ms,
        }
    now = datetime.now(timezone.utc)
    age_ms = int((now - doc["event_time"]).total_seconds() * 1000)
    return {
        "vehicle_id": vehicle_id,
        "latest": event_view(doc),
        "age_ms": age_ms,
        "stale": age_ms > settings.freshness_threshold_ms,
        "freshness_threshold_ms": settings.freshness_threshold_ms,
        "observed_at": iso(now),
    }


@router.get("/vehicles/{vehicle_id}/history")
def history(vehicle_id: str, request: Request, limit: int = 100) -> dict:
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 1000")
    vehicle = call_store(request, lambda: store_of(request).get_vehicle(vehicle_id))
    if vehicle is None:
        raise HTTPException(status_code=404, detail="vehicle not found")
    rows = call_store(request, lambda: store_of(request).history(vehicle_id, limit))
    return {
        "vehicle_id": vehicle_id,
        "order": "event_time,sequence,received_at ascending within the newest window",
        "events": [event_view(row) for row in rows],
    }
