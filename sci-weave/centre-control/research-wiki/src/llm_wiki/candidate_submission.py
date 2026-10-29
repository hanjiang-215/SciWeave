from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from .canonical import canonical_json, sha256_json
from .formal_domain import WikiReferenceQualification, WikiSnapshotRead

# Stable reason codes for candidate submission validation (write-time gates),
# mirroring the mechanical checks moved to the domain MCP (ai4-eex0).
FORMAL_BASE_REQUIRED = "formal_base_required"
BASE_REVISION_MISSING = "base_revision_missing"


@dataclass(frozen=True)
class WikiCandidateSubmissionResult:
    status: str
    reason_code: str
    submission_id: str
    proposal_id: str | None = None
    candidate_commit_id: str | None = None
    branch_id: str | None = None
    commit_hash: str | None = None
    snapshot_digest: str | None = None
    references: tuple[Any, ...] = ()
    owner_review_eligible: bool = False


@dataclass(frozen=True)
class WikiCandidateReference:
    reference_id: str
    target_resource_version_id: str | None
    target_wiki_revision_id: str | None
    reference_role: str
    body_locator: str | None
    qualification: WikiReferenceQualification | None = None


@dataclass(frozen=True)
class CandidateSnapshotResult:
    status: str
    store_id: str | None = None
    branch_id: str | None = None
    commit_hash: str | None = None
    reason_code: str | None = None


class CandidateSnapshotStore(Protocol):
    def create_candidate_snapshot(self, domain_id: str, base_commit_ref: str,
                                 canonical_snapshot: str, idempotency_key: str) -> CandidateSnapshotResult: ...
    def read_exact_snapshot(self, store_id: str, database: str, branch_id: str,
                            commit_hash: str) -> WikiSnapshotRead: ...


class WikiCandidateService:
    """Accept a complete immutable WikiRevision and its full reference set."""

    def __init__(self, *, sqlite_store, terminus_store: CandidateSnapshotStore,
                 resource_review_service, terminus_database: str):
        self._sqlite = sqlite_store
        self._terminus = terminus_store
        self._reviews = resource_review_service
        self._database = terminus_database

    def submit(self, document_change: dict[str, Any], idempotency_key: str) -> WikiCandidateSubmissionResult:
        if not isinstance(document_change, dict) or not isinstance(idempotency_key, str) or not idempotency_key.strip():
            return _result("rejected", "invalid_submission", "")
        document = document_change.get("document")
        references = document_change.get("references")
        try:
            submission_id = _required(document_change, "submission_id")
            proposal_id = _required(document_change, "proposal_id")
            domain = _required(document_change, "wiki_domain_id")
            submitter = _required(document_change, "submitter_id")
        except ValueError:
            return _result("rejected", "invalid_submission", "")
        base_id = _text(document_change.get("base_formal_revision_id"))
        if base_id is None:
            return _result("rejected", FORMAL_BASE_REQUIRED, submission_id, proposal_id)
        if not _valid_document(document, submitter) or not isinstance(references, list):
            return _result("rejected", "invalid_document", submission_id)
        reason = self._validate_references(references, domain, document, base_id)
        if reason:
            return _result("rejected", reason, submission_id, proposal_id)

        change = {"document": document, "references": references}
        digest = sha256_json({**document_change, "document": document, "references": references})
        try:
            with self._sqlite.connection() as connection:
                prior = connection.execute("SELECT * FROM wiki_buffer_submission WHERE idempotency_key=?", (idempotency_key,)).fetchone()
                if prior:
                    if (prior["submission_id"], prior["wiki_domain_id"], prior["submitter_id"], prior["content_digest"]) != (submission_id, domain, submitter, digest):
                        return _result("rejected", "idempotency_conflict", submission_id, prior["proposal_id"])
                    saved = connection.execute("SELECT * FROM wiki_candidate_commit WHERE proposal_id=?", (prior["proposal_id"],)).fetchone()
                    if saved:
                        return self._result_from_rows(prior, saved)
                else:
                    revision = self._sqlite.get_formal_revision(base_id)
                    if revision is None or revision.wiki_domain_id != domain:
                        return _result("rejected", BASE_REVISION_MISSING, submission_id, proposal_id)
                    collision = connection.execute("SELECT 1 FROM wiki_buffer_submission WHERE submission_id=? OR proposal_id=?", (submission_id, proposal_id)).fetchone()
                    if collision:
                        return _result("rejected", "identity_conflict", submission_id, proposal_id)
                    connection.execute("INSERT INTO wiki_buffer_submission VALUES (?,?,?,?,?,?,?,?,?)",
                        (submission_id, domain, submitter, base_id, idempotency_key, digest, proposal_id, _now(), "pending"))
                    connection.commit()
        except sqlite3.Error:
            return _result("result_unknown", "sqlite_result_unknown", submission_id, proposal_id)
        revision = self._sqlite.get_formal_revision(base_id)
        if revision is None or revision.wiki_domain_id != domain:
            return _result("result_unknown", BASE_REVISION_MISSING, submission_id, proposal_id)
        snapshot_documents = [_candidate_revision(document, domain, proposal_id, base_id), *references]
        snapshot = canonical_json(snapshot_documents)
        op_id = sha256_json({"key": idempotency_key, "submission_id": submission_id, "submitter_id": submitter,
                             "wiki_domain_id": domain, "base_formal_revision_id": base_id,
                             "snapshot_digest": sha256_json(snapshot_documents)})
        try:
            raw = self._terminus.create_candidate_snapshot(domain, revision.formal_commit_hash, snapshot, op_id)
            outcome = raw if isinstance(raw, CandidateSnapshotResult) else CandidateSnapshotResult(**raw)
        except Exception:
            outcome = CandidateSnapshotResult("unknown", reason_code="store_result_unknown")
        if outcome.status == "unknown":
            return _result("result_unknown", outcome.reason_code or "store_result_unknown", submission_id, proposal_id)
        if outcome.status != "confirmed" or not all((outcome.store_id, outcome.branch_id, outcome.commit_hash)):
            self._set_status(idempotency_key, "failed")
            return _result("failed", outcome.reason_code or "store_rejected", submission_id, proposal_id)
        try:
            read = self._terminus.read_exact_snapshot(outcome.store_id, self._database, outcome.branch_id, outcome.commit_hash)
        except Exception:
            read = None
        if not isinstance(read, WikiSnapshotRead) or read.status != "confirmed" or (read.store_id, read.database, read.branch_id, read.commit_hash) != (outcome.store_id, self._database, outcome.branch_id, outcome.commit_hash) or not _contains(read.documents, snapshot_documents):
            return _result("result_unknown", "candidate_snapshot_unverified", submission_id, proposal_id)
        if self._sqlite.get_formal_revision(base_id) is None:
            return _result("rejected", BASE_REVISION_MISSING, submission_id, proposal_id)
        try:
            self._persist(document_change, idempotency_key, digest, read.content_digest or sha256_json(list(read.documents)), outcome, base_id)
        except Exception:
            return _result("result_unknown", "sqlite_result_unknown", submission_id, proposal_id)
        with self._sqlite.connection() as connection:
            row = connection.execute("SELECT * FROM wiki_buffer_submission WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            commit = connection.execute("SELECT * FROM wiki_candidate_commit WHERE proposal_id=?", (proposal_id,)).fetchone()
        return self._result_from_rows(row, commit)

    def _validate_references(self, references, domain, document, base_id):
        seen = set()
        revision_id = document.get("wiki_revision_id")
        formal_snapshot = None
        for ref in references:
            if not isinstance(ref, dict) or ref.get("@type") != "ResourceReference":
                return "invalid_reference"
            refid = _text(ref.get("reference_id"))
            rid = _text(ref.get("target_resource_version_id"))
            wid = _text(ref.get("target_wiki_revision_id"))
            role = _text(ref.get("reference_role"))
            if not refid or bool(rid) == bool(wid) or not role or ref.get("source_revision_id") != revision_id:
                return "invalid_reference_target"
            if ref.get("wiki_domain_id", domain) != domain:
                return "cross_domain_reference"
            if refid in seen:
                return "duplicate_reference"
            seen.add(refid)
            if wid:
                if formal_snapshot is None:
                    base_revision = self._sqlite.get_formal_revision(base_id)
                    if base_revision is None or base_revision.wiki_domain_id != domain:
                        return BASE_REVISION_MISSING
                    try:
                        formal_snapshot = self._terminus.read_exact_snapshot(
                            base_revision.terminus_store_id, self._database,
                            base_revision.formal_branch_id, base_revision.formal_commit_hash,
                        )
                    except Exception:
                        return "formal_reference_target_unavailable"
                    if not isinstance(formal_snapshot, WikiSnapshotRead) or formal_snapshot.status != "confirmed" or (
                        formal_snapshot.store_id, formal_snapshot.database,
                        formal_snapshot.branch_id, formal_snapshot.commit_hash,
                    ) != (
                        base_revision.terminus_store_id, self._database,
                        base_revision.formal_branch_id, base_revision.formal_commit_hash,
                    ):
                        return "formal_reference_target_unavailable"
                matches = [item for item in formal_snapshot.documents if isinstance(item, dict)
                           and item.get("wiki_revision_id") == wid
                           and item.get("lifecycle_state") == "formal"
                           and item.get("wiki_domain_id", domain) == domain]
                if len(matches) != 1:
                    return "invalid_wiki_revision_target"
        return None

    def _persist(self, change, key, digest, snapshot_digest, outcome, base_id):
        now = _now()
        doc = change["document"]
        domain, submitter, submission_id, proposal_id = (change[n] for n in ("wiki_domain_id", "submitter_id", "submission_id", "proposal_id"))
        candidate_id = "wiki-candidate-" + hashlib.sha256(key.encode()).hexdigest()[:20]
        event_id = "wiki-audit-" + hashlib.sha256((key + ":accepted").encode()).hexdigest()[:20]
        with self._sqlite.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            base_row = connection.execute(
                "SELECT formal_wiki_revision_id FROM formal_wiki_revision "
                "WHERE formal_wiki_revision_id=? AND wiki_domain_id=?",
                (base_id, domain),
            ).fetchone()
            if base_row is None:
                raise ValueError("base revision missing")
            existing = connection.execute("SELECT * FROM wiki_candidate_commit WHERE proposal_id=?", (proposal_id,)).fetchone()
            if existing:
                if (existing["terminus_store_id"], existing["branch_id"], existing["commit_hash"], existing["content_digest"]) != (outcome.store_id, outcome.branch_id, outcome.commit_hash, digest):
                    raise ValueError("candidate identity conflicts with persisted snapshot")
                connection.execute("UPDATE wiki_buffer_submission SET status='candidate_created' WHERE idempotency_key=?", (key,))
                connection.execute("INSERT OR IGNORE INTO wiki_audit_event VALUES (?,?,?,?,?,?,?,?,?,?)", (event_id, now, submitter, "wiki_candidate_submitted", "WikiProposal", proposal_id, "confirmed", "candidate_created", canonical_json({"submission_id": submission_id, "candidate_commit_id": candidate_id}), None))
                connection.commit()
                return
            connection.execute("INSERT INTO wiki_proposal VALUES (?,?,?,?,?,?,?,?)", (proposal_id, domain, base_id, outcome.store_id, outcome.branch_id, "candidate", submitter, now))
            connection.execute("INSERT INTO wiki_candidate_commit VALUES (?,?,?,?,?,?,?,?,?,?,?)", (candidate_id, domain, proposal_id, outcome.store_id, outcome.branch_id, outcome.commit_hash, base_id, digest, snapshot_digest, submitter, now))
            connection.execute("UPDATE wiki_buffer_submission SET status='candidate_created' WHERE idempotency_key=?", (key,))
            connection.execute("INSERT OR IGNORE INTO wiki_audit_event VALUES (?,?,?,?,?,?,?,?,?,?)", (event_id, now, submitter, "wiki_candidate_submitted", "WikiProposal", proposal_id, "confirmed", "candidate_created", canonical_json({"submission_id": submission_id, "candidate_commit_id": candidate_id}), None))
            connection.commit()

    def _set_status(self, key, status):
        with self._sqlite.connection() as connection:
            connection.execute("UPDATE wiki_buffer_submission SET status=? WHERE idempotency_key=?", (status, key))
            connection.commit()

    def _result_from_rows(self, submission, commit):
        if not commit:
            return _result("result_unknown", "store_result_unknown", submission["submission_id"], submission["proposal_id"])
        docs = []
        try:
            read = self._terminus.read_exact_snapshot(
                commit["terminus_store_id"], self._database,
                commit["branch_id"], commit["commit_hash"],
            )
            if isinstance(read, WikiSnapshotRead) and read.status == "confirmed" and (
                read.store_id, read.database, read.branch_id, read.commit_hash
            ) == (commit["terminus_store_id"], self._database, commit["branch_id"], commit["commit_hash"]):
                docs = list(read.documents)
            else:
                return _result("confirmed", "candidate_snapshot_unavailable", submission["submission_id"], submission["proposal_id"], commit["candidate_commit_id"], commit["branch_id"], commit["commit_hash"], commit["candidate_snapshot_digest"])
        except Exception:
            return _result("confirmed", "candidate_snapshot_unavailable", submission["submission_id"], submission["proposal_id"], commit["candidate_commit_id"], commit["branch_id"], commit["commit_hash"], commit["candidate_snapshot_digest"])
        refs = tuple(WikiCandidateReference(_text(r.get("reference_id")) or "", _text(r.get("target_resource_version_id")), _text(r.get("target_wiki_revision_id")), _text(r.get("reference_role")) or "", _text(r.get("body_locator")), self._qualification(r)) for r in docs if isinstance(r, dict) and r.get("@type") == "ResourceReference")
        eligible = all(
            r.qualification is None or r.qualification.status == "approved"
            for r in refs
        )
        return WikiCandidateSubmissionResult("confirmed", "ok", submission["submission_id"], submission["proposal_id"], commit["candidate_commit_id"], commit["branch_id"], commit["commit_hash"], commit["candidate_snapshot_digest"], refs, eligible)

    def _qualification(self, reference):
        target = reference.get("target_resource_version_id")
        if not target:
            return None
        try:
            q = self._reviews.get_current_qualification(target, reference.get("requested_scope") or reference.get("reference_role"))
            status = getattr(q, "status", "pending")
            return WikiReferenceQualification(target, status, getattr(q, "reason_code", "qualification_unknown"), getattr(q, "review_id", None), tuple(getattr(q, "use_scope", ()) or ()), tuple(getattr(q, "limitations", ()) or ()), tuple(getattr(q, "unknown_facts", ()) or ()))
        except Exception:
            return WikiReferenceQualification(target, "pending", "qualification_unavailable")


def _candidate_revision(document, domain, proposal, base):
    result = dict(document)
    result.update({"wiki_domain_id": domain, "proposal_id": proposal, "base_formal_revision_id": base, "lifecycle_state": "candidate"})
    return result


def _valid_document(document, submitter):
    if not isinstance(document, dict) or document.get("@type") != "WikiRevision": return False
    required = ("wiki_revision_id", "document_id", "category", "title", "body_markdown", "created_by", "created_at")
    if any(not _text(document.get(key)) for key in required): return False
    if document.get("category") not in {"source", "entity", "concept", "synthesis"}: return False
    return document.get("created_by") == submitter


def _contains(actual, expected):
    """True only when every expected document is present in full and unaltered.

    Matching by a weak field (``reference_id`` / ``wiki_revision_id``) let two
    documents with the same id but different content pass, and ``None == None``
    matched any document without those fields (ai4-hhs4). Match by ``@id`` and
    compare the whole document through canonical JSON instead.
    """
    by_id = {
        doc.get("@id"): doc
        for doc in actual
        if isinstance(doc, dict) and isinstance(doc.get("@id"), str)
    }
    for doc in expected:
        if not isinstance(doc, dict):
            return False
        target = canonical_json(doc)
        identity = doc.get("@id")
        if isinstance(identity, str):
            present = by_id.get(identity)
            if present is None or canonical_json(present) != target:
                return False
        else:
            # No stable @id on the expected doc: require a full match against some
            # actual doc -- but ignore the @id the store assigns on write, since the
            # caller-supplied document never carries it. Never a partial-field or
            # None==None match.
            if not any(
                isinstance(item, dict)
                and canonical_json({k: v for k, v in item.items() if k != "@id"}) == target
                for item in actual
            ):
                return False
    return True


def _required(data, key):
    value = _text(data.get(key))
    if not value: raise ValueError(key)
    return value


def _text(value): return value.strip() if isinstance(value, str) and value.strip() else None

def _result(status, reason, submission, proposal=None, candidate=None, branch=None, commit=None, digest=None):
    return WikiCandidateSubmissionResult(
        status, reason, submission, proposal, candidate, branch, commit, digest,
        references=(), owner_review_eligible=False,
    )

def _now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
