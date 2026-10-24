from __future__ import annotations

import json
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import RegistryConfig
from .service import Caller, RegistryError, RegistryService


TOOLS = {"register_principal", "register_workflow_agent", "register_agent_instance", "get_principal_contact", "get_agent_registration", "health"}


def create_registry_server(config: RegistryConfig) -> "RegistryServer":
    conn = sqlite3.connect(config.sqlite_path, check_same_thread=False)
    audit = None
    if config.audit_sqlite_path:
        try:
            from audit_trail import init_audit_table
            audit = sqlite3.connect(config.audit_sqlite_path, check_same_thread=False)
            audit.row_factory = sqlite3.Row
            init_audit_table(audit)
        except Exception:
            conn.close()
            raise
    server = RegistryServer((config.host, config.port), RegistryHandler)
    server.registry_config = config
    server.registry_service = RegistryService(conn, audit)
    server.registry_audit = audit
    return server


class RegistryServer(ThreadingHTTPServer):
    allow_reuse_address = True


class RegistryHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(HTTPStatus.OK, {"status": "ready", "service": "registry", "api_version": "v1"})
            return
        self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/mcp":
            self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        config = self.server.registry_config  # type: ignore[attr-defined]
        if config.bearer_token and self.headers.get("Authorization") != f"Bearer {config.bearer_token}":
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        try:
            request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            caller = Caller(self.headers.get("X-Caller-Id", "anonymous"), self.headers.get("X-Caller-Type", "service"))
            result = self._call(request, caller)
            self._send(HTTPStatus.OK, {"jsonrpc": "2.0", "id": request.get("id"), "result": result})
        except RegistryError as exc:
            self._send(HTTPStatus.OK, {"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": exc.code, "message": str(exc)}})
        except Exception:
            self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})

    def _call(self, request: dict, caller: Caller) -> dict:
        method = request.get("method")
        if method == "tools/list": return {"tools": [{"name": name} for name in sorted(TOOLS)]}
        if method != "tools/call": raise RegistryError("method_not_found")
        params = request.get("params", {})
        name = params.get("name")
        if name not in TOOLS: raise RegistryError("tool_not_found")
        args = params.get("arguments", {})
        service = self.server.registry_service  # type: ignore[attr-defined]
        audit = self.server.registry_audit  # type: ignore[attr-defined]
        target = str(args.get("principal_id") or args.get("agent_id") or "")
        if audit is not None:
            from audit_trail import CallRecord, call_scope
            record = CallRecord(caller.caller_id, "mcp", caller.caller_type if caller.caller_type in {"human", "agent", "system", "service"} else "service", "registry", name, target_object_type="registry", target_object_id=target)
            with call_scope(audit, record):
                return self._dispatch_tool(service, name, caller, args)
        return self._dispatch_tool(service, name, caller, args)

    @staticmethod
    def _dispatch_tool(service: RegistryService, name: str, caller: Caller, args: dict) -> dict:
        if name == "health": result = service.health(caller)
        elif name == "register_principal": result = service.register_principal(caller, args)
        elif name == "register_workflow_agent": result = service.register_workflow_agent(caller, args)
        elif name == "register_agent_instance": result = service.register_agent_instance(caller, args)
        elif name == "get_principal_contact": result = service.get_principal_contact(caller, args)
        else: result = service.get_agent_registration(caller, args)
        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}

    def _send(self, status: HTTPStatus, body: object) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        return
