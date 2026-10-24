from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import MailboxSettings, RetrySettings
from .ports import (
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
        notification_id = intent["notification_id"]
        resolved = [
            {"principal_id": recipient["principal_id"], "email": self.resolver.resolve(recipient["principal_id"])}
            for recipient in intent["recipients"]
        ]
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _later(seconds: float) -> str:
    moment = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    return moment.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _elapsed_seconds(started_at: str, now: str) -> float:
    started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    current = datetime.fromisoformat(now.replace("Z", "+00:00"))
    return (current - started).total_seconds()
