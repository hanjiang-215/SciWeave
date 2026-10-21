from __future__ import annotations

from typing import Any, Protocol

from . import errors
from .canonical import sha256_json
from .formal_domain import (
    FormalResourceReference,
    WikiFormalQueryResult,
    WikiReferenceQualification,
    WikiSnapshotRead,
)


class FormalQuerySqliteStore(Protocol):
    def get_current_formal_revision_id(self, wiki_domain_id: str) -> str | None: ...
    def get_formal_revision(self, revision_id: str): ...
    def get_succeeded_formalization_result(self, wiki_domain_id: str, revision_id: str): ...


class ExactWikiSnapshotStore(Protocol):
    def read_exact_snapshot(self, store_id: str, database: str, branch_id: str, commit_hash: str) -> WikiSnapshotRead: ...


class ResourceQualificationService(Protocol):
    def get_current_qualification(self, resource_version_id: str, requested_scope: str | None = None): ...


class WikiFormalQueryService:
    """Read only a SQLite-activated Wiki revision at its recorded exact commit."""

    def __init__(self, *, sqlite_store: FormalQuerySqliteStore,
                 terminus_store: ExactWikiSnapshotStore, terminus_database: str,
                 resource_review_service: ResourceQualificationService) -> None:
        self._sqlite = sqlite_store
        self._terminus = terminus_store
        self._database = terminus_database
        self._reviews = resource_review_service

    def get_current(self, wiki_domain_id: str) -> WikiFormalQueryResult:
        revision_id = self._sqlite.get_current_formal_revision_id(wiki_domain_id)
        if revision_id is None:
            return self._result(wiki_domain_id, "no_formal_revision", "no_current_pointer")
        revision = self._sqlite.get_formal_revision(revision_id)
        if revision is None:
            return self._result(wiki_domain_id, "inconsistent", "pointer_revision_missing")
        if revision.wiki_domain_id != wiki_domain_id:
            return self._result(wiki_domain_id, "inconsistent", "pointer_domain_mismatch")
        result = self._sqlite.get_succeeded_formalization_result(wiki_domain_id, revision_id)
        if result is None:
            return self._result(wiki_domain_id, "inconsistent", "succeeded_result_missing")
        if (result.result_status != "succeeded" or result.wiki_domain_id != wiki_domain_id
                or result.formal_wiki_revision_id != revision_id
                or result.terminus_store_id != revision.terminus_store_id
                or result.formal_commit_hash != revision.formal_commit_hash):
            return self._result(wiki_domain_id, "inconsistent", "succeeded_result_mismatch")
        try:
            snapshot = self._terminus.read_exact_snapshot(
                revision.terminus_store_id, self._database,
                revision.formal_branch_id, revision.formal_commit_hash,
            )
        except Exception:
            return self._result(wiki_domain_id, "unavailable", errors.STORE_UNAVAILABLE)
        if not isinstance(snapshot, WikiSnapshotRead):
            return self._result(wiki_domain_id, "unavailable", "store_result_unknown")
        if snapshot.status != "confirmed":
            status = "unavailable" if snapshot.status in ("missing", "unavailable") else "unavailable"
            return self._result(wiki_domain_id, status, snapshot.reason_code or errors.STORE_UNAVAILABLE)
        if (snapshot.store_id, snapshot.database, snapshot.branch_id, snapshot.commit_hash) != (
                revision.terminus_store_id, self._database,
                revision.formal_branch_id, revision.formal_commit_hash):
            return self._result(wiki_domain_id, "inconsistent", "snapshot_identity_mismatch")
        digest = sha256_json(list(snapshot.documents))
        if snapshot.content_digest != digest or (
            revision.content_snapshot_digest is not None
            and revision.content_snapshot_digest != digest
        ):
            return self._result(wiki_domain_id, "inconsistent", "snapshot_digest_mismatch")
        revision_docs = [doc for doc in snapshot.documents
                         if _wiki_revision_id(doc) == revision_id]
        if len(revision_docs) != 1:
            return self._result(wiki_domain_id, "inconsistent", "formal_revision_content_mismatch")
        document = revision_docs[0]
        references = []
        for raw in snapshot.documents:
            if not _is_reference(raw) or _text(raw.get("source_revision_id")) != revision_id:
                continue
            resource_target = _text(raw.get("target_resource_version_id"))
            wiki_target = _text(raw.get("target_wiki_revision_id"))
            if bool(resource_target) == bool(wiki_target):
                return self._result(wiki_domain_id, "inconsistent", "reference_target_invalid")
            qualification = None
            if resource_target:
                scope = _text(raw.get("requested_scope")) or _text(raw.get("reference_role"))
                try:
                    current = self._reviews.get_current_qualification(resource_target, scope)
                    qualification = WikiReferenceQualification(
                        resource_version_id=resource_target,
                        status=_text(getattr(current, "status", None)) or "pending",
                        reason_code=_text(getattr(current, "reason_code", None)) or "qualification_unknown",
                        review_id=getattr(current, "review_id", None),
                        use_scope=tuple(getattr(current, "use_scope", ()) or ()),
                        limitations=tuple(getattr(current, "limitations", ()) or ()),
                        unknown_facts=tuple(getattr(current, "unknown_facts", ()) or ()),
                    )
                except Exception:
                    qualification = WikiReferenceQualification(
                        resource_version_id=resource_target, status="pending",
                        reason_code="qualification_unavailable",
                    )
            references.append(FormalResourceReference(
                reference_id=_text(raw.get("reference_id")) or _document_id(raw) or "",
                target_resource_version_id=resource_target,
                target_wiki_revision_id=wiki_target,
                reference_role=_text(raw.get("reference_role")) or "",
                body_locator=_text(raw.get("body_locator")),
                qualification=qualification,
            ))
        return WikiFormalQueryResult(
            status="available", wiki_domain_id=wiki_domain_id, reason_code="ok",
            formal_wiki_revision_id=revision_id,
            terminus_store_id=revision.terminus_store_id,
            database=self._database, formal_branch_id=revision.formal_branch_id,
            formal_commit_hash=revision.formal_commit_hash, content_digest=digest,
            title=_text(document.get("title")), description=_text(document.get("description")),
            body_markdown=_text(document.get("body_markdown")), references=tuple(references),
        )

    @staticmethod
    def _result(domain: str, status: str, reason: str) -> WikiFormalQueryResult:
        return WikiFormalQueryResult(status=status, wiki_domain_id=domain, reason_code=reason)


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _document_id(document: dict[str, Any]) -> str | None:
    return _text(document.get("@id"))


def _wiki_revision_id(document: dict[str, Any]) -> str | None:
    if not _is_wiki_revision(document):
        return None
    return _text(document.get("wiki_revision_id")) or _document_id(document)


def _is_wiki_revision(document: dict[str, Any]) -> bool:
    return str(document.get("@type", "")).endswith("WikiRevision")


def _is_reference(document: dict[str, Any]) -> bool:
    return str(document.get("@type", "")).replace("_", "").lower().endswith("resourcereference")
