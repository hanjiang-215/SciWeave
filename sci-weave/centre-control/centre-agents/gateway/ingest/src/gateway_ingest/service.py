"""Governance-event consumer for the Centre Agent (ai4-a2ba).

One governance event is turned into prereview work:

- ``formal_revision_published``: every reviewable candidate whose base is an
  older formal revision than the published one is a candidate whose report
  became invalid.  For each such candidate with a currently valid report, the
  consumer appends a ``base_moved`` decision through the domain management
  MCP (the report becomes stale) and records the candidate for recompute.
  Candidates based on the published revision itself are untouched, which is
  the "only affects dependents" guarantee.
- ``candidate_created`` / ``candidate_head_updated``: a full-snapshot
  prereview is triggered (a single run covering all candidates), debounced
  per candidate so repeated head updates in a short window produce one
  recompute request, not one per event.

Replay safety follows the message-queue contract: the consumer commits the
offset only after handling finishes, and duplicate deliveries are blocked by
the ``dedupe_key`` unique constraint plus the domain-side append-only report
log.  Permanently unparseable envelopes are recorded as observable errors, not
silently dropped (ai4-te1v failure boundary).

The consumer is deliberately queue-agnostic: it consumes ``GovernanceEvent``
objects and calls a ``DomainMCPClient``.  The CLI layer owns Kafka and
assembly.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from .domain_mcp import DomainMCPClient, ReviewableCandidate

SCHEMA_VERSION = 1

#: Governance event types this consumer has a handler for (ai4-te1v).
GOVERNANCE_EVENT_TYPES = frozenset({"candidate_created", "candidate_head_updated", "formal_revision_published"})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class GovernanceEnvelopeError(RuntimeError):
    """Envelope could not be turned into a usable governance event."""


@dataclass(frozen=True)
class GovernanceEvent:
    """One governance event after tolerant parsing of the wire envelope.

    Tolerant reading: the envelope may carry extra fields; the consumer
    ignores what it does not recognise and fails only on requirements that
    are missing (ai4-te1v schema/version rules).
    """

    event_id: str
    event_type: str
    mapping_domain_id: str
    occurred_at: str
    dedupe_key: str
    payload: dict[str, Any]

    @classmethod
    def from_dict(cls, body: dict[str, Any]) -> "GovernanceEvent":
        if not isinstance(body, dict):
            raise GovernanceEnvelopeError("envelope must be a JSON object")
        event_type = body.get("event_type")
        if not isinstance(event_type, str) or not event_type:
            raise GovernanceEnvelopeError("event_type is required")
        if event_type not in GOVERNANCE_EVENT_TYPES:
            raise GovernanceEnvelopeError(f"unsupported event_type: {event_type}")
        event_id = body.get("event_id") or body.get("message_id")
        if not isinstance(event_id, str) or not event_id:
            raise GovernanceEnvelopeError("event_id is required")
        schema_version = body.get("schema_version")
        if schema_version is not None:
            try:
                parsed_version = int(schema_version)
            except (TypeError, ValueError) as exc:
                # A non-numeric schema_version must be a poison-pill envelope,
                # not an uncaught ValueError that escapes the consumer loop and
                # stops the whole partition (ai4-t7jc).
                raise GovernanceEnvelopeError(
                    f"invalid schema_version: {schema_version!r}"
                ) from exc
            if parsed_version != SCHEMA_VERSION:
                raise GovernanceEnvelopeError(f"unsupported schema_version: {schema_version}")
        domain_id = body.get("mapping_domain_id") or body.get("wiki_domain_id")
        payload = body.get("payload")
        if isinstance(payload, dict):
            domain_id = domain_id or payload.get("mapping_domain_id") or payload.get("wiki_domain_id")
        if not isinstance(domain_id, str) or not domain_id:
            raise GovernanceEnvelopeError("mapping_domain_id is required")
        dedupe_key = body.get("dedupe_key")
        if not isinstance(dedupe_key, str) or not dedupe_key:
            raise GovernanceEnvelopeError("dedupe_key is required")
        occurred_at = body.get("occurred_at") or utc_now()
        if not isinstance(occurred_at, str):
            occurred_at = utc_now()
        return cls(
            event_id=event_id,
            event_type=event_type,
            mapping_domain_id=domain_id,
            occurred_at=occurred_at,
            dedupe_key=dedupe_key,
            payload=payload if isinstance(payload, dict) else {},
        )


@dataclass
class ConsumeOutcome:
    """Result of consuming one event: what was done and what the caller commits."""

    event_id: str
    event_type: str
    dedupe_key: str
    handled: bool
    duplicate: bool = False
    error_code: str | None = None
    stale_candidates: list[str] = field(default_factory=list)
    recompute_triggered: int = 0


class ProcessedKeyStore(Protocol):
    """Idempotency boundary: whether a dedupe key was already handled."""

    def already_processed(self, dedupe_key: str) -> bool: ...
    def mark_processed(self, dedupe_key: str) -> None: ...
    def record_error(self, dedupe_key: str, reason: str) -> None: ...


class SqliteProcessedKeyStore:
    """SQLite-backed dedupe and error log for the ingest consumer.

    Reuses the Work Agent SQLite discipline (WAL, row factory, RLock); the
    single table keeps handled keys and observable permanent errors in one
    place so ``offset`` commits stay safe across restarts.
    """

    def __init__(self, path: str) -> None:
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.RLock()
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS processed_events (
                dedupe_key TEXT PRIMARY KEY,
                status TEXT NOT NULL CHECK(status IN ('processed', 'error')),
                reason TEXT,
                handled_at TEXT NOT NULL
            );
            """
        )

    def already_processed(self, dedupe_key: str) -> bool:
        with self.lock:
            row = self.connection.execute(
                "SELECT status FROM processed_events WHERE dedupe_key = ?", (dedupe_key,)
            ).fetchone()
            return row is not None and row["status"] == "processed"

    def mark_processed(self, dedupe_key: str) -> None:
        with self.lock:
            self.connection.execute(
                """INSERT INTO processed_events (dedupe_key, status, handled_at) VALUES (?, 'processed', ?)
                   ON CONFLICT(dedupe_key) DO NOTHING""",
                (dedupe_key, utc_now()),
            )
            self.connection.commit()

    def record_error(self, dedupe_key: str, reason: str) -> None:
        with self.lock:
            self.connection.execute(
                """INSERT INTO processed_events (dedupe_key, status, reason, handled_at) VALUES (?, 'error', ?, ?)
                   ON CONFLICT(dedupe_key) DO UPDATE SET reason = excluded.reason""",
                (dedupe_key, reason, utc_now()),
            )
            self.connection.commit()

    def close(self) -> None:
        with self.lock:
            self.connection.close()


class MemoryProcessedKeyStore:
    """In-memory dedupe store for local tests and demos."""

    def __init__(self) -> None:
        self._processed: set[str] = set()
        self._errors: dict[str, str] = {}

    def already_processed(self, dedupe_key: str) -> bool:
        return dedupe_key in self._processed

    def mark_processed(self, dedupe_key: str) -> None:
        self._processed.add(dedupe_key)

    def record_error(self, dedupe_key: str, reason: str) -> None:
        self._errors[dedupe_key] = reason


class CentreGovernanceConsumer:
    """Consume one governance event and drive prereview work."""

    def __init__(
        self,
        domain_mcp: DomainMCPClient,
        keys: ProcessedKeyStore,
        *,
        debounce_window_seconds: int = 60,
        now: Any = None,
    ) -> None:
        self.domain_mcp = domain_mcp
        self.keys = keys
        self.debounce_window_seconds = debounce_window_seconds
        self._now = now or utc_now
        self._last_recompute_window: str | None = None

    def consume(self, envelope: dict[str, Any]) -> ConsumeOutcome:
        try:
            event = GovernanceEvent.from_dict(envelope)
        except GovernanceEnvelopeError as exc:
            # Permanent envelope defect (ai4-te1v): record observably, then
            # re-raise so the run loop commits and does not block the partition.
            self.keys.record_error(self._error_key(envelope), str(exc))
            raise
        if self.keys.already_processed(event.dedupe_key):
            return ConsumeOutcome(
                event_id=event.event_id,
                event_type=event.event_type,
                dedupe_key=event.dedupe_key,
                handled=False,
                duplicate=True,
            )
        try:
            if event.event_type == "formal_revision_published":
                outcome = self._handle_formal_revision(event)
            else:
                outcome = self._handle_candidate_event(event)
        except Exception as exc:  # transient/domain failure: leave uncommitted
            raise
        self.keys.mark_processed(event.dedupe_key)
        return outcome

    @staticmethod
    def _error_key(envelope: dict[str, Any]) -> str:
        if not isinstance(envelope, dict):
            return "unparseable-envelope"
        for name in ("dedupe_key", "event_id", "message_id", "event_type"):
            value = envelope.get(name)
            if isinstance(value, str) and value:
                return f"error:{value}"
        return "unparseable-envelope"

    def _handle_formal_revision(self, event: GovernanceEvent) -> ConsumeOutcome:
        new_revision = event.payload.get("formal_revision_id") or event.payload.get("formal_wiki_revision_id")
        if not isinstance(new_revision, str) or not new_revision:
            raise ValueError("formal_revision_id is required")
        candidates = self.domain_mcp.list_reviewable_candidates(event.mapping_domain_id)
        stale: list[str] = []
        for candidate in candidates:
            if not self._depends_on_older_base(candidate, new_revision):
                continue
            if candidate.prereview_status.get("status") == "report_current":
                self.domain_mcp.append_base_moved(
                    event.mapping_domain_id, candidate.candidate_id, candidate.candidate_head
                )
            stale.append(candidate.candidate_id)
        recompute = self._trigger_recompute(event, candidates)
        return ConsumeOutcome(
            event_id=event.event_id,
            event_type=event.event_type,
            dedupe_key=event.dedupe_key,
            handled=True,
            stale_candidates=stale,
            recompute_triggered=recompute,
        )

    def _handle_candidate_event(self, event: GovernanceEvent) -> ConsumeOutcome:
        candidate_id = event.payload.get("candidate_id") or event.payload.get("submission_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise ValueError("candidate_id is required")
        candidates = self.domain_mcp.list_reviewable_candidates(event.mapping_domain_id)
        recompute = self._trigger_recompute(event, candidates)
        return ConsumeOutcome(
            event_id=event.event_id,
            event_type=event.event_type,
            dedupe_key=event.dedupe_key,
            handled=True,
            recompute_triggered=recompute,
        )

    @staticmethod
    def _depends_on_older_base(candidate: ReviewableCandidate, new_revision: str) -> bool:
        """A candidate depends on the published revision only when its base
        differs from it; a candidate based on the new revision is untouched."""
        base = candidate.base_formal_revision_id
        if not base:
            return False
        return base != new_revision

    def _trigger_recompute(self, event: GovernanceEvent, candidates: list[ReviewableCandidate]) -> int:
        """Window-level debounce for candidate events: one full-snapshot review
        per short window regardless of which candidate changed, because each
        review already covers the whole candidate set (ai4-a2ba 快照审).

        Formal-revision events bypass the window: a new base always deserves a
        fresh review even if a candidate review just ran in the same window.
        """
        if event.event_type == "formal_revision_published":
            return 1 if candidates else 0
        window_key = self._now()[:19]
        if self._last_recompute_window == window_key:
            return 0
        self._last_recompute_window = window_key
        return 1


def make_event_body(*, event_type: str, domain_id: str, dedupe_key: str, payload: dict[str, Any], event_id: str | None = None) -> dict[str, Any]:
    """Build one governance wire envelope (matching the domain publisher)."""
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "event_type": event_type,
        "schema_version": 1,
        "mapping_domain_id": domain_id,
        "occurred_at": utc_now(),
        "dedupe_key": dedupe_key,
        "target": {"kind": "candidate" if event_type != "formal_revision_published" else "formal_revision", "id": dedupe_key},
        "payload": payload,
    }


def json_outcome(outcome: ConsumeOutcome) -> str:
    return json.dumps(
        {
            "event_id": outcome.event_id,
            "event_type": outcome.event_type,
            "dedupe_key": outcome.dedupe_key,
            "handled": outcome.handled,
            "duplicate": outcome.duplicate,
            "error_code": outcome.error_code,
            "stale_candidates": outcome.stale_candidates,
            "recompute_triggered": outcome.recompute_triggered,
        },
        ensure_ascii=False,
        sort_keys=True,
    )