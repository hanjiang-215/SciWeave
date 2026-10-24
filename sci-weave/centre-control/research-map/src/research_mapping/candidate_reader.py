"""Read the reviewable candidate set of a Mapping domain as prereview input.

This is the input half of the Centre Agent prereview entry (ai4-he04): the
domain management MCP exposes a snapshot of every candidate that is not
merged, rejected or abandoned, with the exact fixed head and base revision
that SQLite records. Reading happens at the immutable TerminusDB commit per
candidate, with fail isolation so one unavailable store never hides the
others; every candidate either carries its documents or an explicit
``snapshot_status``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .domain import SNAPSHOT_CONFIRMED, SnapshotRead


class CandidateSnapshotReaderStore(Protocol):
    def read_exact_snapshot(
        self, store_id: str, database: str, branch_id: str, commit_hash: str
    ) -> SnapshotRead: ...


@dataclass(frozen=True)
class ReviewableCandidateSnapshot:
    """One reviewable candidate with its fixed head facts and content."""

    submission_id: str
    proposal_id: str
    base_formal_revision_id: str | None
    candidate_commit_id: str | None
    candidate_head: str | None
    submitter_id: str
    proposal_status: str
    documents: tuple[dict[str, Any], ...] = ()
    snapshot_status: str = "available"
    reason_code: str | None = None


class MappingCandidateReader:
    """List the same-time reviewable candidates and read their fixed heads."""

    def __init__(
        self,
        *,
        sqlite_store,
        terminus_store: CandidateSnapshotReaderStore,
        terminus_database: str,
    ) -> None:
        self._sqlite = sqlite_store
        self._terminus = terminus_store
        self._database = terminus_database

    def list_reviewable(self, mapping_domain_id: str) -> list[ReviewableCandidateSnapshot]:
        records = self._sqlite.list_reviewable_candidates(mapping_domain_id)
        items: list[ReviewableCandidateSnapshot] = []
        for record in records:
            store_id = record.get("terminus_store_id")
            branch = record.get("branch_id")
            head = record.get("commit_hash")
            if not store_id or not branch or not head:
                items.append(_item(record, documents=(), snapshot_status="unavailable", reason_code="candidate_snapshot_missing"))
                continue
            snapshot = self._read_exact(str(store_id), str(branch), str(head))
            if (
                not isinstance(snapshot, SnapshotRead)
                or snapshot.status != SNAPSHOT_CONFIRMED
                or snapshot.store_id != str(store_id)
                or snapshot.branch_id != str(branch)
                or snapshot.commit_hash != str(head)
            ):
                items.append(_item(
                    record,
                    documents=(),
                    snapshot_status="unavailable",
                    reason_code=getattr(snapshot, "reason_code", None) or "candidate_store_unavailable",
                ))
                continue
            digest = record.get("candidate_snapshot_digest")
            if digest and snapshot.content_digest != digest:
                items.append(_item(record, documents=(), snapshot_status="unavailable", reason_code="candidate_snapshot_digest_mismatch"))
                continue
            items.append(_item(record, documents=tuple(snapshot.documents), snapshot_status="available"))
        return items

    def _read_exact(self, store_id: str, branch_id: str, commit_hash: str) -> SnapshotRead | None:
        try:
            snapshot = self._terminus.read_exact_snapshot(
                store_id, self._database, branch_id, commit_hash
            )
        except Exception:
            return None
        return snapshot if isinstance(snapshot, SnapshotRead) else None


def _item(
    record: dict[str, object],
    *,
    documents: tuple[dict[str, Any], ...],
    snapshot_status: str,
    reason_code: str | None = None,
) -> ReviewableCandidateSnapshot:
    return ReviewableCandidateSnapshot(
        submission_id=str(record["submission_id"]),
        proposal_id=str(record["proposal_id"]),
        base_formal_revision_id=record.get("base_formal_revision_id"),
        candidate_commit_id=record.get("candidate_commit_id"),
        candidate_head=record.get("commit_hash"),
        submitter_id=str(record["submitter_id"]),
        proposal_status=str(record.get("proposal_status")),
        documents=documents,
        snapshot_status=snapshot_status,
        reason_code=reason_code,
    )