from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .config import MailboxSettings
from .ports import (
    NON_RETRYABLE_RECIPIENT_ERRORS,
    EmailServiceError,
    MailSender,
    OutboundMail,
    RecipientResolver,
)


@dataclass(frozen=True)
class Caller:
    caller_id: str
    caller_type: str


CONFIGURED_NOTIFICATION_KINDS = frozenset(
    {
        "draft_ready",
        "execution_question",
        "execution_failed",
        "revision_draft_ready",
        "revision_failed",
        "prereview_completed",
        "candidate_revision_requested",
        "candidate_rejected",
        "workflow_binding_required",
        "workflow_load_failed",
        "workflow_start_failed",
        "agent_unavailable",
        "task_terminal_summary",
    }
)
SUBJECT_MAX_CHARS = 200
BODY_MAX_CHARS = 4000
_HTML_MARKUP = re.compile(r"<\s*/?\s*[A-Za-z!]")
_SENSITIVE_CONTENT = re.compile(
    r"(?i)(?:\b(?:password|passwd|secret|api[_-]?key|token|credential)s?\b\s*[:=]|bearer\s+\S+|traceback \(most recent call last\)|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)


class EmailDeliveryService:
    def __init__(
        self,
        connection: sqlite3.Connection,
        resolver: RecipientResolver,
        sender: MailSender,
        mailbox: MailboxSettings,
        lock: threading.RLock,
    ) -> None:
        self.conn = connection
        self.resolver = resolver
        self.sender = sender
        self.mailbox = mailbox
        self.lock = lock
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS notification_delivery (
              notification_id TEXT PRIMARY KEY,
              caller_id TEXT NOT NULL,
              dedupe_key TEXT NOT NULL,
              notification_kind TEXT NOT NULL,
              subject TEXT NOT NULL,
              body TEXT NOT NULL,
              related_json TEXT NOT NULL,
              schema_version TEXT NOT NULL,
              recipients_json TEXT NOT NULL,
              delivery_status TEXT NOT NULL,
              attempt_count INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def accept(self, caller: Caller, intent: dict[str, Any]) -> dict[str, str]:
        try:
            existing = self.conn.execute(
                """
                SELECT notification_id, delivery_status, notification_kind, subject, body, recipients_json
                FROM notification_delivery
                WHERE dedupe_key = ?
                """,
                (intent["dedupe_key"],),
            ).fetchone()
        except sqlite3.Error:
            raise EmailServiceError("storage_unavailable") from None
        if existing is not None:
            if not _same_notification(existing, intent):
                raise EmailServiceError("idempotency_conflict")
            return {
                "notification_id": existing["notification_id"],
                "delivery_status": existing["delivery_status"],
            }
        if _content_problem(intent):
            self.record_invalid(caller, intent)
        notification_id = intent["notification_id"]
        try:
            resolved = [_resolved_recipient(self.resolver, recipient) for recipient in intent["recipients"]]
        except EmailServiceError as exc:
            if exc.code not in NON_RETRYABLE_RECIPIENT_ERRORS:
                raise
            self._record_terminal(caller, intent, "permanent_failure")
            raise
        now = _now()
        try:
            self.conn.execute(
                """
                INSERT INTO notification_delivery (
                  notification_id, caller_id, dedupe_key, notification_kind, subject, body,
                  related_json, schema_version, recipients_json, delivery_status, attempt_count,
                  created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)
                """,
                (
                    notification_id,
                    caller.caller_id,
                    intent["dedupe_key"],
                    intent["notification_kind"],
                    intent["subject"],
                    intent["body"],
                    json.dumps(intent["related"], ensure_ascii=False, sort_keys=True),
                    intent["schema_version"],
                    json.dumps(resolved, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            self.conn.commit()
        except sqlite3.Error:
            self.conn.rollback()
            raise EmailServiceError("storage_unavailable") from None
        threading.Thread(target=self._dispatch, args=(notification_id,), daemon=True).start()
        return {"notification_id": notification_id, "acceptance": "accepted_for_delivery"}

    def record_invalid(self, caller: Caller, intent: dict[str, Any]) -> None:
        notification_id = intent.get("notification_id")
        if not isinstance(notification_id, str) or not notification_id.strip():
            raise EmailServiceError("invalid")
        self._record_terminal(caller, intent, "invalid")
        raise EmailServiceError("invalid")

    def _record_terminal(self, caller: Caller, intent: dict[str, Any], delivery_status: str) -> None:
        now = _now()
        related = intent.get("related")
        recipients = intent.get("recipients")
        subject = _text(intent.get("subject"))
        body = _text(intent.get("body"))
        if _contains_sensitive(subject) or _contains_sensitive(body):
            subject = ""
            body = ""
        try:
            self.conn.execute(
                """
                INSERT INTO notification_delivery (
                  notification_id, caller_id, dedupe_key, notification_kind, subject, body,
                  related_json, schema_version, recipients_json, delivery_status, attempt_count,
                  created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    intent["notification_id"],
                    caller.caller_id,
                    _text(intent.get("dedupe_key")),
                    _text(intent.get("notification_kind")),
                    subject,
                    body,
                    json.dumps(related if isinstance(related, dict) else {}, ensure_ascii=False, sort_keys=True),
                    _text(intent.get("schema_version")),
                    json.dumps(recipients if isinstance(recipients, list) else [], ensure_ascii=False),
                    delivery_status,
                    now,
                    now,
                ),
            )
            self.conn.commit()
        except sqlite3.Error:
            self.conn.rollback()
            raise EmailServiceError("storage_unavailable") from None

    def status(self, caller: Caller, notification_id: str) -> dict[str, Any]:
        try:
            row = self.conn.execute(
                """
                SELECT caller_id, delivery_status, attempt_count
                FROM notification_delivery
                WHERE notification_id = ?
                """,
                (notification_id,),
            ).fetchone()
        except sqlite3.Error:
            raise EmailServiceError("storage_unavailable") from None
        if row is None or row["caller_id"] != caller.caller_id:
            raise EmailServiceError("denied")
        return {
            "notification_id": notification_id,
            "delivery_status": row["delivery_status"],
            "attempt_count": row["attempt_count"],
        }

    def _dispatch(self, notification_id: str) -> None:
        with self.lock:
            row = self.conn.execute(
                """
                SELECT subject, body, recipients_json, delivery_status
                FROM notification_delivery
                WHERE notification_id = ?
                """,
                (notification_id,),
            ).fetchone()
            if row is None or row["delivery_status"] != "pending":
                return
            subject = row["subject"]
            body = row["body"]
            recipients = json.loads(row["recipients_json"])
            self.conn.execute(
                """
                UPDATE notification_delivery
                SET delivery_status = 'sending', updated_at = ?
                WHERE notification_id = ?
                """,
                (_now(), notification_id),
            )
            self.conn.commit()
        for recipient in recipients:
            self.sender.send(
                OutboundMail(
                    from_address=self.mailbox.from_address,
                    to_address=recipient["email"],
                    subject=subject,
                    body=body,
                    notification_id=notification_id,
                    smtp_host=self.mailbox.smtp_host,
                    smtp_port=self.mailbox.smtp_port,
                    smtp_username=self.mailbox.smtp_username,
                    smtp_password=self.mailbox.smtp_password,
                )
            )
        with self.lock:
            self.conn.execute(
                """
                UPDATE notification_delivery
                SET delivery_status = 'sent', attempt_count = 1, updated_at = ?
                WHERE notification_id = ? AND delivery_status = 'sending'
                """,
                (_now(), notification_id),
            )
            self.conn.commit()


def _same_notification(row: sqlite3.Row, intent: dict[str, Any]) -> bool:
    stored_recipients = sorted(item["principal_id"] for item in json.loads(row["recipients_json"]))
    requested_recipients = sorted(item["principal_id"] for item in intent["recipients"])
    return (
        row["subject"] == intent["subject"]
        and row["body"] == intent["body"]
        and row["notification_kind"] == intent["notification_kind"]
        and stored_recipients == requested_recipients
    )


def _resolved_recipient(resolver: RecipientResolver, recipient: dict[str, Any]) -> dict[str, str]:
    email = resolver.resolve(recipient["principal_id"])
    claimed = recipient.get("email")
    if isinstance(claimed, str) and claimed.strip() and claimed != email:
        raise EmailServiceError("address_mismatch")
    return {"principal_id": recipient["principal_id"], "email": email}


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return ""


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _contains_sensitive(value: str) -> bool:
    return _SENSITIVE_CONTENT.search(value) is not None


def _content_problem(intent: dict[str, Any]) -> bool:
    if not _nonempty(intent.get("dedupe_key")) or not _nonempty(intent.get("notification_kind")):
        return True
    if intent.get("notification_kind") not in CONFIGURED_NOTIFICATION_KINDS:
        return True
    subject = intent.get("subject")
    body = intent.get("body")
    if not _nonempty(subject) or not _nonempty(body):
        return True
    if intent.get("schema_version") != "1" or not isinstance(intent.get("related"), dict):
        return True
    recipients = intent.get("recipients")
    if not isinstance(recipients, list) or not recipients:
        return True
    for recipient in recipients:
        if not isinstance(recipient, dict) or not _nonempty(recipient.get("principal_id")):
            return True
    if _HTML_MARKUP.search(subject) or _HTML_MARKUP.search(body):
        return True
    if len(subject) > SUBJECT_MAX_CHARS or len(body) > BODY_MAX_CHARS:
        return True
    if _contains_sensitive(subject) or _contains_sensitive(body):
        return True
    return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
