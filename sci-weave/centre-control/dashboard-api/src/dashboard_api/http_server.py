from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .aggregator import DashboardAggregator
from .config import DashboardConfig
from .sources import fetch_json


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server_version = "SciWeaveDashboard/1"

    def do_OPTIONS(self) -> None:  # noqa: N802
        if self.path.startswith("/api/dashboard/"):
            self.send_response(HTTPStatus.NO_CONTENT)
            self._write_cors_headers()
            self.end_headers()
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ready", "api_version": "v1"})
            return
        if self.path == "/api/dashboard/snapshot":
            try:
                payload = self.server.dashboard_aggregator.get_snapshot()  # type: ignore[attr-defined]
            except Exception:
                self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "snapshot_unavailable"})
                return
            self._send_json(HTTPStatus.OK, payload)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PUT(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PATCH(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_DELETE(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def _method_not_allowed(self) -> None:
        self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"})

    def _send_json(self, status: HTTPStatus, payload: object) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self._write_cors_headers()
        self.end_headers()
        self.wfile.write(encoded)

    def _write_cors_headers(self) -> None:
        origin = self.server.dashboard_config.cors_origin  # type: ignore[attr-defined]
        request_origin = self.headers.get("Origin")
        if origin and (request_origin is None or request_origin == origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Accept, Content-Type")
            self.send_header("Vary", "Origin")

    def log_message(self, format: str, *args: object) -> None:
        return


class DashboardServer(ThreadingHTTPServer):
    allow_reuse_address = True


def create_dashboard_server(config: DashboardConfig, aggregator: DashboardAggregator | None = None) -> DashboardServer:
    if aggregator is None:
        def fetch(source):
            return fetch_json(source, timeout_seconds=config.timeout_seconds, max_payload_bytes=config.max_payload_bytes)
        aggregator = DashboardAggregator(config.source_specs, fetch)
    server = DashboardServer((config.host, config.port), DashboardRequestHandler)
    server.dashboard_config = config  # type: ignore[attr-defined]
    server.dashboard_aggregator = aggregator  # type: ignore[attr-defined]
    return server
