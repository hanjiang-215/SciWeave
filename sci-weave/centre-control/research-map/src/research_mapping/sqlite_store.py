from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .domain import FormalMappingRevision, FormalizationResult


class SqliteStore:
    """Foreign-key-enabled governance store.

    Only identities, activation facts and audit indexes live here. Graph
    content is never copied into SQLite.
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
            columns = {
                row["name"] for row in connection.execute(
                    "PRAGMA table_info(mapping_candidate_commit)"
                ).fetchall()
            }
            if "candidate_snapshot_digest" not in columns:
                connection.execute(
                    "ALTER TABLE mapping_candidate_commit ADD COLUMN candidate_snapshot_digest TEXT"
                )
            self._migrate_prereview_report_key(connection)
            connection.commit()

    def _migrate_prereview_report_key(self, connection: sqlite3.Connection) -> None:
        """Widen the prereview report key to include the base revision.

        A database created before ai4-sf8l carries the three-column key, where
        a re-review after ``base_moved`` was INSERT-OR-IGNOREd onto the
        invalidated row: the new checks were dropped and the candidate stayed
        ``report_stale`` for good. Rebuilding the table keeps every row.
        """
        columns: tuple[str, ...] | None = None
        for index in connection.execute("PRAGMA index_list(mapping_prereview_report)").fetchall():
            if not index["unique"]:
                continue
            names = tuple(
                row["name"]
                for row in connection.execute(f"PRAGMA index_info({index['name']})").fetchall()
            )
            if len(names) == 4:
                return
            if len(names) == 3:
                columns = names
        if columns is None:
            return
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.executescript(
            """
            CREATE TABLE mapping_prereview_report_rebuild (
                report_id               TEXT PRIMARY KEY,
                candidate_id            TEXT NOT NULL,
                candidate_head          TEXT NOT NULL,
                base_formal_revision_id TEXT NOT NULL DEFAULT '',
                rule_set_version        TEXT NOT NULL,
                checks                  TEXT NOT NULL,
                verdict                 TEXT NOT NULL CHECK (verdict IN ('passed', 'failed')),
                conflict_matrix         TEXT NOT NULL,
                created_at              TEXT NOT NULL,
                UNIQUE (candidate_id, candidate_head, rule_set_version, base_formal_revision_id)
            );
            INSERT INTO mapping_prereview_report_rebuild
                SELECT report_id, candidate_id, candidate_head,
                       COALESCE(base_formal_revision_id, ''), rule_set_version,
                       checks, verdict, conflict_matrix, created_at
                FROM mapping_prereview_report;
            DROP TABLE mapping_prereview_report;
            ALTER TABLE mapping_prereview_report_rebuild RENAME TO mapping_prereview_report;
            """
        )
        connection.execute("PRAGMA foreign_keys = ON")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def count_candidate_records(self) -> tuple[int, int, int, int]:
        with self.connection() as connection:
            return tuple(
                int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in (
                    "mapping_submission",
                    "mapping_proposal",
                    "mapping_candidate_commit",
                    "mapping_audit_event",
                )
            )

    def ensure_initial_formal_revision(
        self,
        *,
        mapping_domain_id: str,
        terminus_store_id: str,
        formal_branch_id: str,
        formal_commit_hash: str,
        graph_snapshot_digest: str,
        published_at: str,
        published_by: str = "research-map-bootstrap",
        formal_revision_id: str | None = None,
        formalization_operation_id: str | None = None,
        result_id: str | None = None,
    ) -> FormalMappingRevision:
        """Atomically install the domain's first formal revision.

        Existing current pointers are immutable from this bootstrap path. A
        partially populated domain is an error rather than an invitation to
        guess which record should be repaired.
        """
        import hashlib

        if not mapping_domain_id or not terminus_store_id or not formal_branch_id or not formal_commit_hash:
            raise ValueError("initial formal revision identity is incomplete")
        stable = hashlib.sha256(mapping_domain_id.encode("utf-8")).hexdigest()
        revision_id = formal_revision_id or f"formal-initial-{stable[:32]}"
        operation_id = formalization_operation_id or f"formal-bootstrap-{stable[:32]}"
        record_id = result_id or f"formalization-result-{stable[:32]}"
        revision = FormalMappingRevision(
            revision_id, mapping_domain_id, terminus_store_id, formal_branch_id,
            formal_commit_hash, None, None, None, published_by, published_at,
            graph_snapshot_digest, 0, 0,
        )
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            pointer = connection.execute(
                "SELECT current_formal_revision_id FROM mapping_current_formal_revision WHERE mapping_domain_id=?",
                (mapping_domain_id,),
            ).fetchone()
            if pointer is not None:
                existing = connection.execute(
                    "SELECT * FROM formal_mapping_revision WHERE formal_revision_id=?",
                    (pointer["current_formal_revision_id"],),
                ).fetchone()
                if existing is None or existing["mapping_domain_id"] != mapping_domain_id:
                    raise RuntimeError("formal_bootstrap_conflict")
                return _row_to_revision(existing)
            domain_rows = connection.execute(
                "SELECT formal_revision_id FROM formal_mapping_revision WHERE mapping_domain_id=?",
                (mapping_domain_id,),
            ).fetchall()
            if domain_rows:
                raise RuntimeError("formal_bootstrap_partial_state")
            existing_revision = connection.execute(
                "SELECT mapping_domain_id FROM formal_mapping_revision WHERE formal_revision_id=?",
                (revision_id,),
            ).fetchone()
            if existing_revision is not None:
                raise RuntimeError("formal_bootstrap_conflict")
            connection.execute(
                """INSERT INTO formal_mapping_revision
                (formal_revision_id,mapping_domain_id,terminus_store_id,formal_branch_id,formal_commit_hash,
                 base_formal_revision_id,source_proposal_id,approval_audit_event_id,published_by,published_at,
                 graph_snapshot_digest,node_count,edge_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (revision.formal_revision_id, revision.mapping_domain_id, revision.terminus_store_id,
                 revision.formal_branch_id, revision.formal_commit_hash, None, None, None,
                 revision.published_by, revision.published_at, revision.graph_snapshot_digest, 0, 0),
            )
            connection.execute(
                "INSERT INTO mapping_current_formal_revision VALUES (?,?,?)",
                (mapping_domain_id, revision_id, published_at),
            )
            connection.execute(
                """INSERT INTO mapping_formalization_result
                (result_id,mapping_domain_id,formalization_operation_id,attempt_number,result_status,
                 formal_revision_id,terminus_store_id,formal_commit_hash,recorded_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (record_id, mapping_domain_id, operation_id, 1, "succeeded", revision_id,
                 terminus_store_id, formal_commit_hash, published_at),
            )
            connection.commit()
        return revision

    def add_formal_revision(self, revision: FormalMappingRevision) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO formal_mapping_revision (
                    formal_revision_id, mapping_domain_id, terminus_store_id,
                    formal_branch_id, formal_commit_hash, base_formal_revision_id,
                    source_proposal_id, approval_audit_event_id, published_by,
                    published_at, graph_snapshot_digest, node_count, edge_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision.formal_revision_id,
                    revision.mapping_domain_id,
                    revision.terminus_store_id,
                    revision.formal_branch_id,
                    revision.formal_commit_hash,
                    revision.base_formal_revision_id,
                    revision.source_proposal_id,
                    revision.approval_audit_event_id,
                    revision.published_by,
                    revision.published_at,
                    revision.graph_snapshot_digest,
                    revision.node_count,
                    revision.edge_count,
                ),
            )
            connection.commit()

    def add_formalization_result(self, result: FormalizationResult) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO mapping_formalization_result (
                    result_id, mapping_domain_id, formalization_operation_id,
                    attempt_number, result_status, formal_revision_id,
                    terminus_store_id, formal_commit_hash, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.result_id,
                    result.mapping_domain_id,
                    result.formalization_operation_id,
                    result.attempt_number,
                    result.result_status,
                    result.formal_revision_id,
                    result.terminus_store_id,
                    result.formal_commit_hash,
                    result.recorded_at,
                ),
            )
            connection.commit()

    def set_current_formal_revision(
        self, mapping_domain_id: str, formal_revision_id: str, *, updated_at: str
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO mapping_current_formal_revision (
                    mapping_domain_id, current_formal_revision_id, updated_at
                ) VALUES (?, ?, ?)
                ON CONFLICT (mapping_domain_id) DO UPDATE SET
                    current_formal_revision_id = excluded.current_formal_revision_id,
                    updated_at = excluded.updated_at
                """,
                (mapping_domain_id, formal_revision_id, updated_at),
            )
            connection.commit()

    def get_current_formal_revision_id(self, mapping_domain_id: str) -> str | None:
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT current_formal_revision_id
                FROM mapping_current_formal_revision
                WHERE mapping_domain_id = ?
                """,
                (mapping_domain_id,),
            ).fetchone()
        return None if row is None else str(row["current_formal_revision_id"])

    def get_formal_revision(
        self, formal_revision_id: str
    ) -> FormalMappingRevision | None:
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM formal_mapping_revision
                WHERE formal_revision_id = ?
                """,
                (formal_revision_id,),
            ).fetchone()
        return None if row is None else _row_to_revision(row)

    def get_succeeded_formalization_result(
        self, mapping_domain_id: str, formal_revision_id: str
    ) -> FormalizationResult | None:
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM mapping_formalization_result
                WHERE mapping_domain_id = ?
                  AND formal_revision_id = ?
                  AND result_status = 'succeeded'
                ORDER BY recorded_at DESC, rowid DESC
                LIMIT 1
                """,
                (mapping_domain_id, formal_revision_id),
            ).fetchone()
        return None if row is None else _row_to_result(row)

    def get_candidate_for_submission(self, submission_id: str) -> dict | None:
        """Read the governance record of one submission and its candidate.

        Returns a plain dict (submission + proposal + candidate commit) or
        None when the submission does not exist. Graph content stays in
        TerminusDB; only identities and fixed head facts are returned here.
        """
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT s.submission_id, s.mapping_domain_id, s.submitter_id,
                       s.base_formal_revision_id, s.status AS submission_status,
                       s.submitted_at, s.content_digest,
                       p.proposal_id, p.status AS proposal_status,
                       c.candidate_commit_id, c.terminus_store_id, c.branch_id,
                       c.commit_hash, c.candidate_snapshot_digest, c.created_at
                FROM mapping_submission s
                LEFT JOIN mapping_proposal p ON p.proposal_id = s.proposal_id
                LEFT JOIN mapping_candidate_commit c ON c.proposal_id = s.proposal_id
                WHERE s.submission_id = ?
                """,
                (submission_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "submission_id": str(row["submission_id"]),
            "mapping_domain_id": str(row["mapping_domain_id"]),
            "submitter_id": str(row["submitter_id"]),
            "base_formal_revision_id": row["base_formal_revision_id"],
            "submission_status": str(row["submission_status"]),
            "submitted_at": str(row["submitted_at"]),
            "proposal_id": row["proposal_id"],
            "proposal_status": row["proposal_status"],
            "candidate_commit_id": row["candidate_commit_id"],
            "terminus_store_id": row["terminus_store_id"],
            "branch_id": row["branch_id"],
            "commit_hash": row["commit_hash"],
            "candidate_snapshot_digest": row["candidate_snapshot_digest"],
            "created_at": row["created_at"],
        }


    def list_reviewable_candidates(self, mapping_domain_id: str) -> list[dict[str, object]]:
        """List candidate governance records that are still reviewable.

        A reviewable candidate is not merged, rejected or abandoned and has a
        persisted candidate commit. Each record carries the exact fixed head,
        base revision and store location so a prereview scan can read the
        immutable snapshot by identity (he04 / apply the centre agent prereview
        input gate).
        """
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT s.submission_id, s.mapping_domain_id, s.submitter_id,
                       s.base_formal_revision_id, s.status AS submission_status,
                       s.submitted_at, s.content_digest,
                       p.proposal_id, p.status AS proposal_status,
                       c.candidate_commit_id, c.terminus_store_id, c.branch_id,
                       c.commit_hash, c.candidate_snapshot_digest, c.created_at
                FROM mapping_proposal p
                JOIN mapping_candidate_commit c ON c.proposal_id = p.proposal_id
                JOIN mapping_submission s ON s.proposal_id = p.proposal_id
                WHERE p.mapping_domain_id = ?
                  AND p.status NOT IN ('merged', 'rejected', 'abandoned')
                ORDER BY s.submitted_at ASC, s.rowid ASC
                """,
                (mapping_domain_id,),
            ).fetchall()
        return [
            {
                "submission_id": str(row["submission_id"]),
                "mapping_domain_id": str(row["mapping_domain_id"]),
                "submitter_id": str(row["submitter_id"]),
                "base_formal_revision_id": row["base_formal_revision_id"],
                "submission_status": str(row["submission_status"]),
                "submitted_at": str(row["submitted_at"]),
                "proposal_id": row["proposal_id"],
                "proposal_status": row["proposal_status"],
                "candidate_commit_id": row["candidate_commit_id"],
                "terminus_store_id": row["terminus_store_id"],
                "branch_id": row["branch_id"],
                "commit_hash": row["commit_hash"],
                "candidate_snapshot_digest": row["candidate_snapshot_digest"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

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
        """Append one prereview report under the unique candidate-head-rules key.

        The unique key (candidate_id, candidate_head, rule_set_version) makes
        re-review idempotent: INSERT OR IGNORE then SELECT returns the first
        report. No UPDATE/DELETE is ever issued (ai4-oz3s).
        """
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT OR IGNORE INTO mapping_prereview_report (
                    report_id, candidate_id, candidate_head, base_formal_revision_id,
                    rule_set_version, checks, verdict, conflict_matrix, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (report_id, candidate_id, candidate_head, base_formal_revision_id,
                 rule_set_version, checks, verdict, conflict_matrix, created_at),
            )
            row = connection.execute(
                """
                SELECT * FROM mapping_prereview_report
                WHERE candidate_id = ? AND candidate_head = ?
                  AND rule_set_version = ? AND base_formal_revision_id = ?
                """,
                (candidate_id, candidate_head, rule_set_version, base_formal_revision_id or ""),
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
        """Append one invalidation decision; reports are never edited."""
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO mapping_prereview_report_decision (
                    decision_id, target_report_id, reason, superseding_report_id, decided_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (decision_id, target_report_id, reason, superseding_report_id, decided_at),
            )
            row = connection.execute(
                """
                SELECT * FROM mapping_prereview_report_decision
                WHERE decision_id = ?
                """,
                (decision_id,),
            ).fetchone()
            connection.commit()
        return dict(row)

    def current_prereview_report(self, candidate_id: str, candidate_head: str) -> dict | None:
        """Return the report whose head matches and that is not superseded.

        Validity is derived from the latest decision row per candidate
        (ORDER BY decided_at DESC, rowid DESC LIMIT 1), never by editing the
        report row itself (ai4-oz3s).
        """
        with self.connection() as connection:
            report = connection.execute(
                """
                SELECT * FROM mapping_prereview_report
                WHERE candidate_id = ? AND candidate_head = ?
                ORDER BY created_at DESC, rowid DESC LIMIT 1
                """,
                (candidate_id, candidate_head),
            ).fetchone()
            if report is None:
                return None
            decision = connection.execute(
                """
                SELECT * FROM mapping_prereview_report_decision
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
                SELECT * FROM mapping_prereview_report
                WHERE candidate_id = ? AND candidate_head = ?
                ORDER BY created_at DESC, rowid DESC LIMIT 1
                """,
                (candidate_id, candidate_head),
            ).fetchone()
            if report is None:
                return {"status": "missing_report", "candidate_id": candidate_id, "candidate_head": candidate_head}
            decision = connection.execute(
                """
                SELECT * FROM mapping_prereview_report_decision
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


def _row_to_revision(row: sqlite3.Row) -> FormalMappingRevision:
    return FormalMappingRevision(
        formal_revision_id=str(row["formal_revision_id"]),
        mapping_domain_id=str(row["mapping_domain_id"]),
        terminus_store_id=str(row["terminus_store_id"]),
        formal_branch_id=str(row["formal_branch_id"]),
        formal_commit_hash=str(row["formal_commit_hash"]),
        base_formal_revision_id=row["base_formal_revision_id"],
        source_proposal_id=row["source_proposal_id"],
        approval_audit_event_id=row["approval_audit_event_id"],
        published_by=str(row["published_by"]),
        published_at=str(row["published_at"]),
        graph_snapshot_digest=row["graph_snapshot_digest"],
        node_count=row["node_count"],
        edge_count=row["edge_count"],
    )


def _row_to_result(row: sqlite3.Row) -> FormalizationResult:
    return FormalizationResult(
        result_id=str(row["result_id"]),
        mapping_domain_id=str(row["mapping_domain_id"]),
        formalization_operation_id=str(row["formalization_operation_id"]),
        attempt_number=int(row["attempt_number"]),
        result_status=str(row["result_status"]),
        formal_revision_id=str(row["formal_revision_id"]),
        terminus_store_id=str(row["terminus_store_id"]),
        formal_commit_hash=str(row["formal_commit_hash"]),
        recorded_at=str(row["recorded_at"]),
    )
