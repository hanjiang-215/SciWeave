from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import MailboxSettings, RetrySettings
from .ports import (
    NON_RETRYABLE_RECIPIENT_ERRORS,
    EmailServiceError,
    MailSender,
    NonRetryableContentError,
    OutboundMail,
    PermanentSenderFailure,
    RecipientResolver,
    TransientSenderFailure,
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
        retry: RetrySettings,
        lock: threading.RLock,
    ) -> None:
        self.conn = connection
        self.resolver = resolver
        self.sender = sender
        self.mailbox = mailbox
        self.retry = retry
        self.lock = lock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._recover_before = ""
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
              claim_token TEXT,
              next_attempt_at TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()
        self._ensure_retry_columns()

    def _ensure_retry_columns(self) -> None:
        present = {row[1] for row in self.conn.execute("PRAGMA table_info(notification_delivery)")}
        if "claim_token" not in present:
            self.conn.execute("ALTER TABLE notification_delivery ADD COLUMN claim_token TEXT")
        if "next_attempt_at" not in present:
            self.conn.execute("ALTER TABLE notification_delivery ADD COLUMN next_attempt_at TEXT")
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

    def start(self) -> None:
        if self._thread is not None:
            return
        self._recover_before = _now()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="email-delivery", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=0.5)
            self._thread = None

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

    def _run(self) -> None:
        seen: set[str] = set()
        while not self._stop.is_set():
            claimed = self._deliver_one(startup=True, skip=seen)
            if claimed is None:
                break
            seen.add(claimed)
        while not self._stop.is_set():
            if self._stop.wait(self.retry.poll_seconds):
                return
            while not self._stop.is_set() and self._deliver_one(startup=False, skip=frozenset()):
                pass

    def _deliver_one(self, *, startup: bool, skip: set[str]) -> str | None:
        claimed = self._claim_next(startup=startup, skip=skip)
        if claimed is None:
            return None
        notification_id, attempt_count, claim_token, subject, body, recipients = claimed
        try:
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
        except TransientSenderFailure:
            self._settle(notification_id, claim_token, "retryable", _later(self._backoff(attempt_count)))
        except PermanentSenderFailure:
            self._settle(notification_id, claim_token, "permanent_failure", None)
        except NonRetryableContentError:
            self._settle(notification_id, claim_token, "invalid", None)
        else:
            self._settle(notification_id, claim_token, "sent", None)
        return notification_id

    def _claim_next(self, *, startup: bool, skip: set[str]) -> tuple[str, int, str, str, str, list] | None:
        with self.lock:
            rows = self.conn.execute(
                """
                SELECT notification_id, subject, body, recipients_json, delivery_status,
                       attempt_count, next_attempt_at, claim_token, created_at, updated_at
                FROM notification_delivery
                ORDER BY created_at
                """
            ).fetchall()
            now = _now()
            for row in rows:
                if row["notification_id"] in skip or not self._recoverable(row, now, startup=startup):
                    continue
                attempt_count = row["attempt_count"] + 1
                claim_token = uuid.uuid4().hex
                cursor = self.conn.execute(
                    """
                    UPDATE notification_delivery
                    SET delivery_status = 'sending', attempt_count = ?, claim_token = ?,
                        next_attempt_at = NULL, updated_at = ?
                    WHERE notification_id = ? AND delivery_status = ? AND updated_at = ?
                    """,
                    (attempt_count, claim_token, now, row["notification_id"], row["delivery_status"], row["updated_at"]),
                )
                self.conn.commit()
                if cursor.rowcount != 1:
                    continue
                return (
                    row["notification_id"],
                    attempt_count,
                    claim_token,
                    row["subject"],
                    row["body"],
                    json.loads(row["recipients_json"]),
                )
        return None

    def _recoverable(self, row: sqlite3.Row, now: str, *, startup: bool) -> bool:
        if startup and row["created_at"] > self._recover_before:
            return False
        status = row["delivery_status"]
        if status == "pending":
            return True
        if status == "sending":
            return _elapsed_seconds(row["updated_at"], now) >= self.retry.sending_timeout_seconds
        if status != "retryable":
            return False
        if startup:
            return True
        due = row["next_attempt_at"]
        return due is None or due <= now

    def _settle(self, notification_id: str, claim_token: str, status: str, next_attempt_at: str | None) -> None:
        with self.lock:
            self.conn.execute(
                """
                UPDATE notification_delivery
                SET delivery_status = ?, next_attempt_at = ?, claim_token = NULL, updated_at = ?
                WHERE notification_id = ? AND claim_token = ? AND delivery_status = 'sending'
                """,
                (status, next_attempt_at, _now(), notification_id, claim_token),
            )
            self.conn.commit()

    def _backoff(self, attempt_count: int) -> float:
        delay = self.retry.initial_seconds * (self.retry.multiplier ** max(0, attempt_count - 1))
        if delay > self.retry.max_seconds:
            return self.retry.max_seconds
        return delay


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


def _later(seconds: float) -> str:
    moment = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    return moment.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _elapsed_seconds(started_at: str, now: str) -> float:
    started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    current = datetime.fromisoformat(now.replace("Z", "+00:00"))
    return (current - started).total_seconds()
