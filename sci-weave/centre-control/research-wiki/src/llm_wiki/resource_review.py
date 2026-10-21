from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Protocol

from . import errors
from .domain import (
    READ_CONFIRMED,
    READ_MISSING,
    READ_UNAVAILABLE,
    AuthorityContext,
    Qualification,
    ResourceReviewRecord,
    ResourceVersionLocation,
    ResourceVersionRead,
    ResourceVersionSnapshot,
    ReviewOutcome,
    WikiAuditEvent,
)
from .sqlite_store import SqliteStore
from .terminus_store import ExactResourceVersionStore

Decision = str

_VALID_DECISIONS = ("approved", "rejected", "revoked")


class AuthorizationVerifier(Protocol):
    """Verifies a delegated reviewer's authority for one ResourceVersion."""

    def verify(
        self,
        actor_id: str,
        resource_version_id: str,
        owner_id: str,
        authority_context: AuthorityContext,
    ) -> bool: ...


class ExactVersionLocationSource(Protocol):
    """Supplies the exact TerminusDB location that pinned one ResourceVersion.

    The version id alone cannot address a historical snapshot, so the location
    must come from a governance record written when the version was stored.
    Implementations return ``None`` when no such record exists; the service then
    refuses to read rather than falling back to a branch head.
    """

    def locate(self, resource_version_id: str) -> ResourceVersionLocation | None: ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ResourceReviewService:
    """Append-only qualification decisions for exact ResourceVersions."""

    def __init__(
        self,
        *,
        sqlite_store: SqliteStore,
        terminus_store: ExactResourceVersionStore,
        authorizer: AuthorizationVerifier | None = None,
        location_source: ExactVersionLocationSource | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._sqlite = sqlite_store
        self._terminus = terminus_store
        self._authorizer = authorizer
        self._location_source = location_source
        self._clock = clock or _utc_now

    def record_decision(
        self,
        resource_version_id: str,
        actor: str,
        decision: Decision,
        reason: str,
        evidence: str | None = None,
        scope: Sequence[str] = (),
        authority_context: AuthorityContext | None = None,
        limitations: Sequence[str] = (),
    ) -> ReviewOutcome:
        if decision not in _VALID_DECISIONS:
            raise ValueError(
                "decision must be one of: " + ", ".join(_VALID_DECISIONS)
            )
        actor_id = actor.strip() if isinstance(actor, str) else ""
        if not actor_id:
            raise ValueError("actor must be a non-empty identity")
        reason_text = reason.strip() if isinstance(reason, str) else ""
        if not reason_text:
            raise ValueError("reason must be non-empty")

        use_scope = _normalise(scope)
        explicit_limitations = _normalise(limitations)
        now = self._clock()

        snapshot, read_status, read_error, location = self._read(resource_version_id)
        if decision == "approved" and snapshot is None:
            return self._deny(
                resource_version_id,
                actor_id,
                reason_text,
                read_error or errors.STORE_UNAVAILABLE,
                now,
            )

        prior = self._sqlite.latest_review(resource_version_id)
        owner_id = (
            snapshot.owner_id
            if snapshot is not None
            else (prior.target_owner_id if prior is not None else None)
        )
        if not owner_id:
            return self._deny(
                resource_version_id, actor_id, reason_text, errors.OWNER_UNKNOWN, now
            )

        authority_reference, authority_error = self._authority_reference(
            resource_version_id,
            actor_id,
            owner_id,
            authority_context,
        )
        if authority_reference is None:
            return self._deny(
                resource_version_id,
                actor_id,
                reason_text,
                authority_error or errors.AUTHORITY_UNVERIFIED,
                now,
            )

        if snapshot is not None:
            unknown_facts = snapshot.derive_unknown_facts()
            derived_limitations = snapshot.derive_limitations()
            content_digest = snapshot.content_digest
        else:
            unknown_facts = ("version_unconfirmed",)
            derived_limitations = ("version_unconfirmed",)
            content_digest = None

        review = ResourceReviewRecord(
            review_id=str(uuid.uuid4()),
            resource_version_id=resource_version_id,
            target_owner_id=owner_id,
            reviewer_id=actor_id,
            authority_reference=authority_reference,
            decision=decision,
            reason=reason_text,
            evidence_reference=evidence,
            decided_at=now,
            use_scope=use_scope,
            limitations=_merge(explicit_limitations, derived_limitations),
            content_digest=content_digest,
            snapshot_digest=snapshot.snapshot_digest if snapshot is not None else None,
            unknown_facts=unknown_facts,
            snapshot_status=read_status,
            target_location=location,
        )
        self._sqlite.add_review(review)

        event = WikiAuditEvent(
            audit_event_id=str(uuid.uuid4()),
            occurred_at=now,
            actor_id=actor_id,
            action="resource_version_review",
            target_type="ResourceVersion",
            target_id=resource_version_id,
            outcome=decision,
            reason_code=errors.DECISION_RECORDED,
            detail=reason_text,
            related_review_id=review.review_id,
        )
        self._sqlite.add_audit_event(event)

        return ReviewOutcome(
            recorded=True,
            reason_code=errors.DECISION_RECORDED,
            review_id=review.review_id,
            audit_event_id=event.audit_event_id,
            qualification=self.get_current_qualification(resource_version_id),
        )

    def get_current_qualification(
        self, resource_version_id: str, requested_scope: str | None = None
    ) -> Qualification:
        reviews = self._sqlite.list_reviews(resource_version_id)
        applicable = [
            review
            for review in reviews
            if requested_scope is None
            or not review.use_scope
            or requested_scope in review.use_scope
        ]
        if not applicable:
            return Qualification(
                resource_version_id=resource_version_id,
                status="pending",
                reason_code=errors.NO_EFFECTIVE_DECISION,
            )
        latest = applicable[-1]
        return Qualification(
            resource_version_id=resource_version_id,
            status=latest.decision,
            reason_code=errors.DECISION_RECORDED,
            review_id=latest.review_id,
            decided_at=latest.decided_at,
            use_scope=latest.use_scope,
            limitations=latest.limitations,
            unknown_facts=latest.unknown_facts,
        )

    def _read(
        self, resource_version_id: str
    ) -> tuple[
        ResourceVersionSnapshot | None, str, str | None, ResourceVersionLocation | None
    ]:
        location = self._locate(resource_version_id)
        if location is None:
            return None, READ_UNAVAILABLE, errors.EXACT_VERSION_LOCATION_UNKNOWN, None
        try:
            outcome = self._terminus.read_resource_version(
                location, resource_version_id
            )
        except Exception:
            return None, READ_UNAVAILABLE, errors.STORE_UNAVAILABLE, location
        if not isinstance(outcome, ResourceVersionRead):
            return None, READ_UNAVAILABLE, errors.STORE_UNAVAILABLE, location
        if outcome.status == READ_CONFIRMED:
            snapshot = outcome.snapshot
            if snapshot is None or snapshot.resource_version_id != resource_version_id:
                return None, "unconfirmed", errors.VERSION_ID_MISMATCH, location
            return snapshot, READ_CONFIRMED, None, location
        if outcome.status == READ_MISSING:
            return None, READ_MISSING, errors.VERSION_MISSING, location
        return None, READ_UNAVAILABLE, errors.STORE_UNAVAILABLE, location

    def _locate(self, resource_version_id: str) -> ResourceVersionLocation | None:
        if self._location_source is None:
            return None
        try:
            location = self._location_source.locate(resource_version_id)
        except Exception:
            return None
        if not isinstance(location, ResourceVersionLocation):
            return None
        return location

    def _authority_reference(
        self,
        resource_version_id: str,
        actor_id: str,
        owner_id: str,
        authority_context: AuthorityContext | None,
    ) -> tuple[str | None, str | None]:
        if actor_id == owner_id:
            return f"owner:{owner_id}", None
        reference = (
            authority_context.authority_reference.strip()
            if authority_context is not None
            and isinstance(authority_context.authority_reference, str)
            else ""
        )
        if not reference:
            return None, errors.AUTHORITY_MISSING
        if self._authorizer is None:
            return None, errors.AUTHORITY_UNVERIFIED
        try:
            verified = self._authorizer.verify(
                actor_id, resource_version_id, owner_id, authority_context
            )
        except Exception:
            verified = False
        if not verified:
            return None, errors.AUTHORITY_UNVERIFIED
        return reference, None

    def _deny(
        self,
        resource_version_id: str,
        actor_id: str,
        reason: str,
        reason_code: str,
        now: str,
    ) -> ReviewOutcome:
        event = WikiAuditEvent(
            audit_event_id=str(uuid.uuid4()),
            occurred_at=now,
            actor_id=actor_id,
            action="resource_review_attempt",
            target_type="ResourceVersion",
            target_id=resource_version_id,
            outcome="denied",
            reason_code=reason_code,
            detail=reason,
            related_review_id=None,
        )
        self._sqlite.add_audit_event(event)
        return ReviewOutcome(
            recorded=False,
            reason_code=reason_code,
            review_id=None,
            audit_event_id=event.audit_event_id,
            qualification=self.get_current_qualification(resource_version_id),
        )


def _normalise(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, str):
        values = (values,)
    return tuple(str(value).strip() for value in values if str(value).strip())


def _merge(first: tuple[str, ...], second: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    for value in first + second:
        if value not in merged:
            merged.append(value)
    return tuple(merged)
