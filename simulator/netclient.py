"""HTTPS client used by the simulator and the lab probes.

Certificate verification is on. Pass a CA bundle; do not disable verification.
Retries cover timeouts and HTTP 5xx only. A 4xx is final.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import httpx


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def should_retry(status: int | None, timed_out: bool) -> bool:
    if timed_out or status is None:
        return True
    return status >= 500


@dataclass
class Attempt:
    operation: str
    event_id: str
    vehicle_id: str
    attempt: int
    send_ts_utc: str
    response_ts_utc: str
    http_status: int | None
    latency_ms: float | None
    timeout: bool
    error: str
    generated_event_ts_utc: str
    age_ms: int | None = None
    stale: bool | None = None
    duplicate: bool | None = None
    body: dict[str, Any] | None = None

    def csv_row(self, run_id: str, scenario: str) -> dict[str, object]:
        return {
            "run_id": run_id,
            "scenario": scenario,
            "operation": self.operation,
            "event_id": self.event_id,
            "vehicle_id": self.vehicle_id,
            "attempt": self.attempt,
            "send_ts_utc": self.send_ts_utc,
            "response_ts_utc": self.response_ts_utc,
            "http_status": "" if self.http_status is None else self.http_status,
            "latency_ms": "" if self.latency_ms is None else round(self.latency_ms, 3),
            "timeout": self.timeout,
            "error": self.error,
            "generated_event_ts_utc": self.generated_event_ts_utc,
            "age_ms": "" if self.age_ms is None else self.age_ms,
            "stale": "" if self.stale is None else self.stale,
            "duplicate": "" if self.duplicate is None else self.duplicate,
        }


class RetryQueue:
    """Bounded buffer of failed operations. The oldest item is dropped when full."""

    def __init__(self, maxlen: int = 100) -> None:
        self.queue: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self.dropped = 0

    def add(self, item: dict[str, Any]) -> None:
        if self.queue.maxlen is not None and len(self.queue) == self.queue.maxlen:
            self.dropped += 1
            self.queue.popleft()
        self.queue.append(item)

    def drain(self) -> list[dict[str, Any]]:
        items = list(self.queue)
        self.queue.clear()
        return items


def perform(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    operation: str,
    event_id: str = "",
    vehicle_id: str = "",
    attempt: int = 1,
    json_body: dict[str, Any] | None = None,
    timeout: float = 5.0,
    generated_event_ts: datetime | None = None,
    headers: dict[str, str] | None = None,
) -> Attempt:
    send = utc_now()
    started = time.perf_counter()
    status: int | None = None
    error = ""
    timed_out = False
    payload: dict[str, Any] | None = None
    try:
        response = client.request(method, url, json=json_body, timeout=timeout, headers=headers)
        status = response.status_code
        if response.content:
            try:
                parsed = response.json()
            except Exception:
                parsed = None
                error = "non-json response"
            if isinstance(parsed, dict):
                payload = parsed
    except httpx.TimeoutException:
        timed_out = True
        error = "timeout"
    except httpx.HTTPError as exc:
        error = type(exc).__name__
    elapsed = (time.perf_counter() - started) * 1000
    age = payload.get("age_ms") if payload and isinstance(payload.get("age_ms"), int) else None
    stale = payload.get("stale") if payload and isinstance(payload.get("stale"), bool) else None
    duplicate = payload.get("duplicate") if payload and isinstance(payload.get("duplicate"), bool) else None
    generated = generated_event_ts or send
    return Attempt(
        operation=operation,
        event_id=event_id,
        vehicle_id=vehicle_id,
        attempt=attempt,
        send_ts_utc=iso(send),
        response_ts_utc=iso(utc_now()),
        http_status=status,
        latency_ms=elapsed,
        timeout=timed_out,
        error=error,
        generated_event_ts_utc=iso(generated),
        age_ms=age,
        stale=stale,
        duplicate=duplicate,
        body=payload,
    )


def request_with_retries(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    operation: str,
    event_id: str = "",
    vehicle_id: str = "",
    json_body: dict[str, Any] | None = None,
    timeout: float = 5.0,
    generated_event_ts: datetime | None = None,
    max_attempts: int = 3,
    backoff_base: float = 0.05,
    backoff_cap: float = 1.0,
    sleeper: Callable[[float], None] = time.sleep,
    headers: dict[str, str] | None = None,
) -> list[Attempt]:
    attempts: list[Attempt] = []
    for attempt in range(1, max_attempts + 1):
        result = perform(
            client,
            method,
            url,
            operation=operation,
            event_id=event_id,
            vehicle_id=vehicle_id,
            attempt=attempt,
            json_body=json_body,
            timeout=timeout,
            generated_event_ts=generated_event_ts,
            headers=headers,
        )
        attempts.append(result)
        if result.http_status is not None and 200 <= result.http_status < 300:
            return attempts
        if attempt == max_attempts or not should_retry(result.http_status, result.timeout):
            return attempts
        delay = min(backoff_cap, backoff_base * (2 ** (attempt - 1)))
        sleeper(delay)
    return attempts


def open_client(base_url: str, ca_path: str, timeout: float) -> httpx.Client:
    return httpx.Client(base_url=base_url, verify=ca_path, timeout=timeout, trust_env=False)
