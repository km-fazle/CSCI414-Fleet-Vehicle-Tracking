"""Read the API from inside the client namespace. Prints one JSON object."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import httpx

API = "https://10.20.20.10:8443"
CA = "/work/network/tls/certs/ca.crt"


def grab(client: httpx.Client, path: str) -> dict:
    started = time.perf_counter()
    response = client.get(path)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text[:300]}
    return {"status_code": response.status_code, "elapsed_ms": elapsed_ms, "body": body}


def main() -> None:
    try:
        with httpx.Client(verify=CA, timeout=4.0, trust_env=False) as client:
            live = grab(client, API + "/health/live")
            ready = grab(client, API + "/health/ready")
            vehicles = grab(client, API + "/api/v1/vehicles")
            tracks: dict[str, list] = {}
            rows = vehicles["body"].get("vehicles", []) if isinstance(vehicles["body"], dict) else []
            if vehicles["status_code"] == 200:
                ids = [vehicle.get("vehicle_id") for vehicle in rows if vehicle.get("vehicle_id")]

                def history_for(vehicle_id: str) -> tuple[str, list]:
                    history = grab(client, API + "/api/v1/vehicles/" + quote(vehicle_id, safe="") + "/history?limit=80")
                    events = history["body"].get("events") or [] if history["status_code"] == 200 and isinstance(history["body"], dict) else []
                    return vehicle_id, events

                with ThreadPoolExecutor(max_workers=8) as pool:
                    for vehicle_id, events in pool.map(history_for, ids):
                        tracks[vehicle_id] = events
        print(json.dumps({
            "ok": vehicles["status_code"] == 200,
            "live": live,
            "ready": ready,
            "warm_ms": vehicles["elapsed_ms"],
            "vehicles": rows if vehicles["status_code"] == 200 else [],
            "tracks": tracks,
            "error": None if vehicles["status_code"] == 200 else f"vehicle list returned {vehicles['status_code']}",
        }))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"[:400]}))


if __name__ == "__main__":
    main()
