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
