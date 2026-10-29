"""Reap stale candidate branches to stop TerminusDB branch growth (ai4-4g9s).

Every candidate submission creates one ``wiki-candidate-*`` branch that is never
removed once the candidate is merged, rejected or abandoned, so the repository
grows without bound. This module deletes candidate branches that no longer back
an active (non-terminal) submission.

Safety is the whole point:

- Only names on the ``wiki-candidate-`` namespace are ever deleted (the store
  also re-checks this).
- A branch is kept while its submission is still reviewable, and any branch whose
  proposal status is not terminal is kept, because a later formalize would fail
  if its branch disappeared.
- If the store cannot be listed, nothing is deleted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Proposal/submission states after which the candidate branch is safe to drop.
_TERMINAL_STATUSES = frozenset({"merged", "rejected", "abandoned", "formalized", "revoked"})


@dataclass
class ReapResult:
    deleted: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    kept_active: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def active_candidate_branches(sqlite_store, wiki_domain_id: str) -> set[str]:
    """Branch ids still backing a non-terminal candidate for one domain."""
    active: set[str] = set()
    for row in sqlite_store.list_dashboard_candidates(wiki_domain_id):
        branch = row.get("branch_id")
        if not isinstance(branch, str) or not branch:
            continue
        proposal_status = str(row.get("proposal_status") or "")
        submission_status = str(row.get("submission_status") or "")
        if proposal_status in _TERMINAL_STATUSES or submission_status in _TERMINAL_STATUSES:
            continue
        active.add(branch)
    return active


def reap_candidate_branches(*, sqlite_store, terminus_store, wiki_domain_id: str, dry_run: bool = False) -> ReapResult:
    keep = active_candidate_branches(sqlite_store, wiki_domain_id)
    if dry_run:
        candidates = terminus_store.list_candidate_branches()
        if candidates is None:
            return ReapResult(skipped=["store_unreadable"])
        return ReapResult(
            deleted=[branch for branch in candidates if branch not in keep],
            kept_active=sorted(keep & set(candidates)),
        )
    raw = terminus_store.reap_candidate_branches(keep)
    return ReapResult(
        deleted=list(raw.get("deleted", [])),
        failed=list(raw.get("failed", [])),
        kept_active=sorted(keep),
        skipped=list(raw.get("skipped", [])),
    )
