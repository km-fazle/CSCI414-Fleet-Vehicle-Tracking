"""FastAPI application factory."""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app import __version__
from app.config import Settings
from app.db import MongoStore
from app.errors import DatabaseUnavailable
from app.observability import configure_logging
from app.routes import health, runs, telemetry, vehicles

log = logging.getLogger("fleettrace.access")


def create_app(settings: Settings | None = None, store=None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)
    if store is None:
        store = MongoStore(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            app.state.store.ensure_indexes()
        except DatabaseUnavailable as exc:
            logging.getLogger("fleettrace").warning(
                "index setup deferred",
                extra={"exc_type": exc.cause},
            )
        yield
        app.state.store.close()

    app = FastAPI(
        title="FleetTrace Lab",
        version=__version__,
        summary="Simulated fleet location tracking for a segmented Linux lab",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.store = store

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            log.error(
                "unhandled request error",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "route": request.url.path,
                    "exc_type": type(exc).__name__,
                },
            )
            raise
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        response.headers["X-Request-ID"] = request_id
        log.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "route": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    app.include_router(health.router)
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(vehicles.router, prefix="/api/v1")
    app.include_router(telemetry.router, prefix="/api/v1")
    app.include_router(runs.router, prefix="/api/v1")
    return app
