"""Serve the dispatch board on port 8787 inside the lab container."""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from collect import build_board

STATIC = Path(__file__).resolve().parent / "static"
CACHE_SECONDS = 1.0
_lock = threading.Lock()
_cache = {"at": 0.0, "body": None}


def board() -> dict:
    now = time.monotonic()
    with _lock:
        if _cache["body"] is not None and now - _cache["at"] < CACHE_SECONDS:
            return _cache["body"]
        body = build_board()
        _cache["at"] = time.monotonic()
        _cache["body"] = body
        return body


class Handler(BaseHTTPRequestHandler):
    server_version = "FleetTraceDispatch"

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path == "/api/board":
            self._json(board())
            return
        if path in ("/", "/index.html"):
            self._file(STATIC / "index.html")
            return
        if path.startswith("/static/"):
            target = (STATIC / path.removeprefix("/static/")).resolve()
            if target.is_file() and STATIC.resolve() in target.parents:
                self._file(target)
                return
        self.send_error(404)

    def _json(self, payload: dict) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _file(self, path: Path) -> None:
        raw = path.read_bytes()
        kind = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".txt": "text/plain; charset=utf-8",
        }.get(path.suffix, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args) -> None:
        if args and str(args[0]).startswith("GET /api/board"):
            return
        super().log_message(fmt, *args)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"dispatch listening on {args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
