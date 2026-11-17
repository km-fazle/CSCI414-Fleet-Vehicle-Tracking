"""Simulation run metadata stored beside location events."""

from fastapi import APIRouter, Request

from app.models import SimulationRunIn
from app.routes.deps import call_store, store_of
from app.serialize import iso

router = APIRouter(tags=["runs"])


@router.post("/simulation-runs", status_code=201)
def save_run(payload: SimulationRunIn, request: Request) -> dict:
    doc = payload.model_dump()
    kind, saved = call_store(request, lambda: store_of(request).save_run(doc))
    for key in ("started_at", "finished_at"):
        if saved.get(key) is not None:
            saved[key] = iso(saved[key])
    saved.pop("_id", None)
    return {"result": kind, "run": saved}
