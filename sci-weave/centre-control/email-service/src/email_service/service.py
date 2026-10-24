from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .config import MailboxSettings
from .ports import EmailServiceError, MailSender, OutboundMail, RecipientResolver


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
        threading.Thread(target=self._dispatch, args=(notification_id,), daemon=True).start()
        return {"notification_id": notification_id, "acceptance": "accepted_for_delivery"}

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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
