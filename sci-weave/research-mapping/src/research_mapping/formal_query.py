from __future__ import annotations

from . import errors
from .domain import (
    SNAPSHOT_CONFIRMED,
    SNAPSHOT_MISSING,
    SNAPSHOT_UNAVAILABLE,
    FormalQueryResult,
    SnapshotRead,
)
from .sqlite_store import SqliteStore
from .terminus_store import ExactSnapshotStore


class FormalQueryService:
    """Reads the activated Formal MappingRevision and its exact commit.

    Only a matching pointer, succeeded formalization result, exact snapshot
    identity and (when recorded) matching content digest produce content.
    """

    def __init__(
        self,
        *,
        sqlite_store: SqliteStore,
        terminus_store: ExactSnapshotStore,
        terminus_database: str,
    ) -> None:
        self._sqlite = sqlite_store
        self._terminus = terminus_store
        self._database = terminus_database

    def get_current(self, mapping_domain_id: str) -> FormalQueryResult:
        revision_id = self._sqlite.get_current_formal_revision_id(mapping_domain_id)
        if revision_id is None:
            return self._result(
                mapping_domain_id,
                "no_formal_revision",
                errors.NO_CURRENT_POINTER,
            )

        revision = self._sqlite.get_formal_revision(revision_id)
        if revision is None:
            return self._result(
                mapping_domain_id,
                "inconsistent",
                errors.POINTER_REVISION_MISSING,
            )
        if revision.mapping_domain_id != mapping_domain_id:
            return self._result(
                mapping_domain_id,
                "inconsistent",
                errors.POINTER_DOMAIN_MISMATCH,
            )

        formalization = self._sqlite.get_succeeded_formalization_result(
            mapping_domain_id, revision_id
        )
        if formalization is None:
            return self._result(
                mapping_domain_id,
                "inconsistent",
                errors.SUCCEEDED_RESULT_MISSING,
            )
        if (
            formalization.formal_commit_hash != revision.formal_commit_hash
            or formalization.terminus_store_id != revision.terminus_store_id
        ):
            return self._result(
                mapping_domain_id,
                "inconsistent",
                errors.SUCCEEDED_RESULT_MISMATCH,
            )

        try:
            snapshot = self._terminus.read_exact_snapshot(
                revision.terminus_store_id,
                self._database,
                revision.formal_branch_id,
                revision.formal_commit_hash,
            )
        except Exception:
            return self._result(
                mapping_domain_id,
                "unavailable",
                errors.STORE_UNAVAILABLE,
            )

        if not isinstance(snapshot, SnapshotRead):
            return self._result(
                mapping_domain_id,
                "unavailable",
                errors.STORE_RESULT_UNKNOWN,
            )
        if snapshot.status == SNAPSHOT_MISSING:
            return self._result(
                mapping_domain_id,
                "unavailable",
                snapshot.reason_code or errors.COMMIT_MISSING,
            )
        if snapshot.status == SNAPSHOT_UNAVAILABLE:
            return self._result(
                mapping_domain_id,
                "unavailable",
                snapshot.reason_code or errors.STORE_UNAVAILABLE,
            )
        if snapshot.status != SNAPSHOT_CONFIRMED:
            return self._result(
                mapping_domain_id,
                "unavailable",
                errors.STORE_RESULT_UNKNOWN,
            )

        identity_matches = (
            snapshot.store_id == revision.terminus_store_id
            and snapshot.database == self._database
            and snapshot.branch_id == revision.formal_branch_id
            and snapshot.commit_hash == revision.formal_commit_hash
        )
        if not identity_matches:
            return self._result(
                mapping_domain_id,
                "inconsistent",
                errors.SNAPSHOT_IDENTITY_MISMATCH,
            )

        if (
            revision.graph_snapshot_digest is not None
            and snapshot.content_digest != revision.graph_snapshot_digest
        ):
            return self._result(
                mapping_domain_id,
                "inconsistent",
                errors.SNAPSHOT_DIGEST_MISMATCH,
            )

        node_count = sum(
            1
            for document in snapshot.documents
            if str(document.get("@type", "")).endswith("TaskNode")
        )
        edge_count = sum(
            1
            for document in snapshot.documents
            if str(document.get("@type", "")).endswith("DependencyEdge")
        )
        if revision.node_count is not None and revision.node_count != node_count:
            return self._result(
                mapping_domain_id,
                "inconsistent",
                errors.SNAPSHOT_NODE_COUNT_MISMATCH,
            )
        if revision.edge_count is not None and revision.edge_count != edge_count:
            return self._result(
                mapping_domain_id,
                "inconsistent",
                errors.SNAPSHOT_EDGE_COUNT_MISMATCH,
            )

        return FormalQueryResult(
            status="available",
            mapping_domain_id=mapping_domain_id,
            reason_code=errors.OK,
            formal_revision_id=revision.formal_revision_id,
            store_id=revision.terminus_store_id,
            database=self._database,
            branch_id=revision.formal_branch_id,
            commit_hash=revision.formal_commit_hash,
            content_digest=snapshot.content_digest,
            documents=snapshot.documents,
        )

    def _result(
        self, mapping_domain_id: str, status: str, reason_code: str
    ) -> FormalQueryResult:
        return FormalQueryResult(
            status=status,
            mapping_domain_id=mapping_domain_id,
            reason_code=reason_code,
        )
