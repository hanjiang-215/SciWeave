from __future__ import annotations

import sqlite3
import time
from contextlib import asynccontextmanager
from threading import RLock
from typing import Any

from audit_trail import (
    AuditUnavailableError,
    CallRecord,
    begin_call,
    finish_call,
    init_audit_table,
    open_connection,
    record_attempted,
)
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import RegistryConfig, TokenIdentity
from .service import Caller, RegistryError, RegistryService


class StaticTokenVerifier(TokenVerifier):
    """Verifies configured opaque bearer tokens. Identity comes from server config, not request headers."""

    def __init__(self, identities: dict[str, TokenIdentity]) -> None:
        self._identities = identities

    async def verify_token(self, token: str) -> AccessToken | None:
        identity = self._identities.get(token)
        if identity is None:
            return None
        claims: dict[str, Any] = {
            "caller_id": identity.caller_id,
            "caller_type": identity.caller_type,
        }
        if identity.principal_id is not None:
            claims["principal_id"] = identity.principal_id
        if identity.service_role is not None:
            claims["service_role"] = identity.service_role
        return AccessToken(
            token=token,
            client_id=identity.caller_id,
            scopes=[],
            subject=identity.caller_id,
            claims=claims,
        )


def create_registry_server(config: RegistryConfig) -> FastMCP:
    conn = sqlite3.connect(config.sqlite_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    service = RegistryService(conn)
    lock = RLock()
    audit_box: dict[str, sqlite3.Connection] = {}
    server = FastMCP(
        name="SciWeave Registry",
        instructions=(
            "Registry records principals, workflow agents, instances, and notification contacts. "
            "It does not authorize TaskNode execution."
        ),
        host=config.host,
        port=config.port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        token_verifier=StaticTokenVerifier(config.token_identities),
        auth=AuthSettings(
            issuer_url=config.issuer_url,
            resource_server_url=config.resource_url,
            validate_token_resource=False,
        ),
    )

    def caller_from_token() -> Caller:
        token = get_access_token()
        if token is None or token.claims is None:
            raise RegistryError("unauthorized")
        caller_id = token.claims.get("caller_id")
        caller_type = token.claims.get("caller_type")
        principal_id = token.claims.get("principal_id")
        service_role = token.claims.get("service_role")
        if not isinstance(caller_id, str) or caller_type not in {"researcher", "project_owner", "service"}:
            raise RegistryError("unauthorized")
        if principal_id is not None and not isinstance(principal_id, str):
            raise RegistryError("unauthorized")
        if service_role is not None and not isinstance(service_role, str):
            raise RegistryError("unauthorized")
        return Caller(caller_id, caller_type, principal_id, service_role)

    def audited(caller: Caller, tool: str, target_type: str, target_id: str, operation, *, write: bool):
        record = CallRecord(
            caller_id=caller.caller_id,
            channel_id="mcp-streamable-http",
            caller_type="service" if caller.caller_type == "service" else "human",
            service="registry",
            tool=tool,
            target_object_type=target_type,
            target_object_id=target_id or None,
        )
        if not write:
            with lock:
                record_attempted(audit_box["conn"], record)
                return operation()
        with lock:
            call_id = _begin_audit(audit_box["conn"], record)
            started = time.monotonic()
            try:
                result = operation()
            except RegistryError as exc:
                _finish_audit(audit_box["conn"], call_id, exc.code, started)
                raise
            _finish_audit(audit_box["conn"], call_id, None, started)
            return result

    @server.tool(description="Register or update a principal and its notification contact.")
    def register_principal(
        principal_id: str,
        role: str,
        idempotency_key: str,
        contact_email: str | None = None,
        status: str = "active",
    ) -> dict[str, Any]:
        caller = caller_from_token()
        payload = {
            "principal_id": principal_id,
            "role": role,
            "idempotency_key": idempotency_key,
            "contact_email": contact_email,
            "status": status,
        }
        return audited(
            caller, "register_principal", "principal", principal_id,
            lambda: service.register_principal(caller, payload), write=True,
        )

    @server.tool(
        description=(
            "Register or update a workflow agent owned by the caller or Project Owner. "
            "principal_id is required for kind=endpoint (the owning principal) and "
            "must be omitted for kind=centre (self-owned)."
        )
    )
    def register_workflow_agent(
        agent_id: str,
        workflow_id: str,
        kind: str,
        workflow_kind: str,
        idempotency_key: str,
        principal_id: str | None = None,
        created_by: str | None = None,
        status: str = "active",
    ) -> dict[str, Any]:
        caller = caller_from_token()
        payload = {
            "agent_id": agent_id,
            "workflow_id": workflow_id,
            "kind": kind,
            "workflow_kind": workflow_kind,
            "idempotency_key": idempotency_key,
            "principal_id": principal_id,
            "created_by": created_by or caller.caller_id,
            "status": status,
        }
        return audited(
            caller, "register_workflow_agent", "workflow_agent", agent_id,
            lambda: service.register_workflow_agent(caller, payload), write=True,
        )

    @server.tool(description="Register or refresh one runtime instance of a workflow agent.")
    def register_agent_instance(
        agent_id: str,
        agent_instance_id: str,
        idempotency_key: str,
        runtime_status: str = "starting",
        last_seen_at: str | None = None,
    ) -> dict[str, Any]:
        caller = caller_from_token()
        payload = {
            "agent_id": agent_id,
            "agent_instance_id": agent_instance_id,
            "idempotency_key": idempotency_key,
            "runtime_status": runtime_status,
            "last_seen_at": last_seen_at,
        }
        return audited(
            caller, "register_agent_instance", "agent_instance", agent_instance_id,
            lambda: service.register_agent_instance(caller, payload), write=True,
        )

    @server.tool(description="Resolve the current active notification contact for a principal.")
    def get_principal_contact(principal_id: str) -> dict[str, Any]:
        caller = caller_from_token()
        return audited(
            caller, "get_principal_contact", "principal", principal_id,
            lambda: service.get_principal_contact(caller, {"principal_id": principal_id}), write=False,
        )

    @server.tool(description="Read one workflow agent registration and its runtime instances.")
    def get_agent_registration(agent_id: str) -> dict[str, Any]:
        caller = caller_from_token()
        return audited(
            caller, "get_agent_registration", "workflow_agent", agent_id,
            lambda: service.get_agent_registration(caller, {"agent_id": agent_id}), write=False,
        )

    @server.tool(description="Return authenticated Registry service and storage health.")
    def health() -> dict[str, str]:
        caller = caller_from_token()

        def operation() -> dict[str, str]:
            if not _storage_ready(conn, audit_box["conn"], lock):
                raise RegistryError("registry_unavailable")
            return service.health(caller)

        return audited(caller, "health", "service", "registry", operation, write=False)

    @server.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def http_health(_: Request) -> JSONResponse:
        if _storage_ready(conn, audit_box["conn"], lock):
            return JSONResponse({"status": "ready", "service": "registry", "storage": "ready"})
        return JSONResponse(
            {"status": "unavailable", "service": "registry", "storage": "unavailable"},
            status_code=503,
        )

    original_streamable_http_app = server.streamable_http_app

    def streamable_http_app():
        app = original_streamable_http_app()
        previous = app.router.lifespan_context

        @asynccontextmanager
        async def lifespan(asgi_app):
            audit = open_connection(config.audit_sqlite_path)
            try:
                init_audit_table(audit)
            except Exception:
                audit.close()
                raise
            audit_box["conn"] = audit
            try:
                async with previous(asgi_app):
                    yield
            finally:
                audit_box.pop("conn", None)
                audit.close()

        app.router.lifespan_context = lifespan
        return app

    server.streamable_http_app = streamable_http_app
    return server


def _begin_audit(audit: sqlite3.Connection, record: CallRecord) -> str:
    try:
        return begin_call(audit, record)
    except AuditUnavailableError:
        raise RegistryError("audit_unavailable") from None


def _storage_ready(facts: sqlite3.Connection, audit: sqlite3.Connection, lock: RLock) -> bool:
    try:
        with lock:
            facts.execute("SELECT 1 FROM principal LIMIT 1").fetchone()
            audit.execute("SELECT 1 FROM audit_call LIMIT 1").fetchone()
    except sqlite3.Error:
        return False
    return True


def _finish_audit(audit: sqlite3.Connection, call_id: str, error_code: str | None, started: float) -> None:
    duration_ms = max(0, int((time.monotonic() - started) * 1000))
    if error_code is None:
        finish_call(audit, call_id, result="ok", duration_ms=duration_ms)
        return
    result = "denied" if error_code == "denied" else "error"
    finish_call(audit, call_id, result=result, error_code=error_code, duration_ms=duration_ms)
