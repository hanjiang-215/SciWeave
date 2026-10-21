from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WikiFormalRevision:
    formal_wiki_revision_id: str
    wiki_domain_id: str
    terminus_store_id: str
    formal_branch_id: str
    formal_commit_hash: str
    content_snapshot_digest: str | None = None


@dataclass(frozen=True)
class WikiFormalizationResult:
    result_id: str
    wiki_domain_id: str
    formal_wiki_revision_id: str
    terminus_store_id: str
    formal_commit_hash: str
    result_status: str


@dataclass(frozen=True)
class WikiSnapshotRead:
    status: str
    store_id: str | None = None
    database: str | None = None
    branch_id: str | None = None
    commit_hash: str | None = None
    documents: tuple[dict[str, Any], ...] = ()
    content_digest: str | None = None
    reason_code: str | None = None

    @classmethod
    def confirmed(cls, *, store_id: str, database: str, branch_id: str,
                  commit_hash: str, documents: tuple[dict[str, Any], ...] | list[dict[str, Any]],
                  content_digest: str) -> "WikiSnapshotRead":
        return cls("confirmed", store_id, database, branch_id, commit_hash,
                   tuple(documents), content_digest)

    @classmethod
    def unavailable(cls, reason_code: str = "store_unavailable") -> "WikiSnapshotRead":
        return cls(status="unavailable", reason_code=reason_code)

    @classmethod
    def missing(cls, reason_code: str = "commit_missing") -> "WikiSnapshotRead":
        return cls(status="missing", reason_code=reason_code)


@dataclass(frozen=True)
class WikiReferenceQualification:
    resource_version_id: str
    status: str
    reason_code: str
    review_id: str | None = None
    use_scope: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)
    unknown_facts: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FormalResourceReference:
    reference_id: str
    target_resource_version_id: str | None
    target_wiki_revision_id: str | None
    reference_role: str
    body_locator: str | None
    qualification: WikiReferenceQualification | None = None


@dataclass(frozen=True)
class WikiFormalQueryResult:
    status: str
    wiki_domain_id: str
    reason_code: str
    formal_wiki_revision_id: str | None = None
    terminus_store_id: str | None = None
    database: str | None = None
    formal_branch_id: str | None = None
    formal_commit_hash: str | None = None
    content_digest: str | None = None
    title: str | None = None
    description: str | None = None
    body_markdown: str | None = None
    references: tuple[FormalResourceReference, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.status != "available" and (self.body_markdown is not None or self.references):
            raise ValueError("only an available result may carry formal content")
        if self.status == "available" and not all((
            self.formal_wiki_revision_id, self.terminus_store_id, self.database,
            self.formal_branch_id, self.formal_commit_hash, self.content_digest,
            self.body_markdown,
        )):
            raise ValueError("available formal query needs confirmed identity and content")
