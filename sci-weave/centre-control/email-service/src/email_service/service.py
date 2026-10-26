from __future__ import annotations

import json
import re
import sqlite3
import threading
import unicodedata
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
from .registry_client import resolve_recipient


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
_KEPT_CONTROLS = frozenset("\n\r\t")
_FAILURE_SUMMARIES = {
    "retryable": "transient_sender_failure",
    "permanent_failure": "permanent_sender_failure",
    "invalid": "non_retryable_content",
}


def _initial_recipient_progress(recipients: list[dict[str, Any]]) -> list[dict[str, Any]]:
    progress: list[dict[str, Any]] = []
    for item in recipients:
        principal_id = item.get("principal_id")
        if not isinstance(principal_id, str) or not principal_id:
            continue
        progress.append(
            {
                "principal_id": principal_id,
                "email": item.get("email", ""),
                "status": "pending",
                "attempt_count": 0,
                "error_summary": None,
            }
        )
    return progress


def _load_recipient_progress(row: sqlite3.Row) -> list[dict[str, Any]]:
    raw = row["recipient_progress_json"]
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
    return _initial_recipient_progress(json.loads(row["recipients_json"]))


class EmailDeliveryService:
    def __init__(
        self,
        connection: sqlite3.Connection,
        resolver: RecipientResolver,
        sender: MailSender,
        mailbox: MailboxSettings,
        retry: RetrySettings,
        lock: threading.RLock,
        kind_allowlist: dict[str, frozenset[str]],
    ) -> None:
        self.conn = connection
        self.resolver = resolver
        self.sender = sender
        self.mailbox = mailbox
        self.retry = retry
        self.lock = lock
        self.kind_allowlist = kind_allowlist
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
              updated_at TEXT NOT NULL,
              recipient_progress_json TEXT
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
        if "error_summary" not in present:
            self.conn.execute("ALTER TABLE notification_delivery ADD COLUMN error_summary TEXT")
        if "recipient_progress_json" not in present:
            self.conn.execute("ALTER TABLE notification_delivery ADD COLUMN recipient_progress_json TEXT")
        self.conn.commit()

    async def accept(self, caller: Caller, intent: dict[str, Any]) -> dict[str, str]:
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
        if _content_problem(caller, intent, self.kind_allowlist):
            self.record_invalid(caller, intent)
        notification_id = intent["notification_id"]
        try:
            resolved = [
                await _resolved_recipient(self.resolver, recipient)
                for recipient in intent["recipients"]
            ]
        except EmailServiceError as exc:
            if exc.code not in NON_RETRYABLE_RECIPIENT_ERRORS:
                raise
            self._record_terminal(caller, intent, "permanent_failure", exc.code)
            raise
        now = _now()
        try:
            self.conn.execute(
                """
                INSERT INTO notification_delivery (
                  notification_id, caller_id, dedupe_key, notification_kind, subject, body,
                  related_json, schema_version, recipients_json, delivery_status, attempt_count,
                  recipient_progress_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?)
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
                    json.dumps(_initial_recipient_progress(resolved), ensure_ascii=False),
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
        self._record_terminal(caller, intent, "invalid", "invalid")
        raise EmailServiceError("invalid")

    def _record_terminal(
        self,
        caller: Caller,
        intent: dict[str, Any],
        delivery_status: str,
        error_summary: str,
    ) -> None:
        now = _now()
        related = intent.get("related")
        recipients = intent.get("recipients")
        subject = _text(intent.get("subject"))
        body = _text(intent.get("body"))
        try:
            self.conn.execute(
                """
                INSERT INTO notification_delivery (
                  notification_id, caller_id, dedupe_key, notification_kind, subject, body,
                  related_json, schema_version, recipients_json, delivery_status, attempt_count,
                  error_summary, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
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
                    error_summary,
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
                SELECT caller_id, delivery_status, attempt_count, error_summary,
                       recipients_json, recipient_progress_json
                FROM notification_delivery
                WHERE notification_id = ?
                """,
                (notification_id,),
            ).fetchone()
        except sqlite3.Error:
            raise EmailServiceError("storage_unavailable") from None
        if row is None or (caller.caller_type != "operator" and row["caller_id"] != caller.caller_id):
            raise EmailServiceError("denied")
        progress_by_id = {
            item["principal_id"]: item
            for item in _load_recipient_progress(row)
            if isinstance(item, dict) and isinstance(item.get("principal_id"), str)
        }
        recipients: list[dict[str, Any]] = []
        for raw in json.loads(row["recipients_json"]):
            principal_id = raw.get("principal_id")
            if not isinstance(principal_id, str) or not principal_id:
                continue
            item = progress_by_id.get(principal_id)
            if item is None:
                recipients.append(
                    {
                        "principal_id": principal_id,
                        "status": "pending",
                        "attempt_count": 0,
                        "error_summary": None,
                    }
                )
            else:
                recipients.append(
                    {
                        "principal_id": item["principal_id"],
                        "status": item["status"],
                        "attempt_count": item["attempt_count"],
                        "error_summary": item.get("error_summary"),
                    }
                )
        payload = {
            "notification_id": notification_id,
            "delivery_status": row["delivery_status"],
            "attempt_count": row["attempt_count"],
            "recipients": recipients,
        }
        if row["delivery_status"] in _FAILURE_SUMMARIES:
            payload["error_summary"] = row["error_summary"] or "send_failed"
        return payload

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
        notification_id, claim_token, subject, body, recipients, progress = claimed
        for recipient in recipients:
            principal_id = recipient.get("principal_id")
            item = next((p for p in progress if p.get("principal_id") == principal_id), None)
            if item is None:
                item = {
                    "principal_id": principal_id,
                    "email": recipient.get("email", ""),
                    "status": "pending",
                    "attempt_count": 0,
                    "error_summary": None,
                }
                progress.append(item)
            if item["status"] in ("sent", "permanent_failure"):
                continue
            is_claimed = item["status"] == "sending"
            is_final = item["attempt_count"] >= self.retry.max_attempts if is_claimed else item["attempt_count"] + 1 >= self.retry.max_attempts
            if not is_claimed:
                item["attempt_count"] += 1
                item["status"] = "sending"
                item["error_summary"] = None
            self._persist_recipient_progress(notification_id, claim_token, progress)
            try:
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
                if is_final:
                    item["status"] = "permanent_failure"
                    item["error_summary"] = "max_attempts_exceeded"
                else:
                    item["status"] = "retryable"
                    item["error_summary"] = "transient_sender_failure"
            except PermanentSenderFailure:
                item["status"] = "permanent_failure"
                item["error_summary"] = "permanent_sender_failure"
            except NonRetryableContentError:
                item["status"] = "permanent_failure"
                item["error_summary"] = "non_retryable_content"
            except EmailServiceError:
                item["status"] = "permanent_failure"
                item["error_summary"] = "sender_failure"
            except Exception:
                item["status"] = "permanent_failure"
                item["error_summary"] = "sender_failure"
            else:
                item["status"] = "sent"
                item["error_summary"] = None
            self._persist_recipient_progress(notification_id, claim_token, progress)
        self._settle_notification(notification_id, claim_token, progress)
        return notification_id

    def _persist_recipient_progress(
        self, notification_id: str, claim_token: str, progress: list[dict[str, Any]]
    ) -> None:
        max_attempts = max((item["attempt_count"] for item in progress), default=0)
        with self.lock:
            self.conn.execute(
                """
                UPDATE notification_delivery
                SET recipient_progress_json = ?, attempt_count = ?, updated_at = ?
                WHERE notification_id = ? AND claim_token = ? AND delivery_status = 'sending'
                """,
                (json.dumps(progress, ensure_ascii=False), max_attempts, _now(), notification_id, claim_token),
            )
            self.conn.commit()

    def _claim_next(
        self, *, startup: bool, skip: set[str]
    ) -> tuple[str, str, str, str, list, list] | None:
        with self.lock:
            try:
                rows = self.conn.execute(
                    """
                    SELECT notification_id, subject, body, recipients_json, recipient_progress_json,
                           delivery_status, attempt_count, next_attempt_at, claim_token, created_at, updated_at
                    FROM notification_delivery
                    ORDER BY created_at
                    """
                ).fetchall()
            except sqlite3.Error:
                return None
            now = _now()
            for row in rows:
                if row["notification_id"] in skip or not self._recoverable(row, now, startup=startup):
                    continue
                claim_token = uuid.uuid4().hex
                progress = _load_recipient_progress(row)
                for item in progress:
                    if item["status"] not in ("sent", "permanent_failure"):
                        item["attempt_count"] += 1
                        item["status"] = "sending"
                        item["error_summary"] = None
                        break
                claim_attempt_count = max((item["attempt_count"] for item in progress), default=0)
                cursor = self.conn.execute(
                    """
                    UPDATE notification_delivery
                    SET delivery_status = 'sending', claim_token = ?,
                        next_attempt_at = NULL, attempt_count = ?,
                        recipient_progress_json = ?, updated_at = ?
                    WHERE notification_id = ? AND delivery_status = ? AND updated_at = ?
                    """,
                    (
                        claim_token,
                        claim_attempt_count,
                        json.dumps(progress, ensure_ascii=False),
                        now,
                        row["notification_id"],
                        row["delivery_status"],
                        row["updated_at"],
                    ),
                )
                self.conn.commit()
                if cursor.rowcount != 1:
                    continue
                return (
                    row["notification_id"],
                    claim_token,
                    row["subject"],
                    row["body"],
                    json.loads(row["recipients_json"]),
                    progress,
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

    def _settle_notification(
        self, notification_id: str, claim_token: str, progress: list[dict[str, Any]]
    ) -> None:
        statuses = [item["status"] for item in progress]
        max_attempts = max((item["attempt_count"] for item in progress), default=0)
        if all(status == "sent" for status in statuses):
            status, error_summary, next_attempt_at = "sent", None, None
        elif any(status in ("retryable", "pending", "sending") for status in statuses):
            status, error_summary = "retryable", "transient_sender_failure"
            next_attempt_at = _later(self._backoff(max_attempts))
        else:
            status = "permanent_failure"
            failed = [item["error_summary"] for item in progress if item["status"] == "permanent_failure"]
            distinct = set(failed)
            if len(distinct) == 1 and None not in distinct:
                error_summary = distinct.pop()
            else:
                error_summary = "permanent_sender_failure"
            next_attempt_at = None
        with self.lock:
            self.conn.execute(
                """
                UPDATE notification_delivery
                SET delivery_status = ?, error_summary = ?, attempt_count = ?, next_attempt_at = ?,
                    recipient_progress_json = ?, claim_token = NULL, updated_at = ?
                WHERE notification_id = ? AND claim_token = ? AND delivery_status = 'sending'
                """,
                (
                    status,
                    error_summary,
                    max_attempts,
                    next_attempt_at,
                    json.dumps(progress, ensure_ascii=False),
                    _now(),
                    notification_id,
                    claim_token,
                ),
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


async def _resolved_recipient(resolver: RecipientResolver, recipient: dict[str, Any]) -> dict[str, str]:
    email = await resolve_recipient(resolver, recipient["principal_id"])
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


def _content_problem(caller: Caller, intent: dict[str, Any], kind_allowlist: dict[str, frozenset[str]]) -> bool:
    if not _nonempty(intent.get("dedupe_key")) or not _nonempty(intent.get("notification_kind")):
        return True
    if not _kind_allowed(caller, intent["notification_kind"], kind_allowlist):
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
    if _has_disallowed_control(subject) or _has_disallowed_control(body):
        return True
    if len(subject) > SUBJECT_MAX_CHARS or len(body) > BODY_MAX_CHARS:
        return True
    return False


def _kind_allowed(caller: Caller, kind: str, kind_allowlist: dict[str, frozenset[str]]) -> bool:
    if kind in CONFIGURED_NOTIFICATION_KINDS:
        return True
    return kind in kind_allowlist.get(caller.caller_id, frozenset())


def _has_disallowed_control(text: str) -> bool:
    return any(unicodedata.category(char) == "Cc" and char not in _KEPT_CONTROLS for char in text)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _later(seconds: float) -> str:
    moment = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    return moment.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _elapsed_seconds(started_at: str, now: str) -> float:
    started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    current = datetime.fromisoformat(now.replace("Z", "+00:00"))
    return (current - started).total_seconds()
