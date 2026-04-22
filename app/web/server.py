from __future__ import annotations

import argparse
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from .controller import (
    InvalidActionError,
    InvalidSessionStateError,
    SessionNotFoundError,
    SessionRegistry,
)


class SessionApiServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], registry: Optional[SessionRegistry] = None):
        super().__init__(server_address, SessionApiHandler)
        self.registry = registry or SessionRegistry()


class SessionApiHandler(BaseHTTPRequestHandler):
    server: SessionApiServer

    def do_OPTIONS(self) -> None:  # pragma: no cover - trivial CORS path
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_common_headers()
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        status, payload = dispatch_request(self.server.registry, "GET", path)
        self._write_json(status, payload)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        status, payload = dispatch_request(
            self.server.registry,
            "POST",
            path,
            payload=self._read_json_body(),
        )
        self._write_json(status, payload)

    def log_message(self, format: str, *args: Any) -> None:  # pragma: no cover - quiet local API
        return

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        payload = self.rfile.read(length)
        if not payload:
            return {}
        return json.loads(payload.decode("utf-8"))

    def _write_json(self, status: HTTPStatus, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._send_common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_common_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def dispatch_request(
    registry: SessionRegistry,
    method: str,
    path: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
) -> tuple[HTTPStatus, Dict[str, Any]]:
    if method == "GET" and path == "/health":
        return HTTPStatus.OK, {"ok": True}

    if method == "POST" and path == "/api/session":
        session_id, controller = registry.create()
        return HTTPStatus.CREATED, controller.snapshot(session_id)

    if method == "GET" and path.startswith("/api/session/"):
        session_id = path.rsplit("/", 1)[-1]
        try:
            controller = registry.get(session_id)
            return HTTPStatus.OK, controller.snapshot(session_id)
        except SessionNotFoundError as exc:
            return HTTPStatus.NOT_FOUND, {"error": str(exc)}

    if method == "POST" and path.endswith("/action") and path.startswith("/api/session/"):
        session_id = path.split("/")[3]
        action = (payload or {}).get("action")
        if not isinstance(action, dict):
            return HTTPStatus.BAD_REQUEST, {"error": "request body must include an action object"}
        try:
            controller = registry.get(session_id)
            controller.submit_action(action)
            return HTTPStatus.OK, controller.snapshot(session_id)
        except SessionNotFoundError as exc:
            return HTTPStatus.NOT_FOUND, {"error": str(exc)}
        except InvalidActionError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}
        except InvalidSessionStateError as exc:
            return HTTPStatus.CONFLICT, {"error": str(exc)}

    if method == "POST" and path.endswith("/continue") and path.startswith("/api/session/"):
        session_id = path.split("/")[3]
        try:
            controller = registry.get(session_id)
            controller.continue_after_result()
            return HTTPStatus.OK, controller.snapshot(session_id)
        except SessionNotFoundError as exc:
            return HTTPStatus.NOT_FOUND, {"error": str(exc)}
        except InvalidSessionStateError as exc:
            return HTTPStatus.CONFLICT, {"error": str(exc)}

    return HTTPStatus.NOT_FOUND, {"error": "not found"}


def run_server(host: str = "127.0.0.1", port: int = 8765, registry: Optional[SessionRegistry] = None) -> None:
    server = SessionApiServer((host, port), registry=registry)
    try:
        print(f"[mahjong16-web] serving on http://{host}:{port}")
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - manual stop
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Mahjong16 local web session API.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="Bind port. Default: 8765")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
