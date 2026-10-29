import json
import sqlite3
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

from email_service.config import EmailServiceConfig
from email_service.ports import PermanentSenderFailure, UnboundMailSender
from email_service.server import create_email_server
from test_http import (
    API_VERSION,
    BODY,
    FROM_ADDRESS,
    INTENT,
    NOTIFICATION_ID,
    PRINCIPAL_ID,
    RESOLVED_EMAIL,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USERNAME,
    SUBJECT,
    FakeRecipientResolver,
    _Server,
    body,
    call_tool,
    error_code,
)


EXTRA_KIND = "lab_notice"
GATEWAY_ID = "service:task-gateway"
OTHER_ID = "service:centre-workflow"
RAW_SEND_ERROR = f"smtp 550 rejected {SMTP_PASSWORD} body={BODY}"


class LeakyPermanentFailure(PermanentSenderFailure):
    def __init__(self) -> None:
        Exception.__init__(self, RAW_SEND_ERROR)
        self.code = "permanent_sender_failure"


class FakeSender:
    def __init__(self, failure: Exception | None = None) -> None:
        self.sent: list = []
        self.failure = failure

    def send(self, message) -> None:
        if self.failure is not None:
            raise self.failure
        self.sent.append(message)


def _start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    sender: FakeSender,
    mailbox: bool = True,
    allowlist: dict[str, list[str]] | None = None,
):
    delivery_path = tmp_path / "delivery.sqlite"
    audit_path = tmp_path / "audit.sqlite"
    monkeypatch.setenv("SCIWEAVE_EMAIL_SQLITE_PATH", str(delivery_path))
    monkeypatch.setenv("SCIWEAVE_AUDIT_SQLITE_PATH", str(audit_path))
    monkeypatch.setenv("SCIWEAVE_EMAIL_HOST", "127.0.0.1")
    monkeypatch.setenv("SCIWEAVE_EMAIL_PORT", "0")
    monkeypatch.setenv("SCIWEAVE_EMAIL_ISSUER_URL", "http://127.0.0.1/issuer")
    monkeypatch.setenv("SCIWEAVE_EMAIL_RESOURCE_URL", "http://127.0.0.1/email-service")
    monkeypatch.setenv("SCIWEAVE_EMAIL_API_VERSION", API_VERSION)
    monkeypatch.setenv("SCIWEAVE_EMAIL_REGISTRY_URL", "http://registry.test/mcp")
    monkeypatch.setenv("SCIWEAVE_EMAIL_REGISTRY_TOKEN", "registry-token")
    monkeypatch.setenv("SCIWEAVE_EMAIL_REGISTRY_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS", "0.05")
    monkeypatch.setenv("SCIWEAVE_EMAIL_RETRY_INITIAL_SECONDS", "30")
    monkeypatch.setenv("SCIWEAVE_EMAIL_RETRY_MULTIPLIER", "2")
    monkeypatch.setenv("SCIWEAVE_EMAIL_RETRY_MAX_SECONDS", "60")
    monkeypatch.setenv("SCIWEAVE_EMAIL_SENDING_TIMEOUT_SECONDS", "30")
    mailbox_names = (
        "SCIWEAVE_EMAIL_FROM_ADDRESS",
        "SCIWEAVE_EMAIL_SMTP_HOST",
        "SCIWEAVE_EMAIL_SMTP_PORT",
        "SCIWEAVE_EMAIL_SMTP_USERNAME",
        "SCIWEAVE_EMAIL_SMTP_PASSWORD",
        "SCIWEAVE_EMAIL_SMTP_SECURITY",
    )
    if mailbox:
        monkeypatch.setenv("SCIWEAVE_EMAIL_FROM_ADDRESS", FROM_ADDRESS)
        monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_HOST", SMTP_HOST)
        monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_PORT", str(SMTP_PORT))
        monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_USERNAME", SMTP_USERNAME)
        monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_PASSWORD", SMTP_PASSWORD)
        monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_SECURITY", "starttls")
    else:
        for name in mailbox_names:
            monkeypatch.delenv(name, raising=False)
    if allowlist is None:
        monkeypatch.delenv("SCIWEAVE_EMAIL_KIND_ALLOWLIST_JSON", raising=False)
    else:
        monkeypatch.setenv("SCIWEAVE_EMAIL_KIND_ALLOWLIST_JSON", json.dumps(allowlist))
    monkeypatch.setenv(
        "SCIWEAVE_EMAIL_TOKENS_JSON",
        json.dumps(
            {
                "gateway": {"caller_id": GATEWAY_ID, "caller_type": "service"},
                "other": {"caller_id": OTHER_ID, "caller_type": "service"},
                "ops": {"caller_id": "human:oncall", "caller_type": "operator"},
            }
        ),
    )
    config = EmailServiceConfig.from_environment()
    app = create_email_server(
        config,
        FakeRecipientResolver({PRINCIPAL_ID: RESOLVED_EMAIL}),
        sender,
    ).streamable_http_app()
    server = _Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("email-service did not start")
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    return server, thread, {
        "mcp_url": f"http://127.0.0.1:{port}/mcp",
        "health_url": f"http://127.0.0.1:{port}/health",
        "audit_path": audit_path,
        "sender": sender,
    }


def _stop(server, thread) -> None:
    server.should_exit = True
    thread.join(timeout=5)


def _intent(**overrides) -> dict:
    payload = dict(INTENT)
    payload["recipients"] = [{"principal_id": PRINCIPAL_ID}]
    payload["related"] = dict(INTENT["related"])
    payload.update(overrides)
    return payload


def _wait_status(mcp: dict, token: str, notification_id: str, delivery_status: str) -> dict:
    deadline = time.time() + 5
    last = None
    while time.time() < deadline:
        result = call_tool(mcp, token, "get_notification_status", {"notification_id": notification_id})
        if result.isError is False:
            last = body(result)
            if last.get("delivery_status") == delivery_status:
                return last
        time.sleep(0.05)
    raise AssertionError(last)


def test_public_health_is_not_configured_when_mailbox_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    server, thread, mcp = _start(tmp_path, monkeypatch, sender=FakeSender(), mailbox=False)
    try:
        probe = httpx.get(mcp["health_url"])
    finally:
        _stop(server, thread)
    assert probe.status_code == 503
    assert probe.json() == {
        "status": "not_configured",
        "service": "email-service",
        "api_version": API_VERSION,
    }
    assert SMTP_PASSWORD not in probe.text


def test_health_refuses_to_look_ready_with_an_unbound_sender(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """ai4-ceqq: a configured mailbox plus an unbound sender used to read ready."""
    server, thread, mcp = _start(tmp_path, monkeypatch, sender=UnboundMailSender())
    try:
        report = body(call_tool(mcp, "gateway", "health"))
        probe = httpx.get(mcp["health_url"], timeout=5)
    finally:
        _stop(server, thread)

    assert report["components"]["sender"] == "not_bound"
    assert report["components"]["mailbox"] == "ready"
    assert report["status"] == "not_configured"
    assert probe.status_code == 503
    assert probe.json()["status"] == "not_configured"


def test_authenticated_health_is_degraded_when_audit_is_down(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    server, thread, mcp = _start(tmp_path, monkeypatch, sender=FakeSender())
    try:
        audit = sqlite3.connect(mcp["audit_path"])
        try:
            audit.execute("DROP TABLE audit_call")
            audit.commit()
        finally:
            audit.close()
        report = body(call_tool(mcp, "gateway", "health"))
    finally:
        _stop(server, thread)
    assert report == {
        "status": "degraded",
        "components": {
            "delivery_store": "ready",
            "audit": "unavailable",
            "mailbox": "ready",
            "sender": "ready",
        },
    }
    encoded = json.dumps(report)
    assert SMTP_PASSWORD not in encoded
    assert BODY not in encoded


def test_operator_can_read_another_callers_status_without_the_body(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    server, thread, mcp = _start(tmp_path, monkeypatch, sender=FakeSender())
    try:
        accepted = body(call_tool(mcp, "gateway", "send_notification", _intent()))
        assert accepted["acceptance"] == "accepted_for_delivery"
        seen = _wait_status(mcp, "ops", NOTIFICATION_ID, "sent")
        hidden = call_tool(mcp, "other", "get_notification_status", {"notification_id": NOTIFICATION_ID})
    finally:
        _stop(server, thread)
    assert seen == {
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
    assert error_code(hidden) == "denied"
    assert BODY not in json.dumps(seen)
    assert SUBJECT not in json.dumps(seen)
    assert SMTP_PASSWORD not in json.dumps(seen)
    assert BODY not in hidden.content[0].text


@pytest.mark.parametrize(
    ("subject", "body_text"),
    [
        ("bad\x00subject", BODY),
        (SUBJECT, "bad\x1bbody"),
        (SUBJECT, "bad\x7fbody"),
    ],
)
def test_control_characters_are_invalid_and_not_sent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    subject: str,
    body_text: str,
):
    sender = FakeSender()
    server, thread, mcp = _start(tmp_path, monkeypatch, sender=sender)
    notification_id = "ntf-charset-" + str(ord(next(char for char in subject + body_text if ord(char) < 32 or char == "\x7f")))
    try:
        result = call_tool(
            mcp,
            "gateway",
            "send_notification",
            _intent(notification_id=notification_id, dedupe_key=notification_id, subject=subject, body=body_text),
        )
        status = body(call_tool(mcp, "gateway", "get_notification_status", {"notification_id": notification_id}))
    finally:
        _stop(server, thread)
    assert error_code(result) == "invalid"
    assert sender.sent == []
    assert status["delivery_status"] == "invalid"
    assert status["attempt_count"] == 0
    encoded = json.dumps(status)
    assert subject not in encoded
    assert body_text not in encoded
    assert "\x00" not in encoded


def test_newline_tab_and_unicode_are_still_delivered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sender = FakeSender()
    server, thread, mcp = _start(tmp_path, monkeypatch, sender=sender)
    subject = "就绪\t请看"
    body_text = "第一行\n第二行\r\n\t缩进"
    try:
        accepted = body(
            call_tool(
                mcp,
                "gateway",
                "send_notification",
                _intent(
                    notification_id="ntf-charset-ok",
                    dedupe_key="charset-ok",
                    subject=subject,
                    body=body_text,
                ),
            )
        )
        status = _wait_status(mcp, "gateway", "ntf-charset-ok", "sent")
    finally:
        _stop(server, thread)
    assert accepted["acceptance"] == "accepted_for_delivery"
    assert status["delivery_status"] == "sent"
    assert len(sender.sent) == 1
    assert sender.sent[0].subject == subject
    assert sender.sent[0].body == body_text


def test_extra_kind_is_accepted_only_for_the_allowlisted_caller(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sender = FakeSender()
    server, thread, mcp = _start(
        tmp_path,
        monkeypatch,
        sender=sender,
        allowlist={GATEWAY_ID: [EXTRA_KIND]},
    )
    try:
        refused = call_tool(
            mcp,
            "other",
            "send_notification",
            _intent(notification_id="ntf-extra-other", dedupe_key="extra-other", notification_kind=EXTRA_KIND),
        )
        unknown = call_tool(
            mcp,
            "gateway",
            "send_notification",
            _intent(notification_id="ntf-extra-unknown", dedupe_key="extra-unknown", notification_kind="marketing_blast"),
        )
        accepted = body(
            call_tool(
                mcp,
                "gateway",
                "send_notification",
                _intent(notification_id="ntf-extra-ok", dedupe_key="extra-ok", notification_kind=EXTRA_KIND),
            )
        )
        status = _wait_status(mcp, "gateway", "ntf-extra-ok", "sent")
    finally:
        _stop(server, thread)
    assert error_code(refused) == "invalid"
    assert error_code(unknown) == "invalid"
    assert accepted == {"notification_id": "ntf-extra-ok", "acceptance": "accepted_for_delivery"}
    assert status["delivery_status"] == "sent"
    assert [message.notification_id for message in sender.sent] == ["ntf-extra-ok"]


def test_failed_status_summary_omits_body_credentials_and_raw_send_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    sender = FakeSender(failure=LeakyPermanentFailure())
    server, thread, mcp = _start(tmp_path, monkeypatch, sender=sender)
    try:
        body(call_tool(mcp, "gateway", "send_notification", _intent()))
        status = _wait_status(mcp, "gateway", NOTIFICATION_ID, "permanent_failure")
    finally:
        _stop(server, thread)
    assert status == {
        "notification_id": NOTIFICATION_ID,
        "delivery_status": "permanent_failure",
        "attempt_count": 1,
        "error_summary": "permanent_sender_failure",
        "recipients": [
            {
                "principal_id": PRINCIPAL_ID,
                "status": "permanent_failure",
                "attempt_count": 1,
                "error_summary": "permanent_sender_failure",
            }
        ],
    }
    encoded = json.dumps(status)
    assert BODY not in encoded
    assert SMTP_PASSWORD not in encoded
    assert RAW_SEND_ERROR not in encoded
    assert "550" not in encoded


def test_unexpected_sender_error_is_named_but_not_leaked_in_the_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """ai4-onvr: an unanticipated sender exception must leave a usable trace."""
    sender = FakeSender(failure=RuntimeError(f"smtp exploded {SMTP_PASSWORD}"))
    server, thread, mcp = _start(tmp_path, monkeypatch, sender=sender)
    try:
        body(call_tool(mcp, "gateway", "send_notification", _intent()))
        status = _wait_status(mcp, "gateway", NOTIFICATION_ID, "permanent_failure")
    finally:
        _stop(server, thread)
    assert status["error_summary"] == "sender_failure:RuntimeError"
    assert status["recipients"][0]["error_summary"] == "sender_failure:RuntimeError"
    assert SMTP_PASSWORD not in json.dumps(status)
