"""Merged candidate creation for the Wiki domain (ai4-8dgd / ai4-5auy).

Symmetric to ``research_mapping.merged_candidate``: the Centre Agent may
create one new candidate branch from several source candidates. Only a new
branch is created; the author field is multi-valued (every source author),
source authors get no operation rights, and a merged candidate may not be
merged again.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol


class MergedCandidateStore(Protocol):
    def get_candidate_for_submission(self, submission_id: str) -> dict | None: ...


class CandidateSubmitter(Protocol):
    def submit(self, document_change: dict[str, Any], idempotency_key: str): ...


def _merged_submitter(source_authors: list[str]) -> str:
    """Stable merged author marker derived from the sorted source authors."""
    ordered = sorted(dict.fromkeys(author for author in source_authors if author))
    payload = json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))
    return "merged:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class WikiMergedCandidateService:
    """Create a merged candidate branch from source candidates."""

    def __init__(
        self,
        sqlite_store,
        candidate_service: CandidateSubmitter,
        *,
        service_name: str = "wiki-management",
    ) -> None:
        self._sqlite = sqlite_store
        self._candidate_service = candidate_service
        self._service = service_name

    def create_merged(
        self,
        *,
        wiki_domain_id: str,
        source_proposal_ids: list[str],
        base_formal_revision_id: str,
        document_change: dict[str, Any],
        idempotency_key: str,
    ) -> Any:
        """Create one merged Wiki candidate branch; never edits existing ones."""
        if not source_proposal_ids or not isinstance(source_proposal_ids, list):
            raise ValueError("source_proposal_ids is required and must be a non-empty array")
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("idempotency_key is required")

        sources = self._load_sources(wiki_domain_id, source_proposal_ids)
        authors = [str(item["submitter_id"]) for item in sources]
        merged_change = dict(document_change)
        merged_change.setdefault("wiki_domain_id", wiki_domain_id)
        merged_change.setdefault("base_formal_revision_id", base_formal_revision_id)
        merged_change["submitter_id"] = _merged_submitter(authors)
        # Wiki candidate validation requires document.created_by == submitter;
        # stamp the merged marker onto the revision so it passes the write gate.
        document = merged_change.get("document")
        if isinstance(document, dict):
            merged_change["document"] = {**document, "created_by": merged_change["submitter_id"]}
        merged_change["merged_from"] = [
            {
                "proposal_id": str(item["proposal_id"]),
                "submission_id": str(item["submission_id"]),
                "submitter_id": str(item["submitter_id"]),
            }
            for item in sources
        ]
        return self._candidate_service.submit(merged_change, idempotency_key)

    def _load_sources(self, wiki_domain_id: str, source_proposal_ids: list[str]) -> list[dict]:
        records: list[dict] = []
        with self._sqlite.connection() as connection:
            for proposal_id in source_proposal_ids:
                row = connection.execute(
                    """
                    SELECT s.submission_id, s.wiki_domain_id, s.submitter_id,
                           s.base_formal_revision_id, p.proposal_id, p.status AS proposal_status
                    FROM wiki_buffer_submission s
                    JOIN wiki_proposal p ON p.proposal_id = s.proposal_id
                    WHERE p.proposal_id = ? AND p.wiki_domain_id = ?
                    """,
                    (proposal_id, wiki_domain_id),
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