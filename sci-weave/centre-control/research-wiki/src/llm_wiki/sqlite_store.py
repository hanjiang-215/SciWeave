from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .canonical import canonical_json
from .domain import ResourceReviewRecord, ResourceVersionLocation, WikiAuditEvent
from .formal_domain import WikiFormalRevision, WikiFormalizationResult


@dataclass(frozen=True)
class WikiCandidateSubmission:
    submission_id: str
    wiki_domain_id: str
    submitter_id: str
    base_formal_revision_id: str
    idempotency_key: str
    content_digest: str
    proposal_id: str
    submitted_at: str
    status: str


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
            columns={row[1] for row in connection.execute("PRAGMA table_info(wiki_merge_request_buffer)")}
            if "owner_resource_approval_ids" not in columns:
                connection.execute("ALTER TABLE wiki_merge_request_buffer ADD COLUMN owner_resource_approval_ids TEXT NOT NULL DEFAULT '{}' ")
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

    def list_candidate_submissions(self, wiki_domain_id: str) -> list["WikiCandidateSubmission"]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM wiki_buffer_submission WHERE wiki_domain_id=? ORDER BY submitted_at, rowid",
                (wiki_domain_id,),
            ).fetchall()
        return [WikiCandidateSubmission(
            submission_id=str(row["submission_id"]), wiki_domain_id=str(row["wiki_domain_id"]),
            submitter_id=str(row["submitter_id"]), base_formal_revision_id=str(row["base_formal_revision_id"]),
            idempotency_key=str(row["idempotency_key"]), content_digest=str(row["content_digest"]),
            proposal_id=str(row["proposal_id"]), submitted_at=str(row["submitted_at"]), status=str(row["status"]),
        ) for row in rows]

    def list_dashboard_candidates(self, wiki_domain_id: str) -> list[dict[str, object]]:
        """Return candidate identities and review state without copying document content."""
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT s.submission_id, s.proposal_id, s.submitted_at, s.status AS submission_status,
                       p.status AS proposal_status, c.candidate_commit_id, c.terminus_store_id,
                       c.branch_id, c.commit_hash, m.status AS merge_request_status,
                       m.owner_decision
                FROM wiki_buffer_submission AS s
                LEFT JOIN wiki_proposal AS p ON p.proposal_id = s.proposal_id
                LEFT JOIN wiki_candidate_commit AS c ON c.proposal_id = s.proposal_id
                LEFT JOIN wiki_merge_request_buffer AS m ON m.proposal_id = s.proposal_id
                WHERE s.wiki_domain_id = ?
                ORDER BY s.submitted_at ASC, s.rowid ASC
                """,
                (wiki_domain_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_reviewable_candidates(self, wiki_domain_id: str) -> list[dict[str, object]]:
        """List candidate governance records that are still reviewable.

        A reviewable candidate is not merged, rejected or abandoned and has a
        persisted candidate commit. Each record carries the exact fixed head,
        base revision and store location so a prereview scan can read the
        immutable snapshot by identity (ai4-he04 input gate).
        """
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT s.submission_id, s.wiki_domain_id, s.submitter_id,
                       s.base_formal_revision_id, s.status AS submission_status,
                       s.submitted_at, s.content_digest,
                       p.proposal_id, p.status AS proposal_status,
                       c.candidate_commit_id, c.terminus_store_id, c.branch_id,
                       c.commit_hash, c.candidate_snapshot_digest, c.created_at
                FROM wiki_proposal p
                JOIN wiki_candidate_commit c ON c.proposal_id = p.proposal_id
                JOIN wiki_buffer_submission s ON s.proposal_id = p.proposal_id
                WHERE p.wiki_domain_id = ?
                  AND p.status NOT IN ('merged', 'rejected', 'abandoned')
                ORDER BY s.submitted_at ASC, s.rowid ASC
                """,
                (wiki_domain_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def append_prereview_report(
        self,
        *,
        report_id: str,
        candidate_id: str,
        candidate_head: str,
        base_formal_revision_id: str | None,
        rule_set_version: str,
        checks: str,
        verdict: str,
        conflict_matrix: str,
        created_at: str,
    ) -> dict[str, object]:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT OR IGNORE INTO wiki_prereview_report (
                    report_id, candidate_id, candidate_head, base_formal_revision_id,
                    rule_set_version, checks, verdict, conflict_matrix, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (report_id, candidate_id, candidate_head, base_formal_revision_id,
                 rule_set_version, checks, verdict, conflict_matrix, created_at),
            )
            row = connection.execute(
                """
                SELECT * FROM wiki_prereview_report
                WHERE candidate_id = ? AND candidate_head = ? AND rule_set_version = ?
                """,
                (candidate_id, candidate_head, rule_set_version),
            ).fetchone()
            connection.commit()
        return dict(row)

    def append_prereview_decision(
        self,
        *,
        decision_id: str,
        target_report_id: str,
        reason: str,
        superseding_report_id: str | None,
        decided_at: str,
    ) -> dict[str, object]:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO wiki_prereview_report_decision (
                    decision_id, target_report_id, reason, superseding_report_id, decided_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (decision_id, target_report_id, reason, superseding_report_id, decided_at),
            )
            row = connection.execute(
                """
                SELECT * FROM wiki_prereview_report_decision
                WHERE decision_id = ?
                """,
                (decision_id,),
            ).fetchone()
            connection.commit()
        return dict(row)

    def current_prereview_report(self, candidate_id: str, candidate_head: str) -> dict | None:
        with self.connection() as connection:
            report = connection.execute(
                """
                SELECT * FROM wiki_prereview_report
                WHERE candidate_id = ? AND candidate_head = ?
                """,
                (candidate_id, candidate_head),
            ).fetchone()
            if report is None:
                return None
            decision = connection.execute(
                """
                SELECT * FROM wiki_prereview_report_decision
                WHERE target_report_id = ?
                ORDER BY decided_at DESC, rowid DESC LIMIT 1
                """,
                (report["report_id"],),
            ).fetchone()
            if decision is not None:
                return None
        return dict(report)

    def prereview_status(self, candidate_id: str, candidate_head: str) -> dict[str, object]:
        """Return the observable prereview state of one candidate head.

        Distinguishes ``missing_report`` (no report row yet, the candidate is
        blocked waiting for prereview) from ``report_current`` (a report is the
        latest conclusion) and ``report_stale`` (the latest appended decision
        invalidates it with a machine-readable ``reason``). Reading is a pure
        projection of the append-only log; nothing is written here.
        """
        with self.connection() as connection:
            report = connection.execute(
                """
                SELECT * FROM wiki_prereview_report
                WHERE candidate_id = ? AND candidate_head = ?
                """,
                (candidate_id, candidate_head),
            ).fetchone()
            if report is None:
                return {"status": "missing_report", "candidate_id": candidate_id, "candidate_head": candidate_head}
            decision = connection.execute(
                """
                SELECT * FROM wiki_prereview_report_decision
                WHERE target_report_id = ?
                ORDER BY decided_at DESC, rowid DESC LIMIT 1
                """,
                (report["report_id"],),
            ).fetchone()
            base = {
                "status": "report_current",
                "candidate_id": candidate_id,
                "candidate_head": candidate_head,
                "report_id": str(report["report_id"]),
                "verdict": str(report["verdict"]),
                "rule_set_version": str(report["rule_set_version"]),
                "base_formal_revision_id": report["base_formal_revision_id"],
                "created_at": str(report["created_at"]),
            }
            if decision is not None:
                base["status"] = "report_stale"
                base["reason"] = str(decision["reason"])
            return base

    def add_formal_revision(
        self,
        *,
        formal_revision_id: str,
        wiki_domain_id: str,
        terminus_store_id: str,
        formal_branch_id: str,
        formal_commit_hash: str,
        content_snapshot_digest: str | None = None,
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO formal_wiki_revision (
                    formal_wiki_revision_id, wiki_domain_id, terminus_store_id,
                    formal_branch_id, formal_commit_hash, content_snapshot_digest
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (formal_revision_id, wiki_domain_id, terminus_store_id,
                 formal_branch_id, formal_commit_hash, content_snapshot_digest),
            )
            connection.commit()

    def add_formalization_result(
        self, *, result_id: str, wiki_domain_id: str,
        formal_wiki_revision_id: str, terminus_store_id: str,
        formal_commit_hash: str, result_status: str,
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO wiki_formalization_result (
                    result_id, wiki_domain_id, formal_wiki_revision_id,
                    terminus_store_id, formal_commit_hash, result_status
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (result_id, wiki_domain_id, formal_wiki_revision_id,
                 terminus_store_id, formal_commit_hash, result_status),
            )
            connection.commit()

    def set_formalization_status(self, result_id: str, result_status: str) -> None:
        with self.connection() as connection:
            connection.execute(
                "UPDATE wiki_formalization_result SET result_status = ? WHERE result_id = ?",
                (result_status, result_id),
            )
            connection.commit()

    def set_current_formal_revision(
        self, wiki_domain_id: str, formal_revision_id: str | None
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO wiki_current_formal_revision (
                    wiki_domain_id, current_formal_revision_id
                ) VALUES (?, ?)
                ON CONFLICT (wiki_domain_id) DO UPDATE SET
                    current_formal_revision_id = excluded.current_formal_revision_id
                """,
                (wiki_domain_id, formal_revision_id),
            )
            connection.commit()

    def get_current_formal_revision_id(self, wiki_domain_id: str) -> str | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT current_formal_revision_id FROM wiki_current_formal_revision WHERE wiki_domain_id = ?",
                (wiki_domain_id,),
            ).fetchone()
        return None if row is None else row["current_formal_revision_id"]

    def get_formal_revision(self, revision_id: str) -> WikiFormalRevision | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM formal_wiki_revision WHERE formal_wiki_revision_id = ?",
                (revision_id,),
            ).fetchone()
        if row is None:
            return None
        return WikiFormalRevision(
            formal_wiki_revision_id=str(row["formal_wiki_revision_id"]),
            wiki_domain_id=str(row["wiki_domain_id"]),
            terminus_store_id=str(row["terminus_store_id"]),
            formal_branch_id=str(row["formal_branch_id"]),
            formal_commit_hash=str(row["formal_commit_hash"]),
            content_snapshot_digest=row["content_snapshot_digest"],
        )

    def get_succeeded_formalization_result(
        self, wiki_domain_id: str, revision_id: str
    ) -> WikiFormalizationResult | None:
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM wiki_formalization_result
                WHERE wiki_domain_id = ? AND formal_wiki_revision_id = ?
                  AND result_status = 'succeeded'
                ORDER BY rowid DESC LIMIT 1
                """,
                (wiki_domain_id, revision_id),
            ).fetchone()
        if row is None:
            return None
        return WikiFormalizationResult(
            result_id=str(row["result_id"]),
            wiki_domain_id=str(row["wiki_domain_id"]),
            formal_wiki_revision_id=str(row["formal_wiki_revision_id"]),
            terminus_store_id=str(row["terminus_store_id"]),
            formal_commit_hash=str(row["formal_commit_hash"]),
            result_status=str(row["result_status"]),
        )

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
