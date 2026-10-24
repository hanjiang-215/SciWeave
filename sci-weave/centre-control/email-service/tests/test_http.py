import asyncio
import json
import sqlite3
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from audit_trail import query_audit_calls
from email_service.config import EmailServiceConfig
from email_service.server import create_email_server


API_VERSION = "1"
FROM_ADDRESS = "public-mailbox@example.test"
SMTP_HOST = "smtp.example.test"
SMTP_PORT = 2525
SMTP_USERNAME = "mailbox-user"
SMTP_PASSWORD = "mailbox-secret"
PRINCIPAL_ID = "person:owner"
RESOLVED_EMAIL = "owner@example.test"
NOTIFICATION_ID = "ntf-draft-1"
DEDUPE_KEY = "draft-ready:candidate-9"
SUBJECT = "Draft is ready for review"
BODY = "Please review draft candidate-9."

INTENT = {
    "notification_id": NOTIFICATION_ID,
    "dedupe_key": DEDUPE_KEY,
    "notification_kind": "draft_ready",
    "recipients": [{"principal_id": PRINCIPAL_ID}],
    "subject": SUBJECT,
    "body": BODY,
    "related": {
        "mapping_domain_id": "map-1",
        "candidate_id": "candidate-9",
        "formal_revision_id": "rev-1",
        "pending_handoff_id": "handoff-1",
        "execution_id": "exec-1",
    },
    "schema_version": "1",
}


class FakeRecipientResolver:
    def __init__(self, addresses: dict[str, str]) -> None:
        self.addresses = addresses

    def resolve(self, principal_id: str) -> str:
        return self.addresses[principal_id]


class FakeSender:
    def __init__(self) -> None:
        self.sent: list = []

    def send(self, message) -> None:
        self.sent.append(message)


class _Server(uvicorn.Server):
    def install_signal_handlers(self) -> None:
        return


def _domain_facts(path: Path) -> tuple:
    connection = sqlite3.connect(path)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        rows = {
            name: connection.execute(f"SELECT * FROM {name} ORDER BY 1").fetchall()
            for name in tables
        }
        return tables, rows
    finally:
        connection.close()


def _create_domain_sentinel(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE research_mapping (
              mapping_domain_id TEXT PRIMARY KEY,
              formal_revision_id TEXT NOT NULL
            );
            CREATE TABLE llm_wiki (
              page_id TEXT PRIMARY KEY,
              body TEXT NOT NULL
            );
            CREATE TABLE candidate (
              candidate_id TEXT PRIMARY KEY,
              candidate_head TEXT NOT NULL
            );
            CREATE TABLE formal_revision (
              formal_revision_id TEXT PRIMARY KEY,
              status TEXT NOT NULL
            );
            CREATE TABLE pending_handoff (
              pending_handoff_id TEXT PRIMARY KEY,
              status TEXT NOT NULL
            );
            CREATE TABLE execution_record (
              execution_id TEXT PRIMARY KEY,
              status TEXT NOT NULL
            );
            INSERT INTO research_mapping VALUES ('map-1', 'rev-1');
            INSERT INTO llm_wiki VALUES ('wiki-1', 'keep-this-page');
            INSERT INTO candidate VALUES ('candidate-9', 'head-9');
            INSERT INTO formal_revision VALUES ('rev-1', 'published');
            INSERT INTO pending_handoff VALUES ('handoff-1', 'waiting');
            INSERT INTO execution_record VALUES ('exec-1', 'completed');
            """
        )
        connection.commit()
    finally:
        connection.close()


@pytest.fixture
def email_mcp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    delivery_path = tmp_path / "delivery.sqlite"
    audit_path = tmp_path / "audit.sqlite"
    domain_path = tmp_path / "domain.sqlite"
    _create_domain_sentinel(domain_path)
    before = _domain_facts(domain_path)
    monkeypatch.setenv("SCIWEAVE_EMAIL_SQLITE_PATH", str(delivery_path))
    monkeypatch.setenv("SCIWEAVE_AUDIT_SQLITE_PATH", str(audit_path))
    monkeypatch.setenv("SCIWEAVE_EMAIL_HOST", "127.0.0.1")
    monkeypatch.setenv("SCIWEAVE_EMAIL_PORT", "0")
    monkeypatch.setenv("SCIWEAVE_EMAIL_ISSUER_URL", "http://127.0.0.1/issuer")
    monkeypatch.setenv("SCIWEAVE_EMAIL_RESOURCE_URL", "http://127.0.0.1/email-service")
    monkeypatch.setenv("SCIWEAVE_EMAIL_API_VERSION", API_VERSION)
    monkeypatch.setenv("SCIWEAVE_EMAIL_FROM_ADDRESS", FROM_ADDRESS)
    monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_HOST", SMTP_HOST)
    monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_PORT", str(SMTP_PORT))
    monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_USERNAME", SMTP_USERNAME)
    monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_PASSWORD", SMTP_PASSWORD)
    monkeypatch.setenv(
        "SCIWEAVE_EMAIL_TOKENS_JSON",
        json.dumps(
            {
                "gateway": {"caller_id": "service:task-gateway", "caller_type": "service"},
                "other": {"caller_id": "service:centre-workflow", "caller_type": "service"},
            }
        ),
    )
    config = EmailServiceConfig.from_environment()
    resolver = FakeRecipientResolver({PRINCIPAL_ID: RESOLVED_EMAIL})
    sender = FakeSender()
    app = create_email_server(config, resolver, sender).streamable_http_app()
    server = _Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("email-service did not start")
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield {
            "mcp_url": f"http://127.0.0.1:{port}/mcp",
            "health_url": f"http://127.0.0.1:{port}/health",
            "delivery_path": delivery_path,
            "audit_path": audit_path,
            "domain_path": domain_path,
            "domain_before": before,
            "sender": sender,
        }
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _session_call(mcp: dict, token: str, fn):
    async def run():
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(headers=headers, timeout=30) as http:
            async with streamable_http_client(mcp["mcp_url"], http_client=http) as (read, write, _session_id):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await fn(session)

    return asyncio.run(run())


def list_tools(mcp: dict, token: str):
    return _session_call(mcp, token, lambda session: session.list_tools())


def call_tool(mcp: dict, token: str, name: str, arguments: dict | None = None):
    return _session_call(mcp, token, lambda session: session.call_tool(name, arguments or {}))


def body(result) -> dict:
    assert result.isError is False
    assert result.structuredContent is not None
    return result.structuredContent


def error_code(result) -> str:
    assert result.isError is True
    return result.content[0].text.rsplit(": ", 1)[-1]


def accept_draft(mcp: dict):
    return call_tool(mcp, "gateway", "send_notification", INTENT)


def wait_until_sent(mcp: dict, token: str = "gateway") -> dict:
    deadline = time.time() + 5
    last = None
    while time.time() < deadline:
        result = call_tool(mcp, token, "get_notification_status", {"notification_id": NOTIFICATION_ID})
        if result.isError is False:
            last = body(result)
            if last.get("delivery_status") == "sent":
                return last
        time.sleep(0.05)
    raise AssertionError(last)


def test_unauthenticated_mcp_is_rejected_and_health_probe_stays_minimal(email_mcp):
    unauthenticated = httpx.post(
        email_mcp["mcp_url"],
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert unauthenticated.status_code == 401
    assert SMTP_PASSWORD not in unauthenticated.text
    assert BODY not in unauthenticated.text
    probe = httpx.get(email_mcp["health_url"])
    assert probe.status_code == 200
    assert probe.json() == {
        "status": "ready",
        "service": "email-service",
        "api_version": API_VERSION,
    }


def test_valid_notification_is_accepted_then_reports_delivery_status_only(email_mcp):
    accepted = body(accept_draft(email_mcp))
    assert accepted == {
        "notification_id": NOTIFICATION_ID,
        "acceptance": "accepted_for_delivery",
    }
    status = wait_until_sent(email_mcp)
    assert status == {
        "notification_id": NOTIFICATION_ID,
        "delivery_status": "sent",
        "attempt_count": 1,
    }
    assert len(email_mcp["sender"].sent) == 1
    message = email_mcp["sender"].sent[0]
    assert message.to_address == RESOLVED_EMAIL
    assert message.notification_id == NOTIFICATION_ID
    assert message.subject == SUBJECT
    assert message.body == BODY


def test_another_caller_cannot_see_the_notification(email_mcp):
    accept_draft(email_mcp)
    wait_until_sent(email_mcp)
    hidden = call_tool(
        email_mcp, "other", "get_notification_status", {"notification_id": NOTIFICATION_ID}
    )
    assert error_code(hidden) == "denied"
    assert BODY not in hidden.content[0].text
    assert SMTP_PASSWORD not in hidden.content[0].text
    assert SUBJECT not in hidden.content[0].text


def test_authenticated_health_returns_component_status(email_mcp):
    report = body(call_tool(email_mcp, "gateway", "health"))
    assert report == {
        "status": "ready",
        "components": {
            "delivery_store": "ready",
            "audit": "ready",
            "mailbox": "ready",
        },
    }
    encoded = json.dumps(report)
    assert SMTP_PASSWORD not in encoded
    assert SMTP_USERNAME not in encoded
    assert BODY not in encoded


def test_access_ledger_mentions_notification_but_not_body_or_credentials(email_mcp):
    accept_draft(email_mcp)
    wait_until_sent(email_mcp)
    assert email_mcp["audit_path"].resolve() != email_mcp["delivery_path"].resolve()
    audit = sqlite3.connect(email_mcp["audit_path"])
    audit.row_factory = sqlite3.Row
    try:
        calls = query_audit_calls(audit, service="email-service", tool="send_notification")
        tables = {
            row[0]
            for row in audit.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    finally:
        audit.close()
    assert tables == {"audit_call"}
    assert calls
    assert any(row["target_object_id"] == NOTIFICATION_ID for row in calls)
    leaked = " ".join(str(value) for row in calls for value in tuple(row) if value is not None)
    assert BODY not in leaked
    assert SUBJECT not in leaked
    assert SMTP_PASSWORD not in leaked
    assert SMTP_USERNAME not in leaked
    assert RESOLVED_EMAIL not in leaked


def test_domain_facts_stay_unchanged_and_no_handoff_tool_is_exposed(email_mcp):
    listed = list_tools(email_mcp, "gateway")
    assert {tool.name for tool in listed.tools} == {
        "send_notification",
        "get_notification_status",
        "health",
    }
    accept_draft(email_mcp)
    wait_until_sent(email_mcp)
    assert _domain_facts(email_mcp["domain_path"]) == email_mcp["domain_before"]


def test_schema_forbids_sender_overrides_and_mail_uses_configured_mailbox(email_mcp):
    listed = list_tools(email_mcp, "gateway")
    send_tool = next(tool for tool in listed.tools if tool.name == "send_notification")
    properties = set(send_tool.inputSchema["properties"])
    assert properties == {
        "notification_id",
        "dedupe_key",
        "notification_kind",
        "recipients",
        "subject",
        "body",
        "related",
        "schema_version",
    }
    accept_draft(email_mcp)
    wait_until_sent(email_mcp)
    message = email_mcp["sender"].sent[0]
    assert message.from_address == FROM_ADDRESS
    assert message.smtp_host == SMTP_HOST
    assert message.smtp_port == SMTP_PORT
    assert message.smtp_username == SMTP_USERNAME
    assert message.smtp_password == SMTP_PASSWORD
