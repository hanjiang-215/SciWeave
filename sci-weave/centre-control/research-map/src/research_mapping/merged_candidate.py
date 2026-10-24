"""Merged candidate creation for the Mapping domain (ai4-8dgd / ai4-5auy).

The Centre Agent may synthesise one new candidate branch from several
source candidates on the same formal base. The merged candidate is an
ordinary candidate: it goes through the same prereview and owner approval
path and introduces no new Proposal state. This module owns the three
merged-specific constraints:

- only a new branch may be created; existing candidates are never edited;
- the author field is multi-valued and records every source author;
  source authors get no operation rights over the merged candidate;
- a merged candidate may not be merged again (no nesting).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Protocol


class MergedCandidateStore(Protocol):
    def get_candidate_for_submission(self, submission_id: str) -> dict | None: ...


class CandidateSubmitter(Protocol):
    def submit(self, change_set: dict[str, Any], idempotency_key: str): ...


def _merged_submitter(source_authors: list[str]) -> str:
    """Stable merged author marker derived from the sorted source authors.

    The prefix makes a merged candidate recognisable (the no-merge-again
    check) and the digest stays stable across idempotent replays.
    """
    ordered = sorted(dict.fromkeys(author for author in source_authors if author))
    payload = json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))
    return "merged:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class MappingMergedCandidateService:
    """Create a merged candidate branch from source candidates."""

    def __init__(
        self,
        sqlite_store,
        candidate_service: CandidateSubmitter,
        *,
        service_name: str = "mapping-management",
    ) -> None:
        self._sqlite = sqlite_store
        self._candidate_service = candidate_service
        self._service = service_name

    def create_merged(
        self,
        *,
        mapping_domain_id: str,
        source_proposal_ids: list[str],
        base_formal_revision_id: str,
        change_set: dict[str, Any],
        idempotency_key: str,
    ) -> Any:
        """Create one merged candidate branch; never edits existing candidates.

        Returns the candidate service submit result. Raises ValueError with a
        stable reason for merged-specific rejections.
        """
        if not source_proposal_ids or not isinstance(source_proposal_ids, list):
            raise ValueError("source_proposal_ids is required and must be a non-empty array")
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("idempotency_key is required")

        sources = self._load_sources(mapping_domain_id, source_proposal_ids)
        authors = [str(item["submitter_id"]) for item in sources]
        merged_set = dict(change_set)
        merged_set.setdefault("mapping_domain_id", mapping_domain_id)
        merged_set.setdefault("base_formal_revision_id", base_formal_revision_id)
        merged_set["submitter_id"] = _merged_submitter(authors)
        # Record provenance inside the change set so the digest covers it; the
        # governance record keeps only identities, content stays in TerminusDB.
        merged_set["merged_from"] = [
            {
                "proposal_id": str(item["proposal_id"]),
                "submission_id": str(item["submission_id"]),
                "submitter_id": str(item["submitter_id"]),
            }
            for item in sources
        ]
        return self._candidate_service.submit(merged_set, idempotency_key)

    def _load_sources(self, mapping_domain_id: str, source_proposal_ids: list[str]) -> list[dict]:
        records: list[dict] = []
        with self._sqlite.connection() as connection:
            for proposal_id in source_proposal_ids:
                row = connection.execute(
                    """
                    SELECT s.submission_id, s.mapping_domain_id, s.submitter_id,
                           s.base_formal_revision_id, p.proposal_id, p.status AS proposal_status
                    FROM mapping_submission s
                    JOIN mapping_proposal p ON p.proposal_id = s.proposal_id
                    WHERE p.proposal_id = ? AND p.mapping_domain_id = ?
                    """,
                    (proposal_id, mapping_domain_id),
                ).fetchone()
                if row is None:
                    raise ValueError("source_candidate_not_found")
                if row["proposal_status"] not in {"candidate", "review_pending", "approved_pending_formalization"}:
                    raise ValueError("source_candidate_not_reviewable")
                submitter = str(row["submitter_id"])
                if submitter.startswith("merged:"):
                    raise ValueError("nested_merged_candidate")
                records.append(dict(row))
        return records