from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .canonical import canonical_json
from .domain import ResourceReviewRecord, ResourceVersionLocation, WikiAuditEvent


class SqliteStore:
    """Append-only resource review and audit records.

    The store exposes insert and read operations only; there is no update or
    delete path, so earlier decisions and denied attempts stay intact.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._schema_path = Path(__file__).with_name("schema.sql")

    def initialize(self) -> None:
        if self.path != ":memory:":
            Path(self.path).expanduser().resolve().parent.mkdir(
                parents=True, exist_ok=True
            )
        schema = self._schema_path.read_text(encoding="utf-8")
        with self.connection() as connection:
            connection.executescript(schema)
            connection.commit()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def add_review(self, review: ResourceReviewRecord) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO resource_version_review (
                    review_id, resource_version_id, target_owner_id, reviewer_id,
                    authority_reference, decision, reason, evidence_reference,
                    decided_at, use_scope, limitations, content_digest,
                    snapshot_digest, unknown_facts, snapshot_status, target_location
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review.review_id,
                    review.resource_version_id,
                    review.target_owner_id,
                    review.reviewer_id,
                    review.authority_reference,
                    review.decision,
                    review.reason,
                    review.evidence_reference,
                    review.decided_at,
                    json.dumps(list(review.use_scope)),
                    json.dumps(list(review.limitations)),
                    review.content_digest,
                    review.snapshot_digest,
                    json.dumps(list(review.unknown_facts)),
                    review.snapshot_status,
                    _location_to_text(review.target_location),
                ),
            )
            connection.commit()

    def list_reviews(self, resource_version_id: str) -> list[ResourceReviewRecord]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM resource_version_review
                WHERE resource_version_id = ?
                ORDER BY decided_at ASC, rowid ASC
                """,
                (resource_version_id,),
            ).fetchall()
        return [_row_to_review(row) for row in rows]

    def latest_review(self, resource_version_id: str) -> ResourceReviewRecord | None:
        reviews = self.list_reviews(resource_version_id)
        return None if not reviews else reviews[-1]

    def add_audit_event(self, event: WikiAuditEvent) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO wiki_audit_event (
                    audit_event_id, occurred_at, actor_id, action, target_type,
                    target_id, outcome, reason_code, detail, related_review_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.audit_event_id,
                    event.occurred_at,
                    event.actor_id,
                    event.action,
                    event.target_type,
                    event.target_id,
                    event.outcome,
                    event.reason_code,
                    event.detail,
                    event.related_review_id,
                ),
            )
            connection.commit()

    def list_audit_events(self, target_id: str) -> list[WikiAuditEvent]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM wiki_audit_event
                WHERE target_id = ?
                ORDER BY occurred_at ASC, rowid ASC
                """,
                (target_id,),
            ).fetchall()
        return [_row_to_event(row) for row in rows]


def _row_to_review(row: sqlite3.Row) -> ResourceReviewRecord:
    return ResourceReviewRecord(
        review_id=str(row["review_id"]),
        resource_version_id=str(row["resource_version_id"]),
        target_owner_id=row["target_owner_id"],
        reviewer_id=str(row["reviewer_id"]),
        authority_reference=str(row["authority_reference"]),
        decision=str(row["decision"]),
        reason=str(row["reason"]),
        evidence_reference=row["evidence_reference"],
        decided_at=str(row["decided_at"]),
        use_scope=tuple(json.loads(row["use_scope"])),
        limitations=tuple(json.loads(row["limitations"])),
        content_digest=row["content_digest"],
        snapshot_digest=row["snapshot_digest"],
        unknown_facts=tuple(json.loads(row["unknown_facts"])),
        snapshot_status=str(row["snapshot_status"]),
        target_location=_location_from_text(row["target_location"]),
    )


def _location_to_text(location: ResourceVersionLocation | None) -> str | None:
    if location is None:
        return None
    return canonical_json(
        {
            "store_id": location.store_id,
            "database": location.database,
            "branch_id": location.branch_id,
            "commit_hash": location.commit_hash,
        }
    )


def _location_from_text(value: object) -> ResourceVersionLocation | None:
    if not value:
        return None
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    fields = ("store_id", "database", "branch_id", "commit_hash")
    if not all(isinstance(parsed.get(name), str) for name in fields):
        return None
    return ResourceVersionLocation(**{name: parsed[name] for name in fields})


def _row_to_event(row: sqlite3.Row) -> WikiAuditEvent:
    return WikiAuditEvent(
        audit_event_id=str(row["audit_event_id"]),
        occurred_at=str(row["occurred_at"]),
        actor_id=str(row["actor_id"]),
        action=str(row["action"]),
        target_type=str(row["target_type"]),
        target_id=str(row["target_id"]),
        outcome=str(row["outcome"]),
        reason_code=str(row["reason_code"]),
        detail=row["detail"],
        related_review_id=row["related_review_id"],
    )
