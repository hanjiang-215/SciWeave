from __future__ import annotations

from dataclasses import dataclass, field

from . import errors

READ_CONFIRMED = "confirmed"
READ_MISSING = "missing"
READ_UNAVAILABLE = "unavailable"

QUALIFICATION_PENDING = "pending"


@dataclass(frozen=True)
class ResourceVersionLocation:
    """Exact TerminusDB location that holds one immutable ResourceVersion.

    A version id alone cannot address a historical snapshot: the exact
    ``store/database/branch/commit`` has to come from a governance record that
    pinned the write. This value object keeps that four-part identity together
    so callers cannot pass a partial location.
    """

    store_id: str
    database: str
    branch_id: str
    commit_hash: str

    def __post_init__(self) -> None:
        for name in ("store_id", "database", "branch_id", "commit_hash"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")


@dataclass(frozen=True)
class AuthorityContext:
    """Traceable authority supplied by the trusted composition boundary."""

    authority_reference: str
    evidence: str | None = None


@dataclass(frozen=True)
class ResourceVersionSnapshot:
    """Immutable facts about one exact ResourceVersion."""

    resource_version_id: str
    resource_id: str | None = None
    owner_id: str | None = None
    snapshot_digest: str | None = None
    content_digest: str | None = None
    content_checksum_algorithm: str | None = None
    source_locator: str | None = None
    source_external_id: str | None = None
    external_version_id: str | None = None
    current_access_locator: str | None = None
    availability_status: str | None = None
    availability_checked_at: str | None = None
    generated_at: str | None = None
    generated_by: str | None = None
    generated_by_task_id: str | None = None
    license: str | None = None
    attribution: str | None = None
    handling_mode: str | None = None

    def derive_unknown_facts(self) -> tuple[str, ...]:
        facts: list[str] = []
        if not self.resource_id:
            facts.append("resource_id")
        if not self.owner_id:
            facts.append("owner_id")
        if not self.content_digest:
            facts.append("content_checksum")
        if not self.license:
            facts.append("license")
        if not self.attribution:
            facts.append("attribution")
        if not self.handling_mode:
            facts.append("handling_mode")
        if not self.source_locator:
            facts.append("source_locator")
        if not self.current_access_locator:
            facts.append("access_locator")
        if not self.availability_status:
            facts.append("availability_status")
        elif not self.availability_checked_at:
            facts.append("availability_checked_at")
        if not self.generated_by:
            facts.append("generated_by")
        if not self.generated_at:
            facts.append("generated_at")
        if not self.external_version_id and not self.content_digest:
            facts.append("external_content_unpinned")
        return tuple(facts)

    def derive_limitations(self) -> tuple[str, ...]:
        limitations: list[str] = []
        if not self.license:
            limitations.append("license_unknown")
        if not self.content_digest:
            limitations.append("content_unpinned")
        if not self.external_version_id and not self.content_digest:
            limitations.append("external_content_unpinned")
        if self.handling_mode == "researcher_required":
            limitations.append("researcher_handling_required")
        return tuple(limitations)


@dataclass(frozen=True)
class ResourceVersionRead:
    """Structured outcome of reading one exact ResourceVersion."""

    status: str
    snapshot: ResourceVersionSnapshot | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if self.status != READ_CONFIRMED and self.snapshot is not None:
            raise ValueError("only a confirmed read may carry a snapshot")
        if self.status == READ_CONFIRMED and self.snapshot is None:
            raise ValueError("a confirmed read needs a snapshot")

    @classmethod
    def confirmed(cls, snapshot: ResourceVersionSnapshot) -> "ResourceVersionRead":
        return cls(status=READ_CONFIRMED, snapshot=snapshot)

    @classmethod
    def missing(
        cls, reason_code: str = errors.VERSION_MISSING
    ) -> "ResourceVersionRead":
        return cls(status=READ_MISSING, reason_code=reason_code)

    @classmethod
    def unavailable(
        cls, reason_code: str = errors.STORE_UNAVAILABLE
    ) -> "ResourceVersionRead":
        return cls(status=READ_UNAVAILABLE, reason_code=reason_code)


@dataclass(frozen=True)
class ResourceReviewRecord:
    review_id: str
    resource_version_id: str
    target_owner_id: str | None
    reviewer_id: str
    authority_reference: str
    decision: str
    reason: str
    evidence_reference: str | None
    decided_at: str
    use_scope: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    content_digest: str | None = None
    snapshot_digest: str | None = None
    unknown_facts: tuple[str, ...] = ()
    snapshot_status: str = READ_UNAVAILABLE
    target_location: ResourceVersionLocation | None = None


@dataclass(frozen=True)
class WikiAuditEvent:
    audit_event_id: str
    occurred_at: str
    actor_id: str
    action: str
    target_type: str
    target_id: str
    outcome: str
    reason_code: str
    detail: str | None = None
    related_review_id: str | None = None


@dataclass(frozen=True)
class Qualification:
    resource_version_id: str
    status: str
    reason_code: str
    review_id: str | None = None
    decided_at: str | None = None
    use_scope: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)
    unknown_facts: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ReviewOutcome:
    recorded: bool
    reason_code: str
    review_id: str | None
    audit_event_id: str
    qualification: Qualification
