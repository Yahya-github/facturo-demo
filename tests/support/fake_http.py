"""Tiny local HTTP servers for exercising updater.py without any network access.

Every test that needs a "GitHub" or "storage" endpoint spins one of these up on
127.0.0.1:0 (an OS-assigned free port) in a background thread. Nothing here ever
talks to the real internet — see the ground rules in changes/team-d.md.
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

Route = Callable[["_Handler"], None]


class _Handler(BaseHTTPRequestHandler):
    routes: dict[str, Route] = {}
    received: list[dict] = []

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - silence default access log
        pass

    def _dispatch(self) -> None:
        self.received.append({
            "method": self.command,
            "path": self.path,
            "headers": dict(self.headers.items()),
        })
        route = self.routes.get(self.path)
        if route is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        route(self)

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        self._dispatch()

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib naming
        self._dispatch()


def make_server(routes: dict[str, Route]) -> tuple[ThreadingHTTPServer, list[dict]]:
    """A stopped-but-bound server: `.server_port` is already known.

    Returns (server, received) — `received` fills up with one dict per request
    (method, path, headers) as soon as the server is actually serving (see
    `running()`), so tests can assert on what was sent without the route
    functions having to do their own bookkeeping.
    """
    received: list[dict] = []
    handler_cls = type("_TestHandler", (_Handler,), {"routes": dict(routes), "received": received})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    return server, received


@contextmanager
def running(server: ThreadingHTTPServer):
    """Serve `server` in a daemon thread for the life of the `with` block."""
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def json_response(handler: _Handler, status: int, payload) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler: _Handler, status: int, text: str) -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def bytes_response(handler: _Handler, status: int, data: bytes,
                    content_type: str = "application/octet-stream") -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def redirect_response(handler: _Handler, location: str) -> None:
    handler.send_response(302)
    handler.send_header("Location", location)
    handler.send_header("Content-Length", "0")
    handler.end_headers()
