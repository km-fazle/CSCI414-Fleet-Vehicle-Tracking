"""Process liveness is independent of MongoDB readiness."""

from fastapi import APIRouter, HTTPException, Request

from app.routes.deps import store_of

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "live"}


@router.get("/health/ready")
def ready(request: Request) -> dict[str, str]:
    store = store_of(request)
    try:
        ok = store.ping()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"message": "database unavailable", "cause": type(exc).__name__},
        ) from exc
    if not ok:
        raise HTTPException(
            status_code=503,
            detail={"message": "database unavailable", "cause": "ping failed"},
        )
    return {"status": "ready"}
