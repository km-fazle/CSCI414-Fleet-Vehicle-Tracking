"""Telemetry ingest. Duplicate event IDs are not written twice."""

import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.models import TelemetryIn
from app.routes.deps import call_store, store_of
from app.serialize import event_view, iso

router = APIRouter(tags=["telemetry"])


@router.post("/telemetry")
def create_telemetry(payload: TelemetryIn, request: Request) -> JSONResponse:
    store = store_of(request)
    vehicle = call_store(request, lambda: store.get_vehicle(payload.vehicle_id))
    if vehicle is None:
        raise HTTPException(status_code=404, detail="vehicle not found")

    body = payload.model_dump()
    doc = {
        "event_id": body["event_id"],
        "vehicle_id": body["vehicle_id"],
        "simulation_run_id": body.get("simulation_run_id"),
        "sequence": body["sequence"],
        "event_time": body["event_time"],
        "location": {"type": "Point", "coordinates": [body["lon"], body["lat"]]},
        "lat": body["lat"],
        "lon": body["lon"],
        "source_type": body["source_type"],
        "source_record_id": body.get("source_record_id"),
        "generation_method": body["generation_method"],
        "simulation_seed": body.get("simulation_seed"),
    }
    started = time.perf_counter()
    kind, saved = call_store(request, lambda: store.insert_event(doc))
    ingest_ms = round((time.perf_counter() - started) * 1000, 3)
    if kind == "conflict":
        raise HTTPException(status_code=409, detail="event_id already exists with a different payload")

    content = {
        "event_id": saved["event_id"],
        "received_at": iso(saved["received_at"]),
        "ingest_latency_ms": ingest_ms,
        "duplicate": kind == "duplicate",
        "event": event_view(saved),
    }
    status = 200 if kind == "duplicate" else 201
    return JSONResponse(status_code=status, content=content)
