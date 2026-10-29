"""Subscriber core: turn inbound messages into durable Worker executions.

One message goes through a fixed order, mirroring ``docs/data-flow/work-agent.md``:

1. find or create the stable ``task_session`` for the message target;
2. in a single SQLite transaction, create a ``queued`` execution record with
   ``trigger='queue'`` and ``trigger_ref`` set to the message identity, and write
   an audit event;
3. the Worker runner (``worker_runner``) atomically claims the Worker Lease and
   only then runs the loop, so the same target is serialized while different
   targets may run concurrently;
4. the caller commits the consumer offset only after the Worker loop has fully
   ended.

Replay safety: deduplication uses the ``business_key`` unique constraint
derived from the references required by the message-queue contract.  Duplicate
delivery of the same message therefore returns the persisted execution instead
of creating a second one.
"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from task_agent_worker.store import ExecutionStore, utc_now

from .queue import QueueMessage


class SubscriberService:
    """Consumes ``QueueMessage`` objects and persists them into executions."""

    def __init__(self, store: ExecutionStore, agent_id: str):
        self.store = store
        self.agent_id = agent_id

    def handle_message(self, message: QueueMessage) -> dict[str, Any]:
        """Persist one inbound message as a ``queued`` execution record.

        Returns a result dict; ``duplicate=True`` when the business key was
        already present (the persisted execution is returned unchanged).
        """
        envelope = message.payload
        target = envelope.get("target", {})
        task_node_id = self._required_text(target, "id")
        event_id = str(envelope.get("event_id") or message.key or message.offset)
        mapping_domain_id = self._optional_text(envelope, "mapping_domain_id")
        payload = envelope.get("payload", {})
        if isinstance(payload, dict):
            trigger_revision = self._optional_text(payload, "formal_revision_id") or self._optional_text(envelope, "formal_revision_id")
            target_version_ref = self._optional_text(payload, "target_node_version_ref") or self._optional_text(envelope, "target_node_version_ref")
        else:
            trigger_revision = self._optional_text(envelope, "formal_revision_id")
            target_version_ref = self._optional_text(envelope, "target_node_version_ref")
        business_key = f"{task_node_id}:{target_version_ref}:{trigger_revision}"

        now = utc_now()
        execution_id = str(uuid.uuid4())
        session_id = f"task_{self.agent_id}_{task_node_id}_{uuid.uuid4().hex}"
        with self.store.transaction() as connection:
            existing = connection.execute(
                "SELECT execution_id FROM execution_records WHERE business_key = ?",
                (business_key,),
            ).fetchone()
            if existing is not None:
                return self._describe(connection, existing["execution_id"], duplicate=True)

            session = connection.execute(
                "SELECT session_id FROM task_sessions WHERE task_node_id = ?",
                (task_node_id,),
            ).fetchone()
            if session is None:
                connection.execute(
                    "INSERT INTO task_sessions VALUES (?, ?, ?, ?)",
                    (task_node_id, session_id, now, now),
                )
            else:
                session_id = session["session_id"]
            connection.execute(
                """INSERT INTO execution_records
                   (execution_id, task_node_id, session_id, status, trigger,
                    trigger_ref, business_key, mapping_domain_id, created_at, updated_at)
                   VALUES (?, ?, ?, 'queued', 'queue', ?, ?, ?, ?, ?)""",
                (
                    execution_id, task_node_id, session_id, event_id[:200], business_key,
                    mapping_domain_id or None, now, now,
                ),
            )
            connection.execute(
                """INSERT INTO audit_events
                   (event_type, task_node_id, execution_id, details, created_at)
                   VALUES ('message_received', ?, ?, ?, ?)""",
                (task_node_id, execution_id, self._details(message), now),
            )
            connection.execute(
                """INSERT INTO audit_events
                   (event_type, task_node_id, execution_id, details, created_at)
                   VALUES ('execution_queued', ?, ?, '{}', ?)""",
                (task_node_id, execution_id, now),
            )
        return self._describe_in_new_connection(execution_id, duplicate=False)

    def queued_targets(self) -> list[str]:
        """Distinct targets that currently have a queued execution."""
        with self.store.lock:
            rows = self.store.connection.execute(
                "SELECT DISTINCT task_node_id FROM execution_records WHERE status = 'queued' ORDER BY task_node_id"
            ).fetchall()
        return [row["task_node_id"] for row in rows]

    def next_queued_execution(self, task_node_id: str) -> dict[str, Any] | None:
        """Oldest queued execution for a target, for the Worker runner to claim."""
        with self.store.lock:
            row = self.store.connection.execute(
                """SELECT execution_id, task_node_id, session_id, trigger, trigger_ref, business_key
                   FROM execution_records
                   WHERE task_node_id = ? AND status = 'queued'
                   ORDER BY created_at, rowid LIMIT 1""",
                (task_node_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def _describe_in_new_connection(self, execution_id: str, *, duplicate: bool) -> dict[str, Any]:
        with self.store.lock:
            return self._describe(self.store.connection, execution_id, duplicate=duplicate)

    @staticmethod
    def _describe(connection: sqlite3.Connection, execution_id: str, *, duplicate: bool) -> dict[str, Any]:
        row = connection.execute(
            """SELECT execution_id, task_node_id, session_id,
                      status AS execution_status, trigger, trigger_ref,
                      business_key, mapping_domain_id, created_at, updated_at
               FROM execution_records WHERE execution_id = ?""",
            (execution_id,),
        ).fetchone()
        return {
            "execution_id": row["execution_id"],
            "task_node_id": row["task_node_id"],
            "session_id": row["session_id"],
            "execution_status": row["execution_status"],
            "trigger": row["trigger"],
            "trigger_ref": row["trigger_ref"],
            "business_key": row["business_key"],
            "mapping_domain_id": row["mapping_domain_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "duplicate": duplicate,
        }

    @staticmethod
    def _details(message: QueueMessage) -> str:
        return (
            f'{{"topic": "{message.topic}", "partition": {message.partition}, '
            f'"offset": {message.offset}, "key": "{message.key or ""}"}}'
        )

    @staticmethod
    def _required_text(mapping: dict[str, Any], name: str) -> str:
        value = mapping.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required")
        return value.strip()

    @staticmethod
    def _optional_text(mapping: dict[str, Any], name: str) -> str:
        value = mapping.get(name)
        if not isinstance(value, str):
            return ""
        return value.strip()