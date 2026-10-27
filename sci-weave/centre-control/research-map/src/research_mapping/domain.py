from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import errors
from .canonical import sha256_json

SNAPSHOT_CONFIRMED = "confirmed"
SNAPSHOT_MISSING = "missing"
SNAPSHOT_UNAVAILABLE = "unavailable"

QUERY_AVAILABLE = "available"
QUERY_NO_FORMAL_REVISION = "no_formal_revision"
QUERY_INCONSISTENT = "inconsistent"
QUERY_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class FormalMappingRevision:
    formal_revision_id: str
    mapping_domain_id: str
    terminus_store_id: str
    formal_branch_id: str
    formal_commit_hash: str
    base_formal_revision_id: str | None
    source_proposal_id: str | None
    approval_audit_event_id: str | None
    published_by: str
    published_at: str
    graph_snapshot_digest: str | None = None
    node_count: int | None = None
    edge_count: int | None = None


@dataclass(frozen=True)
class FormalizationResult:
    result_id: str
    mapping_domain_id: str
    formalization_operation_id: str
    attempt_number: int
    result_status: str
    formal_revision_id: str
    terminus_store_id: str
    formal_commit_hash: str
    recorded_at: str


@dataclass(frozen=True)
class SnapshotRead:
    """Structured outcome of reading one exact TerminusDB commit.

    Only ``confirmed`` may carry documents; the adapter must never turn an
    unknown or mismatched response into a successful read.
    """

    status: str
    store_id: str | None = None
    database: str | None = None
    branch_id: str | None = None
    commit_hash: str | None = None
    documents: tuple[dict[str, Any], ...] = ()
    content_digest: str | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if self.status != SNAPSHOT_CONFIRMED and self.documents:
            raise ValueError("only a confirmed snapshot may carry documents")
        if self.status == SNAPSHOT_CONFIRMED:
            identity = (self.store_id, self.database, self.branch_id, self.commit_hash)
            if any(value is None or value == "" for value in identity):
                raise ValueError("a confirmed snapshot needs store/database/branch/commit")
            if self.content_digest is None:
                raise ValueError("a confirmed snapshot needs a content digest")

    @classmethod
    def confirmed(
        cls,
        *,
        store_id: str,
        database: str,
        branch_id: str,
        commit_hash: str,
        documents: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    ) -> "SnapshotRead":
        materialized = tuple(documents)
        return cls(
            status=SNAPSHOT_CONFIRMED,
            store_id=store_id,
            database=database,
            branch_id=branch_id,
            commit_hash=commit_hash,
            documents=materialized,
            content_digest=sha256_json(list(materialized)),
        )

    @classmethod
    def missing(cls, reason_code: str = errors.COMMIT_MISSING) -> "SnapshotRead":
        return cls(status=SNAPSHOT_MISSING, reason_code=reason_code)

    @classmethod
    def unavailable(
        cls, reason_code: str = errors.STORE_UNAVAILABLE
    ) -> "SnapshotRead":
        return cls(status=SNAPSHOT_UNAVAILABLE, reason_code=reason_code)


@dataclass(frozen=True)
class FormalQueryResult:
    status: str
    mapping_domain_id: str
    reason_code: str
    formal_revision_id: str | None = None
    store_id: str | None = None
    database: str | None = None
    branch_id: str | None = None
    commit_hash: str | None = None
    content_digest: str | None = None
    # The principal that approved this revision (ai4-2raq). It is the only
    # recorded answer to "who is the project owner here" -- there is no PO
    # roster -- and the handoff coordinator needs it to address the terminal
    # summary. Optional because a failure result has no revision to read it
    # from.
    published_by: str | None = None
    documents: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.status != QUERY_AVAILABLE and self.documents:
            raise ValueError("only an available result may carry graph content")
        if self.status == QUERY_AVAILABLE:
            required = (
                self.formal_revision_id,
                self.store_id,
                self.database,
                self.branch_id,
                self.commit_hash,
                self.content_digest,
            )
            if any(value is None or value == "" for value in required):
                raise ValueError("an available result needs confirmed identity")

    @property
    def nodes(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            document
            for document in self.documents
            if str(document.get("@type", "")).endswith("TaskNode")
        )

    @property
    def edges(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            document
            for document in self.documents
            if str(document.get("@type", "")).endswith("DependencyEdge")
        )
