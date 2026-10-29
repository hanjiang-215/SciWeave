"""Bootstrap the first formal Wiki revision for a domain (B3 / ai4-0hdz).

Every candidate submission requires an existing ``base_formal_revision_id``
(``candidate_submission.py`` validates it against a stored revision), but nothing
in the product created the *first* one. A fresh domain was therefore stuck at
``no_current_pointer`` with an empty dashboard, reachable only by hand-seeding
SQLite and TerminusDB out of band.

This service is the missing entry point. It writes the immutable empty default
snapshot to TerminusDB and then activates it in SQLite through
``ensure_initial_formal_revision``, which is already atomic and refuses to
displace a different current pointer. Running it against a domain that already
has a formal revision is a safe no-op that reports ``already_exists``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class WikiBootstrapResult:
    status: str  # created | already_exists | failed | unknown
    reason_code: str | None
    wiki_domain_id: str
    formal_revision_id: str | None = None
    formal_commit_hash: str | None = None


class WikiBootstrapService:
    def __init__(self, *, sqlite_store, terminus_store) -> None:
        self._sqlite = sqlite_store
        self._terminus = terminus_store

    def bootstrap(self, wiki_domain_id: str) -> WikiBootstrapResult:
        domain = str(wiki_domain_id or "")
        if not domain:
            return WikiBootstrapResult("failed", "wiki_domain_id_required", domain)

        existing = self._sqlite.get_current_formal_revision_id(domain)
        if existing is not None:
            # Idempotent: never touch a domain that already has a pointer. Report
            # the current revision instead of creating a second baseline.
            return WikiBootstrapResult("already_exists", None, domain, existing, None)

        domain_key = hashlib.sha256(domain.encode("utf-8")).hexdigest()
        revision_id = "wiki-default-" + domain_key
        result_id = "wiki-default-result-" + domain_key

        initial = self._terminus.ensure_default_formal_snapshot(domain)
        if getattr(initial, "status", None) != "confirmed":
            reason = getattr(initial, "reason_code", None) or "formal_snapshot_unavailable"
            # A store ambiguity is not a clean failure; surface it so the caller
            # can retry rather than believing nothing happened.
            status = "unknown" if getattr(initial, "status", None) == "unknown" else "failed"
            return WikiBootstrapResult(status, reason, domain)

        current = self._sqlite.ensure_initial_formal_revision(
            formal_revision_id=revision_id,
            result_id=result_id,
            wiki_domain_id=domain,
            terminus_store_id=initial.store_id,
            formal_branch_id=initial.branch_id,
            formal_commit_hash=initial.commit_hash,
        )
        # ``ensure_initial_formal_revision`` returns the active revision id: ours
        # when it just created it, or an existing one when another pointer won a
        # race. Either way the domain now has a baseline.
        status = "created" if current == revision_id else "already_exists"
        return WikiBootstrapResult(status, None, domain, current, initial.commit_hash)
