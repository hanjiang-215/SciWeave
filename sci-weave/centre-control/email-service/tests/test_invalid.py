import json
import sqlite3
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from email_service.config import EmailServiceConfig
from email_service.ports import EmailServiceError
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
    _Server,
    body,
    call_tool,
    error_code,
)


class ScriptedRecipientResolver:
    def __init__(self) -> None:
        self.addresses = {PRINCIPAL_ID: RESOLVED_EMAIL}
        self.failures: dict[str, EmailServiceError] = {}

    def resolve(self, principal_id: str) -> str:
        failure = self.failures.get(principal_id)
        if failure is not None:
            raise failure
        try:
            return self.addresses[principal_id]
        except KeyError:
            raise EmailServiceError("contact_missing") from None


class FakeSender:
    def __init__(self) -> None:
        self.sent: list = []

    def send(self, message) -> None:
        self.sent.append(message)


@pytest.fixture
def invalid_mcp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
    monkeypatch.setenv("SCIWEAVE_EMAIL_RETRY_INITIAL_SECONDS", "1")
    monkeypatch.setenv("SCIWEAVE_EMAIL_RETRY_MULTIPLIER", "2")
    monkeypatch.setenv("SCIWEAVE_EMAIL_RETRY_MAX_SECONDS", "60")
    monkeypatch.setenv("SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS", "0.05")
    monkeypatch.setenv("SCIWEAVE_EMAIL_SENDING_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("SCIWEAVE_EMAIL_FROM_ADDRESS", FROM_ADDRESS)
    monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_HOST", SMTP_HOST)
    monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_PORT", str(SMTP_PORT))
    monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_USERNAME", SMTP_USERNAME)
    monkeypatch.setenv("SCIWEAVE_EMAIL_SMTP_PASSWORD", SMTP_PASSWORD)
    monkeypatch.setenv(
        "SCIWEAVE_EMAIL_TOKENS_JSON",
        json.dumps({"gateway": {"caller_id": "service:task-gateway", "caller_type": "service"}}),
    )
    monkeypatch.setenv("SCIWEAVE_EMAIL_RETRY_INITIAL_SECONDS", "1")
    monkeypatch.setenv("SCIWEAVE_EMAIL_RETRY_MULTIPLIER", "2")
    monkeypatch.setenv("SCIWEAVE_EMAIL_RETRY_MAX_SECONDS", "60")
    monkeypatch.setenv("SCIWEAVE_EMAIL_DISPATCH_POLL_SECONDS", "0.05")
    monkeypatch.setenv("SCIWEAVE_EMAIL_SENDING_TIMEOUT_SECONDS", "30")
    config = EmailServiceConfig.from_environment()
    resolver = ScriptedRecipientResolver()
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
            "delivery_path": delivery_path,
            "resolver": resolver,
            "sender": sender,
        }
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _intent(**overrides) -> dict:
    payload = {
        "notification_id": NOTIFICATION_ID,
        "dedupe_key": INTENT["dedupe_key"],
        "notification_kind": INTENT["notification_kind"],
        "recipients": [{"principal_id": PRINCIPAL_ID}],
        "subject": SUBJECT,
        "body": BODY,
        "related": dict(INTENT["related"]),
        "schema_version": INTENT["schema_version"],
    }
    payload.update(overrides)
    return payload


def _status(mcp: dict, notification_id: str) -> dict:
    return body(call_tool(mcp, "gateway", "get_notification_status", {"notification_id": notification_id}))


def test_unconfigured_notification_kind_is_queryable_and_not_sent(invalid_mcp):
    notification_id = "ntf-unknown-kind"
    result = call_tool(
        invalid_mcp,
        "gateway",
        "send_notification",
        _intent(notification_id=notification_id, notification_kind="marketing_blast"),
    )
    assert error_code(result) == "invalid"
    assert invalid_mcp["sender"].sent == []
    status = _status(invalid_mcp, notification_id)
    assert status == {
        "notification_id": notification_id,
        "delivery_status": "invalid",
        "attempt_count": 0,
        "error_summary": "invalid",
        "recipients": [
            {
                "principal_id": PRINCIPAL_ID,
                "status": "pending",
                "attempt_count": 0,
                "error_summary": None,
            }
        ],
    }
    time.sleep(0.3)
    assert _status(invalid_mcp, notification_id)["delivery_status"] == "invalid"
    assert _status(invalid_mcp, notification_id)["attempt_count"] == 0
    assert invalid_mcp["sender"].sent == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"subject": ""},
        {"body": ""},
        {"dedupe_key": ""},
        {"schema_version": ""},
        {"recipients": []},
        {"recipients": [{}]},
        {"subject": None},
    ],
)
def test_missing_required_fields_are_queryable_invalid_and_not_sent(invalid_mcp, overrides):
    notification_id = "ntf-missing-" + "-".join(overrides)
    result = call_tool(
        invalid_mcp,
        "gateway",
        "send_notification",
        _intent(notification_id=notification_id, **overrides),
    )
    assert error_code(result) == "invalid"
    assert BODY not in result.content[0].text
    assert invalid_mcp["sender"].sent == []
    assert _status(invalid_mcp, notification_id)["delivery_status"] == "invalid"
    assert _status(invalid_mcp, notification_id)["attempt_count"] == 0


def test_omitted_required_field_is_queryable_invalid_and_not_sent(invalid_mcp):
    notification_id = "ntf-omitted-subject"
    payload = _intent(notification_id=notification_id)
    del payload["subject"]
    result = call_tool(invalid_mcp, "gateway", "send_notification", payload)
    assert error_code(result) == "invalid"
    assert invalid_mcp["sender"].sent == []
    assert _status(invalid_mcp, notification_id) == {
        "notification_id": notification_id,
        "delivery_status": "invalid",
        "attempt_count": 0,
        "error_summary": "invalid",
        "recipients": [
            {
                "principal_id": PRINCIPAL_ID,
                "status": "pending",
                "attempt_count": 0,
                "error_summary": None,
            }
        ],
    }


def test_html_body_is_queryable_invalid_and_not_sent(invalid_mcp):
    notification_id = "ntf-html"
    result = call_tool(
        invalid_mcp,
        "gateway",
        "send_notification",
        _intent(notification_id=notification_id, body="<p>Please review the draft.</p>"),
    )
    assert error_code(result) == "invalid"
    assert "<p>" not in result.content[0].text
    assert invalid_mcp["sender"].sent == []
    assert _status(invalid_mcp, notification_id)["delivery_status"] == "invalid"


def test_html_subject_is_queryable_invalid_and_not_sent(invalid_mcp):
    notification_id = "ntf-html-subject"
    result = call_tool(
        invalid_mcp,
        "gateway",
        "send_notification",
        _intent(notification_id=notification_id, subject="<b>Draft ready</b>"),
    )
    assert error_code(result) == "invalid"
    assert invalid_mcp["sender"].sent == []
    assert _status(invalid_mcp, notification_id)["delivery_status"] == "invalid"


def test_unsupported_schema_version_is_queryable_invalid_and_not_sent(invalid_mcp):
    notification_id = "ntf-schema-2"
    result = call_tool(
        invalid_mcp,
        "gateway",
        "send_notification",
        _intent(notification_id=notification_id, schema_version="2"),
    )
    assert error_code(result) == "invalid"
    assert invalid_mcp["sender"].sent == []
    assert _status(invalid_mcp, notification_id)["delivery_status"] == "invalid"


def test_over_limit_subject_is_queryable_invalid_and_not_sent(invalid_mcp):
    notification_id = "ntf-long-subject"
    result = call_tool(
        invalid_mcp,
        "gateway",
        "send_notification",
        _intent(notification_id=notification_id, subject="S" * 300),
    )
    assert error_code(result) == "invalid"
    assert invalid_mcp["sender"].sent == []
    assert _status(invalid_mcp, notification_id)["delivery_status"] == "invalid"


def test_attachment_is_queryable_invalid_and_not_sent(invalid_mcp):
    notification_id = "ntf-attachment"
    payload = _intent(notification_id=notification_id)
    payload["attachments"] = [{"filename": "draft.txt", "content": "not-a-mail-part"}]
    result = call_tool(invalid_mcp, "gateway", "send_notification", payload)
    assert error_code(result) == "invalid"
    assert invalid_mcp["sender"].sent == []
    assert _status(invalid_mcp, notification_id)["delivery_status"] == "invalid"
    assert _status(invalid_mcp, notification_id)["attempt_count"] == 0


def test_over_limit_body_is_queryable_invalid_and_not_sent(invalid_mcp):
    notification_id = "ntf-long-body"
    result = call_tool(
        invalid_mcp,
        "gateway",
        "send_notification",
        _intent(notification_id=notification_id, body="A" * 10000),
    )
    assert error_code(result) == "invalid"
    assert invalid_mcp["sender"].sent == []
    assert _status(invalid_mcp, notification_id)["delivery_status"] == "invalid"


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (EmailServiceError("contact_missing"), "contact_missing"),
        (EmailServiceError("contact_disabled"), "contact_disabled"),
        (EmailServiceError("principal_not_found"), "principal_not_found"),
    ],
)
def test_unusable_contact_is_permanent_and_not_sent(invalid_mcp, failure, code):
    notification_id = "ntf-" + code.replace("_", "-")
    invalid_mcp["resolver"].failures[PRINCIPAL_ID] = failure
    result = call_tool(
        invalid_mcp,
        "gateway",
        "send_notification",
        _intent(notification_id=notification_id),
    )
    assert error_code(result) == code
    assert RESOLVED_EMAIL not in result.content[0].text
    assert invalid_mcp["sender"].sent == []
    status = _status(invalid_mcp, notification_id)
    assert status == {
        "notification_id": notification_id,
        "delivery_status": "permanent_failure",
        "attempt_count": 0,
        "error_summary": code,
        "recipients": [
            {
                "principal_id": PRINCIPAL_ID,
                "status": "pending",
                "attempt_count": 0,
                "error_summary": None,
            }
        ],
    }
    time.sleep(0.3)
    assert _status(invalid_mcp, notification_id)["delivery_status"] == "permanent_failure"
    assert invalid_mcp["sender"].sent == []


def test_mismatched_contact_address_is_permanent_and_not_sent(invalid_mcp):
    notification_id = "ntf-address-mismatch"
    result = call_tool(
        invalid_mcp,
        "gateway",
        "send_notification",
        _intent(
            notification_id=notification_id,
            recipients=[{"principal_id": PRINCIPAL_ID, "email": "other@example.test"}],
        ),
    )
    assert error_code(result) == "address_mismatch"
    assert "other@example.test" not in result.content[0].text
    assert invalid_mcp["sender"].sent == []
    assert _status(invalid_mcp, notification_id)["delivery_status"] == "permanent_failure"
    assert _status(invalid_mcp, notification_id)["attempt_count"] == 0


def test_caller_sender_overrides_are_rejected_and_mailbox_stays_configured(invalid_mcp):
    rejected_id = "ntf-sender-override"
    payload = _intent(notification_id=rejected_id, dedupe_key="override-1")
    payload["from_address"] = "attacker@example.test"
    payload["smtp_host"] = "smtp.attacker.test"
    payload["smtp_password"] = "caller-supplied-secret"
    rejected = call_tool(invalid_mcp, "gateway", "send_notification", payload)
    assert error_code(rejected) == "invalid"
    assert "attacker@example.test" not in rejected.content[0].text
    assert "caller-supplied-secret" not in rejected.content[0].text
    assert invalid_mcp["sender"].sent == []
    assert _status(invalid_mcp, rejected_id)["delivery_status"] == "invalid"

    accepted_id = "ntf-after-override"
    accepted = body(
        call_tool(
            invalid_mcp,
            "gateway",
            "send_notification",
            _intent(notification_id=accepted_id, dedupe_key="after-override"),
        )
    )
    assert accepted == {
        "notification_id": accepted_id,
        "acceptance": "accepted_for_delivery",
    }
    deadline = time.time() + 5
    status = None
    while time.time() < deadline:
        status = _status(invalid_mcp, accepted_id)
        if status.get("delivery_status") == "sent":
            break
        time.sleep(0.05)
    assert status == {
        "notification_id": accepted_id,
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
    assert len(invalid_mcp["sender"].sent) == 1
    message = invalid_mcp["sender"].sent[0]
    assert message.from_address == FROM_ADDRESS
    assert message.smtp_host == SMTP_HOST
    assert message.smtp_port == SMTP_PORT
    assert message.smtp_username == SMTP_USERNAME
    assert message.smtp_password == SMTP_PASSWORD
    assert message.to_address == RESOLVED_EMAIL


def test_matching_contact_address_is_still_delivered(invalid_mcp):
    notification_id = "ntf-address-match"
    accepted = body(
        call_tool(
            invalid_mcp,
            "gateway",
            "send_notification",
            _intent(
                notification_id=notification_id,
                dedupe_key="address-match",
                recipients=[{"principal_id": PRINCIPAL_ID, "email": RESOLVED_EMAIL}],
            ),
        )
    )
    assert accepted == {
        "notification_id": notification_id,
        "acceptance": "accepted_for_delivery",
    }
    deadline = time.time() + 5
    status = None
    while time.time() < deadline:
        status = _status(invalid_mcp, notification_id)
        if status.get("delivery_status") == "sent":
            break
        time.sleep(0.05)
    assert status["delivery_status"] == "sent"
    assert len(invalid_mcp["sender"].sent) == 1
    assert invalid_mcp["sender"].sent[0].to_address == RESOLVED_EMAIL
    assert invalid_mcp["sender"].sent[0].from_address == FROM_ADDRESS


def test_storage_unavailable_does_not_send(invalid_mcp):
    lock = sqlite3.connect(invalid_mcp["delivery_path"])
    lock.execute("BEGIN EXCLUSIVE")
    try:
        result = call_tool(invalid_mcp, "gateway", "send_notification", _intent(notification_id="ntf-storage"))
        assert error_code(result) == "storage_unavailable"
        assert invalid_mcp["sender"].sent == []
    finally:
        lock.rollback()
        lock.close()
    hidden = call_tool(
        invalid_mcp,
        "gateway",
        "get_notification_status",
        {"notification_id": "ntf-storage"},
    )
    assert error_code(hidden) == "denied"
    assert invalid_mcp["sender"].sent == []
