from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class CandidateSubmissionResult:
    status: str
    reason_code: str
    submission_id: str
    proposal_id: str | None = None
    candidate_commit_id: str | None = None
    branch_id: str | None = None
    commit_hash: str | None = None
    content_digest: str | None = None


@dataclass(frozen=True)
class CandidateSnapshotResult:
    status: str
    store_id: str | None = None
    branch_id: str | None = None
    commit_hash: str | None = None
    reason_code: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
