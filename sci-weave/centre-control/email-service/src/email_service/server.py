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
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import EmailServiceConfig, MailboxSettings, TokenIdentity
from .ports import EmailServiceError, MailSender, RecipientResolver
from .service import Caller, EmailDeliveryService


class StaticTokenVerifier(TokenVerifier):
    """Verifies configured opaque bearer tokens. Identity comes from server config, not request headers."""

    def __init__(self, identities: dict[str, TokenIdentity]) -> None:
        self._identities = identities

    async def verify_token(self, token: str) -> AccessToken | None:
        identity = self._identities.get(token)
        if identity is None:
            return None
        return AccessToken(
            token=token,
            client_id=identity.caller_id,
            scopes=[],
            subject=identity.caller_id,
            claims={"caller_id": identity.caller_id, "caller_type": identity.caller_type},
        )


def create_email_server(
    config: EmailServiceConfig,
    resolver: RecipientResolver,
    sender: MailSender,
) -> FastMCP:
    conn = sqlite3.connect(config.sqlite_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    lock = RLock()
    service = EmailDeliveryService(conn, resolver, sender, config.mailbox, config.retry, lock)
    audit_box: dict[str, sqlite3.Connection] = {}
    server = FastMCP(
        name="SciWeave Email Service",
        instructions=(
            "Accept human_notification_intent for delivery and report delivery status. "
            "Mail success does not change domain facts or publish a task handoff."
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
            raise EmailServiceError("unauthorized")
        caller_id = token.claims.get("caller_id")
        caller_type = token.claims.get("caller_type")
        if not isinstance(caller_id, str) or caller_type not in {"researcher", "project_owner", "service"}:
            raise EmailServiceError("unauthorized")
        return Caller(caller_id, caller_type)

    def audited(caller: Caller, tool: str, target_type: str, target_id: str, operation, *, write: bool):
        record = CallRecord(
            caller_id=caller.caller_id,
            channel_id="mcp-streamable-http",
            caller_type="service" if caller.caller_type == "service" else "human",
            service="email-service",
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
            except EmailServiceError as exc:
                _finish_audit(audit_box["conn"], call_id, exc.code, started)
                raise
            _finish_audit(audit_box["conn"], call_id, None, started)
            return result

    @server.tool(description="Accept one human_notification_intent for later delivery.")
    def send_notification(
        notification_id: str,
        dedupe_key: str,
        notification_kind: str,
        recipients: list[dict[str, str]],
        subject: str,
        body: str,
        related: dict[str, str],
        schema_version: str,
    ) -> dict[str, str]:
        caller = caller_from_token()
        intent = {
            "notification_id": notification_id,
            "dedupe_key": dedupe_key,
            "notification_kind": notification_kind,
            "recipients": recipients,
            "subject": subject,
            "body": body,
            "related": related,
            "schema_version": schema_version,
        }
        return audited(
            caller,
            "send_notification",
            "notification",
            notification_id,
            lambda: service.accept(caller, intent),
            write=True,
        )

    @server.tool(description="Read delivery status for a notification submitted by this caller.")
    def get_notification_status(notification_id: str) -> dict[str, Any]:
        caller = caller_from_token()
        return audited(
            caller,
            "get_notification_status",
            "notification",
            notification_id,
            lambda: service.status(caller, notification_id),
            write=True,
        )

    @server.tool(description="Return authenticated component status for delivery, audit, and mailbox.")
    def health() -> dict[str, Any]:
        caller = caller_from_token()
        return audited(
            caller,
            "health",
            "service",
            "email-service",
            lambda: _component_health(conn, audit_box["conn"], lock, config.mailbox),
            write=False,
        )

    @server.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def http_health(_: Request) -> JSONResponse:
        payload = {
            "status": "ready" if _stores_ready(conn, audit_box.get("conn"), lock) else "unavailable",
            "service": "email-service",
            "api_version": config.api_version,
        }
        if payload["status"] != "ready":
            return JSONResponse(payload, status_code=503)
        return JSONResponse(payload)

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
            service.start()
            try:
                async with previous(asgi_app):
                    yield
            finally:
                service.stop()
                audit_box.pop("conn", None)
                audit.close()

        app.router.lifespan_context = lifespan
        return app

    server.streamable_http_app = streamable_http_app
    _reject_undeclared_send_arguments(server, service, caller_from_token)
    return server


_SEND_NOTIFICATION_FIELDS = frozenset(
    {
        "notification_id",
        "dedupe_key",
        "notification_kind",
        "recipients",
        "subject",
        "body",
        "related",
        "schema_version",
    }
)


def _reject_undeclared_send_arguments(server: FastMCP, service: EmailDeliveryService, caller_from_token) -> None:
    tool = server._tool_manager.get_tool("send_notification")
    if tool is None:
        raise RuntimeError("send_notification tool is not registered")
    original = tool.fn_metadata.call_fn_with_arg_validation

    async def call_fn_with_arg_validation(fn, fn_is_async, arguments_to_validate, arguments_to_pass_directly):
        arguments = arguments_to_validate or {}
        undeclared = set(arguments) - _SEND_NOTIFICATION_FIELDS
        missing = _SEND_NOTIFICATION_FIELDS - set(arguments)
        if undeclared or missing:
            service.record_invalid(caller_from_token(), arguments)
        try:
            return await original(fn, fn_is_async, arguments_to_validate, arguments_to_pass_directly)
        except ValidationError:
            service.record_invalid(caller_from_token(), arguments)

    object.__setattr__(tool.fn_metadata, "call_fn_with_arg_validation", call_fn_with_arg_validation)


def _begin_audit(audit: sqlite3.Connection, record: CallRecord) -> str:
    try:
        return begin_call(audit, record)
    except AuditUnavailableError:
        raise EmailServiceError("audit_unavailable") from None


def _finish_audit(audit: sqlite3.Connection, call_id: str, error_code: str | None, started: float) -> None:
    duration_ms = max(0, int((time.monotonic() - started) * 1000))
    if error_code is None:
        finish_call(audit, call_id, result="ok", duration_ms=duration_ms)
        return
    result = "denied" if error_code == "denied" else "error"
    finish_call(audit, call_id, result=result, error_code=error_code, duration_ms=duration_ms)


def _stores_ready(facts: sqlite3.Connection, audit: sqlite3.Connection | None, lock: RLock) -> bool:
    if audit is None:
        return False
    try:
        with lock:
            facts.execute("SELECT 1 FROM notification_delivery LIMIT 1").fetchone()
            audit.execute("SELECT 1 FROM audit_call LIMIT 1").fetchone()
    except sqlite3.Error:
        return False
    return True


def _component_health(
    facts: sqlite3.Connection,
    audit: sqlite3.Connection,
    lock: RLock,
    mailbox: MailboxSettings,
) -> dict[str, Any]:
    delivery = "ready"
    audit_state = "ready"
    try:
        with lock:
            facts.execute("SELECT 1 FROM notification_delivery LIMIT 1").fetchone()
    except sqlite3.Error:
        delivery = "unavailable"
    try:
        with lock:
            audit.execute("SELECT 1 FROM audit_call LIMIT 1").fetchone()
    except sqlite3.Error:
        audit_state = "unavailable"
    mailbox_state = _mailbox_state(mailbox)
    states = {delivery, audit_state, mailbox_state}
    if "unavailable" in states:
        overall = "unavailable"
    elif "not_configured" in states:
        overall = "not_configured"
    else:
        overall = "ready"
    return {
        "status": overall,
        "components": {
            "delivery_store": delivery,
            "audit": audit_state,
            "mailbox": mailbox_state,
        },
    }


def _mailbox_state(mailbox: MailboxSettings) -> str:
    configured = (
        bool(mailbox.from_address)
        and bool(mailbox.smtp_host)
        and bool(mailbox.smtp_username)
        and bool(mailbox.smtp_password)
        and isinstance(mailbox.smtp_port, int)
        and mailbox.smtp_port > 0
    )
    if configured:
        return "ready"
    return "not_configured"
