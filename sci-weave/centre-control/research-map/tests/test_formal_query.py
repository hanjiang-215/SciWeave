from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from typing import Any

from research_mapping import errors
from research_mapping.domain import (
    FormalMappingRevision,
    FormalizationResult,
    SnapshotRead,
)
from research_mapping.formal_query import FormalQueryService
from research_mapping.sqlite_store import SqliteStore


MAPPING_DOMAIN_ID = "mapping-domain-1"
FORMAL_REVISION_ID = "formal-revision-1"
STORE_ID = "admin"
DATABASE = "research-mapping"
BRANCH_ID = "formal"
COMMIT_HASH = "commit-1"

GRAPH_DOCUMENTS = (
    {"@id": "TaskNode/task-1", "@type": "TaskNode"},
    {"@id": "DependencyEdge/edge-1", "@type": "DependencyEdge"},
)


class FakeTerminusStore:
    def __init__(self, outcome: Any):
        self.outcome = outcome
        self.calls: list[tuple[str, str, str, str]] = []

    def read_exact_snapshot(
        self, store_id: str, database: str, branch_id: str, commit_hash: str
    ) -> Any:
        self.calls.append((store_id, database, branch_id, commit_hash))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class FormalQueryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sqlite = SqliteStore(os.path.join(self._tmp.name, "mapping.db"))
        self.sqlite.initialize()
        self.snapshot = SnapshotRead.confirmed(
            store_id=STORE_ID,
            database=DATABASE,
            branch_id=BRANCH_ID,
            commit_hash=COMMIT_HASH,
            documents=GRAPH_DOCUMENTS,
        )
        self.terminus = FakeTerminusStore(self.snapshot)
        self.service = FormalQueryService(
            sqlite_store=self.sqlite,
            terminus_store=self.terminus,
            terminus_database=DATABASE,
        )

    def test_available_query_returns_the_current_exact_formal_snapshot(self) -> None:
        revision = self._seed_current_revision()

        result = self.service.get_current(MAPPING_DOMAIN_ID)

        self.assertEqual(result.status, "available")
        self.assertEqual(result.reason_code, errors.OK)
        self.assertEqual(result.formal_revision_id, revision.formal_revision_id)
        self.assertEqual(result.store_id, STORE_ID)
        self.assertEqual(result.database, DATABASE)
        self.assertEqual(result.branch_id, BRANCH_ID)
        self.assertEqual(result.commit_hash, COMMIT_HASH)
        self.assertEqual(result.content_digest, self.snapshot.content_digest)
        # ai4-2raq: the approver comes from the revision row, not the graph.
        self.assertEqual(result.published_by, "owner-1")
        self.assertEqual(result.documents, GRAPH_DOCUMENTS)
        self.assertEqual(len(result.nodes), 1)
        self.assertEqual(len(result.edges), 1)
        self.assertEqual(
            self.terminus.calls,
            [(STORE_ID, DATABASE, BRANCH_ID, COMMIT_HASH)],
        )

    def test_no_current_pointer_returns_an_empty_formal_view(self) -> None:
        result = self.service.get_current(MAPPING_DOMAIN_ID)

        self.assertEqual(result.status, "no_formal_revision")
        self.assertEqual(result.reason_code, errors.NO_CURRENT_POINTER)
        self.assertEqual(result.documents, ())
        self.assertEqual(self.terminus.calls, [])

    def test_get_by_revision_reads_an_activated_historical_revision(self) -> None:
        self._seed_current_revision()

        result = self.service.get_by_revision(MAPPING_DOMAIN_ID, FORMAL_REVISION_ID)

        self.assertEqual(result.status, "available")
        self.assertEqual(result.reason_code, errors.OK)
        self.assertEqual(result.formal_revision_id, FORMAL_REVISION_ID)
        self.assertEqual(result.commit_hash, COMMIT_HASH)
        self.assertEqual(result.published_by, "owner-1")
        self.assertEqual(result.documents, GRAPH_DOCUMENTS)
        self.assertEqual(
            self.terminus.calls,
            [(STORE_ID, DATABASE, BRANCH_ID, COMMIT_HASH)],
        )

    def test_get_by_revision_unknown_revision_is_not_found(self) -> None:
        result = self.service.get_by_revision(MAPPING_DOMAIN_ID, "no-such-revision")

        self.assertEqual(result.status, "no_such_revision")
        self.assertEqual(result.reason_code, errors.REVISION_NOT_FOUND)
        self.assertEqual(result.documents, ())
        self.assertIsNone(result.published_by)
        self.assertEqual(self.terminus.calls, [])

    def test_get_by_revision_keeps_all_activated_revision_gates(self) -> None:
        # A revision row without a succeeded formalization result must not
        # yield content even when requested explicitly by revision id.
        self._seed_current_revision(add_result=False)

        result = self.service.get_by_revision(MAPPING_DOMAIN_ID, FORMAL_REVISION_ID)

        self.assertEqual(result.status, "inconsistent")
        self.assertEqual(result.reason_code, errors.SUCCEEDED_RESULT_MISSING)
        self.assertEqual(result.documents, ())
        self.assertEqual(self.terminus.calls, [])

    def test_pointer_to_a_missing_revision_is_inconsistent(self) -> None:
        # Simulate a damaged or externally modified governance database. Normal
        # store writes enforce this foreign key, but queries must still fail closed.
        connection = sqlite3.connect(self.sqlite.path)
        try:
            connection.execute(
                """
                INSERT INTO mapping_current_formal_revision (
                    mapping_domain_id, current_formal_revision_id, updated_at
                ) VALUES (?, ?, ?)
                """,
                (MAPPING_DOMAIN_ID, "missing-revision", "2026-10-21T00:00:00Z"),
            )
            connection.commit()
        finally:
            connection.close()

        result = self.service.get_current(MAPPING_DOMAIN_ID)

        self.assertEqual(result.status, "inconsistent")
        self.assertEqual(result.reason_code, errors.POINTER_REVISION_MISSING)
        self.assertEqual(result.documents, ())
        self.assertEqual(self.terminus.calls, [])

    def test_pointer_to_a_revision_from_another_domain_is_inconsistent(self) -> None:
        revision = self._revision(mapping_domain_id="another-domain")
        self._seed_current_revision(revision=revision, add_result=False)

        result = self.service.get_current(MAPPING_DOMAIN_ID)

        self.assertEqual(result.status, "inconsistent")
        self.assertEqual(result.reason_code, errors.POINTER_DOMAIN_MISMATCH)
        self.assertEqual(result.documents, ())
        self.assertEqual(self.terminus.calls, [])

    def test_non_succeeded_formalization_does_not_activate_a_revision(self) -> None:
        self._seed_current_revision(
            result=self._formalization_result(result_status="failed")
        )

        result = self.service.get_current(MAPPING_DOMAIN_ID)

        self.assertEqual(result.status, "inconsistent")
        self.assertEqual(result.reason_code, errors.SUCCEEDED_RESULT_MISSING)
        self.assertEqual(result.documents, ())
        self.assertEqual(self.terminus.calls, [])

    def test_succeeded_result_with_a_different_commit_is_inconsistent(self) -> None:
        self._seed_current_revision(
            result=self._formalization_result(formal_commit_hash="other-commit")
        )

        result = self.service.get_current(MAPPING_DOMAIN_ID)

        self.assertEqual(result.status, "inconsistent")
        self.assertEqual(result.reason_code, errors.SUCCEEDED_RESULT_MISMATCH)
        self.assertEqual(result.documents, ())
        self.assertEqual(self.terminus.calls, [])

    def test_succeeded_result_with_a_different_store_is_inconsistent(self) -> None:
        self._seed_current_revision(
            result=self._formalization_result(terminus_store_id="other-store")
        )

        result = self.service.get_current(MAPPING_DOMAIN_ID)

        self.assertEqual(result.status, "inconsistent")
        self.assertEqual(result.reason_code, errors.SUCCEEDED_RESULT_MISMATCH)
        self.assertEqual(result.documents, ())
        self.assertEqual(self.terminus.calls, [])

    def test_missing_exact_commit_is_unavailable_without_graph_content(self) -> None:
        self._seed_current_revision()
        self.terminus.outcome = SnapshotRead.missing()

        result = self.service.get_current(MAPPING_DOMAIN_ID)

        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.reason_code, errors.COMMIT_MISSING)
        self.assertEqual(result.documents, ())

    def test_unavailable_store_is_not_treated_as_an_empty_snapshot(self) -> None:
        self._seed_current_revision()
        self.terminus.outcome = SnapshotRead.unavailable("connection_timeout")

        result = self.service.get_current(MAPPING_DOMAIN_ID)

        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.reason_code, "connection_timeout")
        self.assertEqual(result.documents, ())

    def test_unknown_store_result_is_unavailable(self) -> None:
        self._seed_current_revision()
        self.terminus.outcome = {"status": "confirmed", "documents": GRAPH_DOCUMENTS}

        result = self.service.get_current(MAPPING_DOMAIN_ID)

        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.reason_code, errors.STORE_RESULT_UNKNOWN)
        self.assertEqual(result.documents, ())

    def test_store_exception_is_unavailable(self) -> None:
        self._seed_current_revision()
        self.terminus.outcome = RuntimeError("store connection failed")

        result = self.service.get_current(MAPPING_DOMAIN_ID)

        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.reason_code, errors.STORE_UNAVAILABLE)
        self.assertEqual(result.documents, ())

    def test_confirmed_snapshot_identity_must_match_the_requested_commit(self) -> None:
        self._seed_current_revision()

        for field, value in (
            ("store_id", "other-store"),
            ("database", "other-database"),
            ("branch_id", "other-branch"),
            ("commit_hash", "other-commit"),
        ):
            with self.subTest(field=field):
                self.terminus.outcome = replace(self.snapshot, **{field: value})

                result = self.service.get_current(MAPPING_DOMAIN_ID)

                self.assertEqual(result.status, "inconsistent")
                self.assertEqual(
                    result.reason_code, errors.SNAPSHOT_IDENTITY_MISMATCH
                )
                self.assertEqual(result.documents, ())

    def test_confirmed_snapshot_digest_must_match_the_revision(self) -> None:
        revision = self._revision(graph_snapshot_digest="f" * 64)
        self._seed_current_revision(revision=revision)

        result = self.service.get_current(MAPPING_DOMAIN_ID)

        self.assertEqual(result.status, "inconsistent")
        self.assertEqual(result.reason_code, errors.SNAPSHOT_DIGEST_MISMATCH)
        self.assertEqual(result.documents, ())

    def test_confirmed_snapshot_node_count_must_match_the_revision(self) -> None:
        revision = self._revision(node_count=2)
        self._seed_current_revision(revision=revision)

        result = self.service.get_current(MAPPING_DOMAIN_ID)

        self.assertEqual(result.status, "inconsistent")
        self.assertEqual(result.reason_code, errors.SNAPSHOT_NODE_COUNT_MISMATCH)
        self.assertEqual(result.documents, ())

    def test_confirmed_snapshot_edge_count_must_match_the_revision(self) -> None:
        revision = self._revision(edge_count=2)
        self._seed_current_revision(revision=revision)

        result = self.service.get_current(MAPPING_DOMAIN_ID)

        self.assertEqual(result.status, "inconsistent")
        self.assertEqual(result.reason_code, errors.SNAPSHOT_EDGE_COUNT_MISMATCH)
        self.assertEqual(result.documents, ())

    def test_sqlite_store_enables_foreign_keys(self) -> None:
        with self.sqlite.connection() as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_sqlite_store_initialization_is_idempotent(self) -> None:
        self.sqlite.initialize()
        self.assertIsNone(self.sqlite.get_current_formal_revision_id(MAPPING_DOMAIN_ID))

    def _seed_current_revision(
        self,
        *,
        revision: FormalMappingRevision | None = None,
        result: FormalizationResult | None = None,
        add_result: bool = True,
    ) -> FormalMappingRevision:
        revision = revision or self._revision()
        self.sqlite.add_formal_revision(revision)
        if add_result:
            self.sqlite.add_formalization_result(result or self._formalization_result())
        self.sqlite.set_current_formal_revision(
            MAPPING_DOMAIN_ID,
            revision.formal_revision_id,
            updated_at="2026-10-21T00:00:00Z",
        )
        return revision

    def _revision(self, **overrides: Any) -> FormalMappingRevision:
        values: dict[str, Any] = {
            "formal_revision_id": FORMAL_REVISION_ID,
            "mapping_domain_id": MAPPING_DOMAIN_ID,
            "terminus_store_id": STORE_ID,
            "formal_branch_id": BRANCH_ID,
            "formal_commit_hash": COMMIT_HASH,
            "base_formal_revision_id": None,
            "source_proposal_id": "proposal-1",
            "approval_audit_event_id": "audit-event-1",
            "published_by": "owner-1",
            "published_at": "2026-10-21T00:00:00Z",
            "graph_snapshot_digest": self.snapshot.content_digest,
            "node_count": 1,
            "edge_count": 1,
        }
        values.update(overrides)
        return FormalMappingRevision(**values)

    def _formalization_result(self, **overrides: Any) -> FormalizationResult:
        values: dict[str, Any] = {
            "result_id": "result-1",
            "mapping_domain_id": MAPPING_DOMAIN_ID,
            "formalization_operation_id": "operation-1",
            "attempt_number": 1,
            "result_status": "succeeded",
            "formal_revision_id": FORMAL_REVISION_ID,
            "terminus_store_id": STORE_ID,
            "formal_commit_hash": COMMIT_HASH,
            "recorded_at": "2026-10-21T00:00:00Z",
        }
        values.update(overrides)
        return FormalizationResult(**values)


if __name__ == "__main__":
    unittest.main()
