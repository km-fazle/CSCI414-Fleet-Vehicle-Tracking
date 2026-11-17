"""Shared route helpers."""

import logging

from fastapi import HTTPException, Request

from app.config import Settings
from app.errors import DatabaseUnavailable

log = logging.getLogger("fleettrace.api")


def store_of(request: Request):
    return request.app.state.store


def settings_of(request: Request) -> Settings:
    return request.app.state.settings


def call_store(request: Request, fn):
    try:
        return fn()
    except DatabaseUnavailable as exc:
        log.warning(
            "database unavailable",
            extra={
                "exc_type": exc.cause,
                "route": request.url.path,
                "request_id": getattr(request.state, "request_id", None),
            },
        )
        raise HTTPException(
            status_code=503,
            detail={"message": "database unavailable", "cause": exc.cause},
        ) from exc
