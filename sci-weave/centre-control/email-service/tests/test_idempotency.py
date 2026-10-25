import asyncio
import json
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from email_service.config import EmailServiceConfig
from email_service.server import create_email_server


API_VERSION = "1"
FROM_ADDRESS = "public-mailbox@example.test"
SMTP_HOST = "smtp.example.test"
SMTP_PORT = 2525
SMTP_USERNAME = "mailbox-user"
SMTP_PASSWORD = "mailbox-secret"
PRINCIPAL_ID = "person:owner"
OTHER_PRINCIPAL_ID = "person:reviewer"
RESOLVED_EMAIL = "owner@example.test"
OTHER_EMAIL = "reviewer@example.test"
NOTIFICATION_ID = "ntf-draft-1"
REPLAY_NOTIFICATION_ID = "ntf-draft-replay"
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
    "related": {"candidate_id": "candidate-9"},
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


@pytest.fixture
def idempotent_mcp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    delivery_path = tmp_path / "delivery.sqlite"
    audit_path = tmp_path / "audit.sqlite"
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
        json.dumps({"gateway": {"caller_id": "service:task-gateway", "caller_type": "service"}}),
    )
    config = EmailServiceConfig.from_environment()
    resolver = FakeRecipientResolver({PRINCIPAL_ID: RESOLVED_EMAIL, OTHER_PRINCIPAL_ID: OTHER_EMAIL})
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
        yield {"mcp_url": f"http://127.0.0.1:{port}/mcp", "sender": sender}
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _session_call(mcp: dict, fn):
    async def run():
        headers = {"Authorization": "Bearer gateway"}
        async with httpx.AsyncClient(headers=headers, timeout=30) as http:
            async with streamable_http_client(mcp["mcp_url"], http_client=http) as (read, write, _session_id):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await fn(session)

    return asyncio.run(run())


def call_tool(mcp: dict, name: str, arguments: dict):
    return _session_call(mcp, lambda session: session.call_tool(name, arguments))


def body(result) -> dict:
    assert result.isError is False
    assert result.structuredContent is not None
    return result.structuredContent


def error_code(result) -> str:
    assert result.isError is True
    return result.content[0].text.rsplit(": ", 1)[-1]


def send(mcp: dict, intent: dict):
    return call_tool(mcp, "send_notification", intent)


def wait_until_sent(mcp: dict) -> dict:
    deadline = time.time() + 5
    last = None
    while time.time() < deadline:
        result = call_tool(mcp, "get_notification_status", {"notification_id": NOTIFICATION_ID})
        if result.isError is False:
            last = body(result)
            if last.get("delivery_status") == "sent":
                return last
        time.sleep(0.05)
    raise AssertionError(last)


def test_credential_like_body_is_accepted_and_replay_returns_existing(idempotent_mcp):
    intent = {**INTENT, "body": "Reset with password=hunter2 before review."}
    accepted = body(send(idempotent_mcp, intent))
    assert accepted == {
        "notification_id": NOTIFICATION_ID,
        "acceptance": "accepted_for_delivery",
    }
    status = wait_until_sent(idempotent_mcp)
    assert status == {
        "notification_id": NOTIFICATION_ID,
        "delivery_status": "sent",
        "attempt_count": 1,
        "recipients": [
            {
                "principal_id": PRINCIPAL_ID,
                "status": "sent",
                "attempt_count": 1,
                "error_summary": None,
            }
        ],
    }
    assert "hunter2" not in json.dumps(status)
    replayed = body(send(idempotent_mcp, {**intent, "notification_id": REPLAY_NOTIFICATION_ID}))
    assert replayed == {
        "notification_id": NOTIFICATION_ID,
        "delivery_status": "sent",
    }
    assert len(idempotent_mcp["sender"].sent) == 1
    assert idempotent_mcp["sender"].sent[0].body == intent["body"]


def test_equivalent_replay_returns_original_notification_and_does_not_send_again(idempotent_mcp):
    accepted = body(send(idempotent_mcp, INTENT))
    assert accepted == {
        "notification_id": NOTIFICATION_ID,
        "acceptance": "accepted_for_delivery",
    }
    status = wait_until_sent(idempotent_mcp)
    assert status == {
        "notification_id": NOTIFICATION_ID,
        "delivery_status": "sent",
        "attempt_count": 1,
        "recipients": [
            {
                "principal_id": PRINCIPAL_ID,
                "status": "sent",
                "attempt_count": 1,
                "error_summary": None,
            }
        ],
    }

    replay = {
        **INTENT,
        "notification_id": REPLAY_NOTIFICATION_ID,
        "related": {"candidate_id": "candidate-9", "execution_id": "exec-2"},
        "schema_version": "2",
    }
    replayed = body(send(idempotent_mcp, replay))
    assert replayed == {
        "notification_id": NOTIFICATION_ID,
        "delivery_status": "sent",
    }
    assert len(idempotent_mcp["sender"].sent) == 1
    message = idempotent_mcp["sender"].sent[0]
    assert message.to_address == RESOLVED_EMAIL
    assert message.notification_id == NOTIFICATION_ID
    assert message.subject == SUBJECT
    assert message.body == BODY

    deadline = time.time() + 0.4
    while time.time() < deadline:
        assert len(idempotent_mcp["sender"].sent) == 1
        time.sleep(0.05)
    again = body(call_tool(idempotent_mcp, "get_notification_status", {"notification_id": NOTIFICATION_ID}))
    assert again == status


@pytest.mark.parametrize(
    "override",
    [
        {"subject": "A different subject"},
        {"body": "A different body."},
        {"recipients": [{"principal_id": OTHER_PRINCIPAL_ID}]},
        {"notification_kind": "execution_failed"},
    ],
)
def test_same_dedupe_key_with_different_content_conflicts_and_leaves_original(idempotent_mcp, override):
    send(idempotent_mcp, INTENT)
    status = wait_until_sent(idempotent_mcp)
    conflict_id = "ntf-conflict"
    conflict = send(idempotent_mcp, {**INTENT, "notification_id": conflict_id, **override})
    assert error_code(conflict) == "idempotency_conflict"
    assert SUBJECT not in conflict.content[0].text
    assert BODY not in conflict.content[0].text
    assert SMTP_PASSWORD not in conflict.content[0].text

    assert len(idempotent_mcp["sender"].sent) == 1
    message = idempotent_mcp["sender"].sent[0]
    assert message.to_address == RESOLVED_EMAIL
    assert message.notification_id == NOTIFICATION_ID
    assert message.subject == SUBJECT
    assert message.body == BODY
    unchanged = body(call_tool(idempotent_mcp, "get_notification_status", {"notification_id": NOTIFICATION_ID}))
    assert unchanged == status
    missing = call_tool(idempotent_mcp, "get_notification_status", {"notification_id": conflict_id})
    assert error_code(missing) == "denied"

    replayed = body(send(idempotent_mcp, {**INTENT, "notification_id": REPLAY_NOTIFICATION_ID}))
    assert replayed == {
        "notification_id": NOTIFICATION_ID,
        "delivery_status": "sent",
    }
    assert len(idempotent_mcp["sender"].sent) == 1


def test_reordered_recipients_are_the_same_notification(idempotent_mcp):
    first = {
        **INTENT,
        "recipients": [
            {"principal_id": PRINCIPAL_ID},
            {"principal_id": OTHER_PRINCIPAL_ID},
        ],
    }
    send(idempotent_mcp, first)
    wait_until_sent(idempotent_mcp)
    assert len(idempotent_mcp["sender"].sent) == 2

    replayed = body(
        send(
            idempotent_mcp,
            {
                **first,
                "notification_id": REPLAY_NOTIFICATION_ID,
                "recipients": [
                    {"principal_id": OTHER_PRINCIPAL_ID},
                    {"principal_id": PRINCIPAL_ID},
                ],
            },
        )
    )
    assert replayed == {
        "notification_id": NOTIFICATION_ID,
        "delivery_status": "sent",
    }
    assert len(idempotent_mcp["sender"].sent) == 2
    assert {message.to_address for message in idempotent_mcp["sender"].sent} == {RESOLVED_EMAIL, OTHER_EMAIL}
