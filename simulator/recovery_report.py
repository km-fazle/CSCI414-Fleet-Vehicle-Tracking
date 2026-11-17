"""Build the recovery timeline from probe JSON files. No guessed durations."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def millis(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() * 1000)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--detected", required=True)
    parser.add_argument("--failed-post", required=True)
    parser.add_argument("--ready", required=True)
    parser.add_argument("--success-post", required=True)
    parser.add_argument("--success-get", required=True)
    parser.add_argument("--retry-post", required=True)
    parser.add_argument("--restart-invoked", required=True)
    parser.add_argument("--hold-seconds", type=float, required=True)
    args = parser.parse_args()

    detected = load(args.detected)
    failed = load(args.failed_post)
    ready = load(args.ready)
    success = load(args.success_post)
    follow = load(args.success_get)
    retried = load(args.retry_post)
    restart_at = parse_time(Path(args.restart_invoked).read_text(encoding="utf-8").strip())
    detected_at = parse_time(detected["response_ts_utc"])
    ready_at = parse_time(ready["response_ts_utc"])
    success_at = parse_time(success["response_ts_utc"])

    problems = []
    if detected.get("ok"):
        problems.append("health check succeeded while the API was supposed to be down")
    if failed.get("ok"):
        problems.append("telemetry post succeeded while the API was supposed to be down")
    if not ready.get("ok"):
        problems.append("readiness did not recover")
    if not success.get("ok"):
        problems.append("post-recovery telemetry post failed")
    if not follow.get("ok"):
        problems.append("post-recovery read failed")
    event_id = (success.get("body") or {}).get("event_id")
    latest_id = ((follow.get("body") or {}).get("latest") or {}).get("event_id")
    if event_id and latest_id and event_id != latest_id:
        problems.append("latest event does not match the post-recovery write")

    timeline = {
        "hold_seconds": args.hold_seconds,
        "detected_down_at": detected["response_ts_utc"],
        "failed_post_during_outage": {
            "http_status": failed.get("http_status"),
            "error": failed.get("error"),
            "event_id": failed.get("event_id"),
            "response_ts_utc": failed.get("response_ts_utc"),
        },
        "restart_invoked_at": restart_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "ready_at": ready["response_ts_utc"],
        "successful_write_at": success["response_ts_utc"],
        "recovery_duration_ms": millis(detected_at, success_at),
        "restart_to_ready_ms": millis(restart_at, ready_at),
        "restart_to_successful_write_ms": millis(restart_at, success_at),
        "post_recovery_event_id": event_id,
        "retry_after_recovery": {
            "event_id": retried.get("event_id"),
            "http_status": retried.get("http_status"),
            "duplicate": (retried.get("body") or {}).get("duplicate"),
            "ok": retried.get("ok"),
        },
        "definition": "recovery_duration_ms is the detected-down response time to the first successful post. It includes the intentional hold, not only process restart time.",
        "problems": problems,
    }
    Path(args.out).write_text(json.dumps(timeline, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(timeline, indent=2))
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
