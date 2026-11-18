"""Tiny stdlib HTTP server for the agent twin UI.

    GET /             → twin/static/index.html
    GET /api/state    → sources.snapshot() as JSON  (?hours=24)
    GET /api/health   → {"ok": true}
"""

from __future__ import annotations

import json
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from twin import sources

INDEX = Path(__file__).resolve().parent / "static" / "index.html"


class TwinHandler(BaseHTTPRequestHandler):
    def __init__(self, *args: Any, options: dict, **kwargs: Any) -> None:
        self.options = options
        super().__init__(*args, **kwargs)

    def log_message(self, fmt: str, *args: Any) -> None:  # keep the terminal quiet
        pass

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: Any, code: int = 200) -> None:
        self._send(code, json.dumps(payload).encode(), "application/json")

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/state":
            try:
                hours = max(1, min(168, int(parse_qs(url.query).get("hours", ["24"])[0])))
            except ValueError:
                hours = 24
            self._json(sources.snapshot(
                self.options["root"],
                copilot_dir=self.options["copilot_dir"],
                copilot_match=self.options["copilot_match"],
                copilot_limit=self.options["copilot_limit"],
                hours=hours,
            ))
        elif url.path == "/api/health":
            self._json({"ok": True})
        else:
            self._json({"error": "not found"}, 404)


def serve(host: str = "127.0.0.1", port: int = 8787, *, root: Path = sources.REPO_ROOT,
          copilot_dir: Path = sources.COPILOT_STATE_DIR, copilot_match: Optional[str] = None,
          copilot_limit: int = 12) -> ThreadingHTTPServer:
    options = {"root": root, "copilot_dir": copilot_dir,
               "copilot_match": copilot_match, "copilot_limit": copilot_limit}
    return ThreadingHTTPServer((host, port), partial(TwinHandler, options=options))
