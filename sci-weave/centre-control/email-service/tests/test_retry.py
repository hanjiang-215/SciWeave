import json
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from email_service.config import EmailServiceConfig
from email_service.ports import NonRetryableContentError, PermanentSenderFailure, TransientSenderFailure
from email_service.server import create_email_server


API_VERSION = "1"
FROM_ADDRESS = "public-mailbox@example.test"
SMTP_HOST = "smtp.example.test"
SMTP_PORT = 2525
SMTP_USERNAME = "mailbox-user"
SMTP_PASSWORD = "mailbox-secret"
PRINCIPAL_ID = "person:owner"
RESOLVED_EMAIL = "owner@example.test"
NOTIFICATION_ID = "ntf-retry-1"
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
    def resolve(self, principal_id: str) -> str:
        assert principal_id == PRINCIPAL_ID
        return RESOLVED_EMAIL


class ScriptedSender:
    """Fake sender. Outcomes are exceptions to raise, or None to accept the message."""

    def __init__(self, outcomes: list[Exception | None], afterwards: Exception | None = None) -> None:
        self.outcomes = list(outcomes)
        self.afterwards = afterwards
        self.calls: list = []
        self.gate = threading.Event()
        self.gate.set()

    def send(self, message) -> None:
        self.calls.append(message)
        self.gate.wait()
        outcome = self.outcomes.pop(0) if self.outcomes else self.afterwards
        if outcome is not None:
            raise outcome


class _Server(uvicorn.Server):
    def install_signal_handlers(self) -> None:
        return


def _session_call(mcp_url: str, token: str, fn):
    async def run():
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(headers=headers, timeout=30) as http:
            async with streamable_http_client(mcp_url, http_client=http) as (read, write, _session_id):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await fn(session)

    return asyncio_run(run())


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


def list_tools(mcp_url: str, token: str = "gateway"):
    return _session_call(mcp_url, token, lambda session: session.list_tools())


def call_tool(mcp_url: str, name: str, arguments: dict | None = None, token: str = "gateway"):
    return _session_call(mcp_url, token, lambda session: session.call_tool(name, arguments or {}))


def body(result) -> dict:
    assert result.isError is False
    assert result.structuredContent is not None
    return result.structuredContent


def _configure(monkeypatch: pytest.MonkeyPatch, delivery_path: Path, audit_path: Path, **overrides: str) -> None:
    values = {
        "SCIWEAVE_EMAIL_SQLITE_PATH": str(delivery_path),
        "SCIWEAVE_AUDIT_SQLITE_PATH": str(audit_path),
        "SCIWEAVE_EMAIL_HOST": "127.0.0.1",
        "SCIWEAVE_EMAIL_PORT": "0",
        "SCIWEAVE_EMAIL_ISSUER_URL": "http://127.0.0.1/issuer",
        "SCIWEAVE_EMAIL_RESOURCE_URL": "http://127.0.0.1/email-service",
        "SCIWEAVE_EMAIL_API_VERSION": API_VERSION,
        "SCIWEAVE_EMAIL_FROM_ADDRESS": FROM_ADDRESS,
        "SCIWEAVE_EMAIL_SMTP_HOST": SMTP_HOST,
        "SCIWEAVE_EMAIL_SMTP_PORT": str(SMTP_PORT),
        "SCIWEAVE_EMAIL_SMTP_USERNAME": SMTP_USERNAME,
        "SCIWEAVE_EMAIL_SMTP_PASSWORD": SMTP_PASSWORD,
        "SCIWEAVE_EMAIL_TOKENS_JSON": json.dumps(
            {"gateway": {"caller_id": "service:task-gateway", "caller_type": "service"}}
        ),
        "SCIWEAVE_EMAIL_RETRY_INITIAL_SECONDS": "1",
        "SCIWEAVE_EMAIL_RETRY_MULTIPLIER": "2",
        "SCIWEAVE_EMAIL_RETRY_MAX_SECONDS": "60",
        "SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS": "0.05",
        "SCIWEAVE_EMAIL_SENDING_TIMEOUT_SECONDS": "30",
    }
    values.update(overrides)
    for name, value in values.items():
        monkeypatch.setenv(name, value)


@contextmanager
def running_server(monkeypatch: pytest.MonkeyPatch, delivery_path: Path, audit_path: Path, sender, **overrides: str):
    _configure(monkeypatch, delivery_path, audit_path, **overrides)
    config = EmailServiceConfig.from_environment()
    app = create_email_server(config, FakeRecipientResolver(), sender).streamable_http_app()
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
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def statuses_until(mcp_url: str, notification_id: str, target: str, timeout: float = 8) -> list[dict]:
    seen: list[dict] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = call_tool(mcp_url, "get_notification_status", {"notification_id": notification_id})
        assert result.isError is False
        seen.append(body(result))
        if seen[-1]["delivery_status"] == target:
            return seen
        time.sleep(0.02)
    raise AssertionError(seen)


def test_transient_failure_retries_to_sent_as_the_same_notification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    delivery_path = tmp_path / "delivery.sqlite"
    audit_path = tmp_path / "audit.sqlite"
    sender = ScriptedSender([TransientSenderFailure(), None])
    with running_server(
        monkeypatch,
        delivery_path,
        audit_path,
        sender,
        SCIWEAVE_EMAIL_RETRY_INITIAL_SECONDS="1.5",
        SCIWEAVE_EMAIL_RETRY_MAX_SECONDS="1.5",
        SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS="0.05",
    ) as mcp_url:
        tool_names = {tool.name for tool in list_tools(mcp_url).tools}
        assert "retry_notification" not in tool_names
        accepted = body(call_tool(mcp_url, "send_notification", INTENT))
        assert accepted == {
            "notification_id": NOTIFICATION_ID,
            "acceptance": "accepted_for_delivery",
        }
        seen = statuses_until(mcp_url, NOTIFICATION_ID, "retryable", timeout=5)
        assert seen[-1] == {
            "notification_id": NOTIFICATION_ID,
            "delivery_status": "retryable",
            "attempt_count": 1,
            "error_summary": "transient_sender_failure",
        }
        sent = statuses_until(mcp_url, NOTIFICATION_ID, "sent", timeout=5)
        assert sent[-1] == {
            "notification_id": NOTIFICATION_ID,
            "delivery_status": "sent",
            "attempt_count": 2,
        }
        assert [message.notification_id for message in sender.calls] == [NOTIFICATION_ID, NOTIFICATION_ID]
        assert len(sender.calls) == 2


def _remains(mcp_url: str, notification_id: str, status: str, duration: float = 0.4) -> dict:
    deadline = time.time() + duration
    last = None
    while time.time() < deadline:
        result = call_tool(mcp_url, "get_notification_status", {"notification_id": notification_id})
        assert result.isError is False
        last = body(result)
        assert last["delivery_status"] == status
        assert last["notification_id"] == notification_id
        time.sleep(0.02)
    assert last is not None
    return last


def test_restart_continues_a_pending_notification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    delivery_path = tmp_path / "delivery.sqlite"
    audit_path = tmp_path / "audit.sqlite"
    stalled = ScriptedSender([])
    with running_server(
        monkeypatch,
        delivery_path,
        audit_path,
        stalled,
        SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS="60",
    ) as mcp_url:
        accepted = body(call_tool(mcp_url, "send_notification", INTENT))
        assert accepted["notification_id"] == NOTIFICATION_ID
        pending = _remains(mcp_url, NOTIFICATION_ID, "pending")
        assert pending["attempt_count"] == 0
    assert stalled.calls == []
    resumed = ScriptedSender([])
    with running_server(
        monkeypatch,
        delivery_path,
        audit_path,
        resumed,
        SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS="0.05",
    ) as mcp_url:
        sent = statuses_until(mcp_url, NOTIFICATION_ID, "sent")
    assert sent[-1] == {
        "notification_id": NOTIFICATION_ID,
        "delivery_status": "sent",
        "attempt_count": 1,
    }
    assert [message.notification_id for message in resumed.calls] == [NOTIFICATION_ID]
    assert stalled.calls == []


def test_restart_continues_timed_out_sending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    delivery_path = tmp_path / "delivery.sqlite"
    audit_path = tmp_path / "audit.sqlite"
    blocked = ScriptedSender([])
    blocked.gate.clear()
    try:
        with running_server(
            monkeypatch,
            delivery_path,
            audit_path,
            blocked,
            SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS="0.05",
            SCIWEAVE_EMAIL_SENDING_TIMEOUT_SECONDS="30",
        ) as mcp_url:
            body(call_tool(mcp_url, "send_notification", INTENT))
            sending = statuses_until(mcp_url, NOTIFICATION_ID, "sending")
            assert sending[-1]["attempt_count"] == 1
        resumed = ScriptedSender([])
        with running_server(
            monkeypatch,
            delivery_path,
            audit_path,
            resumed,
            SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS="0.05",
            SCIWEAVE_EMAIL_SENDING_TIMEOUT_SECONDS="0",
        ) as mcp_url:
            sent = statuses_until(mcp_url, NOTIFICATION_ID, "sent")
            assert sent[-1] == {
                "notification_id": NOTIFICATION_ID,
                "delivery_status": "sent",
                "attempt_count": 2,
            }
            assert [message.notification_id for message in resumed.calls] == [NOTIFICATION_ID]
            blocked.gate.set()
            stayed = _remains(mcp_url, NOTIFICATION_ID, "sent")
            assert stayed["notification_id"] == NOTIFICATION_ID
            assert [message.notification_id for message in resumed.calls] == [NOTIFICATION_ID]
    finally:
        blocked.gate.set()


def test_restart_continues_retryable_without_a_new_notification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    delivery_path = tmp_path / "delivery.sqlite"
    audit_path = tmp_path / "audit.sqlite"
    failing = ScriptedSender([], afterwards=TransientSenderFailure())
    with running_server(
        monkeypatch,
        delivery_path,
        audit_path,
        failing,
        SCIWEAVE_EMAIL_RETRY_INITIAL_SECONDS="30",
        SCIWEAVE_EMAIL_RETRY_MAX_SECONDS="30",
        SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS="0.05",
    ) as mcp_url:
        body(call_tool(mcp_url, "send_notification", INTENT))
        retryable = statuses_until(mcp_url, NOTIFICATION_ID, "retryable")
        assert retryable[-1] == {
            "notification_id": NOTIFICATION_ID,
            "delivery_status": "retryable",
            "attempt_count": 1,
            "error_summary": "transient_sender_failure",
        }
    resumed = ScriptedSender([])
    with running_server(
        monkeypatch,
        delivery_path,
        audit_path,
        resumed,
        SCIWEAVE_EMAIL_RETRY_INITIAL_SECONDS="30",
        SCIWEAVE_EMAIL_RETRY_MAX_SECONDS="30",
        SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS="0.05",
    ) as mcp_url:
        sent = statuses_until(mcp_url, NOTIFICATION_ID, "sent", timeout=3)
    assert sent[-1] == {
        "notification_id": NOTIFICATION_ID,
        "delivery_status": "sent",
        "attempt_count": 2,
    }
    assert [message.notification_id for message in resumed.calls] == [NOTIFICATION_ID]


def test_permanent_sender_failure_stays_queryable_and_is_not_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    delivery_path = tmp_path / "delivery.sqlite"
    audit_path = tmp_path / "audit.sqlite"
    sender = ScriptedSender([PermanentSenderFailure()])
    with running_server(
        monkeypatch,
        delivery_path,
        audit_path,
        sender,
        SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS="0.05",
    ) as mcp_url:
        body(call_tool(mcp_url, "send_notification", INTENT))
        failed = statuses_until(mcp_url, NOTIFICATION_ID, "permanent_failure")
        assert failed[-1] == {
            "notification_id": NOTIFICATION_ID,
            "delivery_status": "permanent_failure",
            "attempt_count": 1,
            "error_summary": "permanent_sender_failure",
        }
        assert len(sender.calls) == 1
    resumed = ScriptedSender([])
    with running_server(
        monkeypatch,
        delivery_path,
        audit_path,
        resumed,
        SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS="0.05",
        SCIWEAVE_EMAIL_SENDING_TIMEOUT_SECONDS="0",
    ) as mcp_url:
        stayed = _remains(mcp_url, NOTIFICATION_ID, "permanent_failure")
    assert stayed == {
        "notification_id": NOTIFICATION_ID,
        "delivery_status": "permanent_failure",
        "attempt_count": 1,
        "error_summary": "permanent_sender_failure",
    }
    assert resumed.calls == []


def test_non_retryable_content_stays_invalid_after_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    delivery_path = tmp_path / "delivery.sqlite"
    audit_path = tmp_path / "audit.sqlite"
    sender = ScriptedSender([NonRetryableContentError()])
    with running_server(
        monkeypatch,
        delivery_path,
        audit_path,
        sender,
        SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS="0.05",
    ) as mcp_url:
        body(call_tool(mcp_url, "send_notification", INTENT))
        invalid = statuses_until(mcp_url, NOTIFICATION_ID, "invalid")
        assert invalid[-1] == {
            "notification_id": NOTIFICATION_ID,
            "delivery_status": "invalid",
            "attempt_count": 1,
            "error_summary": "non_retryable_content",
        }
        assert len(sender.calls) == 1
    resumed = ScriptedSender([])
    with running_server(
        monkeypatch,
        delivery_path,
        audit_path,
        resumed,
        SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS="0.05",
        SCIWEAVE_EMAIL_SENDING_TIMEOUT_SECONDS="0",
    ) as mcp_url:
        stayed = _remains(mcp_url, NOTIFICATION_ID, "invalid")
    assert stayed == {
        "notification_id": NOTIFICATION_ID,
        "delivery_status": "invalid",
        "attempt_count": 1,
        "error_summary": "non_retryable_content",
    }
    assert resumed.calls == []


RESEND_ID = "ntf-retry-2"
RESEND_DEDUPE_KEY = "draft-ready:candidate-9:manual"


def test_manual_resend_uses_a_new_notification_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    delivery_path = tmp_path / "delivery.sqlite"
    audit_path = tmp_path / "audit.sqlite"
    sender = ScriptedSender([PermanentSenderFailure()])
    with running_server(
        monkeypatch,
        delivery_path,
        audit_path,
        sender,
        SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS="0.05",
    ) as mcp_url:
        tool_names = {tool.name for tool in list_tools(mcp_url).tools}
        assert tool_names == {"send_notification", "get_notification_status", "health"}
        body(call_tool(mcp_url, "send_notification", INTENT))
        failed = statuses_until(mcp_url, NOTIFICATION_ID, "permanent_failure")
        assert failed[-1]["delivery_status"] == "permanent_failure"
        accepted = body(
            call_tool(
                mcp_url,
                "send_notification",
                {**INTENT, "notification_id": RESEND_ID, "dedupe_key": RESEND_DEDUPE_KEY},
            )
        )
        assert accepted == {
            "notification_id": RESEND_ID,
            "acceptance": "accepted_for_delivery",
        }
        sent = statuses_until(mcp_url, RESEND_ID, "sent")
        assert sent[-1] == {
            "notification_id": RESEND_ID,
            "delivery_status": "sent",
            "attempt_count": 1,
        }
        original = body(call_tool(mcp_url, "get_notification_status", {"notification_id": NOTIFICATION_ID}))
        assert original == {
            "notification_id": NOTIFICATION_ID,
            "delivery_status": "permanent_failure",
            "attempt_count": 1,
            "error_summary": "permanent_sender_failure",
        }
    assert [message.notification_id for message in sender.calls] == [NOTIFICATION_ID, RESEND_ID]
