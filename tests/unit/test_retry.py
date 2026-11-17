"""Retry policy tests. They do not open a socket."""

import httpx

from netclient import RetryQueue, request_with_retries, should_retry


def test_should_retry_only_timeouts_and_server_errors() -> None:
    assert should_retry(503, False) is True
    assert should_retry(None, True) is True
    assert should_retry(None, False) is True
    assert should_retry(422, False) is False
    assert should_retry(404, False) is False
    assert should_retry(201, False) is False


class _Stub:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)

    def request(self, method, url, json=None, timeout=None, headers=None):
        item = self.outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_retries_then_succeeds_without_sleeping_on_success() -> None:
    slept = []
    client = _Stub(
        [
            httpx.Response(503, json={"detail": "down"}),
            httpx.Response(201, json={"duplicate": False, "event_id": "e1"}),
        ]
    )
    attempts = request_with_retries(
        client,
        "POST",
        "/api/v1/telemetry",
        operation="post_telemetry",
        event_id="e1",
        max_attempts=3,
        sleeper=slept.append,
    )
    assert [item.http_status for item in attempts] == [503, 201]
    assert len(slept) == 1
    assert attempts[-1].duplicate is False


def test_client_error_is_not_retried() -> None:
    slept = []
    client = _Stub([httpx.Response(422, json={"detail": "bad"})])
    attempts = request_with_retries(
        client,
        "POST",
        "/api/v1/telemetry",
        operation="post_telemetry",
        max_attempts=3,
        sleeper=slept.append,
    )
    assert len(attempts) == 1
    assert slept == []


def test_retry_queue_drops_the_oldest_item() -> None:
    queue = RetryQueue(maxlen=2)
    queue.add({"event_id": "a"})
    queue.add({"event_id": "b"})
    queue.add({"event_id": "c"})
    assert queue.dropped == 1
    assert [item["event_id"] for item in queue.drain()] == ["b", "c"]
