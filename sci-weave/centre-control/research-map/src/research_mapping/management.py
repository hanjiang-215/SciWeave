from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from audit_trail import (
    AuditUnavailableError,
    AuditValidationError,
    CallRecord,
    begin_call,
    call_scope,
    finish_call,
    init_audit_table,
    open_connection,
    record_attempted,
)

from . import errors
from .candidate_domain import CandidateSubmissionResult
from .candidate_submission import MappingCandidateService
from .domain import FormalQueryResult
from .formal_query import FormalQueryService
from .governance_events import (
    NoopGovernanceEventPublisher,
    candidate_event,
    formal_revision_event,
)

_READ_CAPABILITIES = frozenset({"read", "centre"})
_CENTRE_CAPABILITIES = frozenset({"centre"})
_CANDIDATE_SUBMIT_CAPABILITIES = frozenset({"candidate_submit"})
_CANDIDATE_REVIEW_CAPABILITIES = frozenset({"candidate_review"})
_FORMALIZE_CAPABILITIES = frozenset({"formalize"})
_PREREVIEW_LOG_CAPABILITIES = frozenset({"prereview_log"})
_MERGED_CANDIDATE_CAPABILITIES = frozenset({"merged_candidate"})


class ManagementDenied(RuntimeError):
    """Stable denied outcome for an unauthorized management MCP call."""

    def __init__(self, tool: str) -> None:
        super().__init__("caller is not authorized for this tool")
        self.tool = tool


class ManagementConfigError(RuntimeError):
    pass


def _record_for(
    *, caller_id: str, channel_id: str, caller_type: str, service: str, tool: str,
    target_object_type: str | None = None, target_object_id: str | None = None,
    args_digest: str | None = None, refs: str | None = None,
) -> CallRecord:
    return CallRecord(
        caller_id=caller_id, channel_id=channel_id, caller_type=caller_type,
        service=service, tool=tool, target_object_type=target_object_type,
        target_object_id=target_object_id, args_digest=args_digest, refs=refs,
    )


@dataclass(frozen=True)
class ManagementCallOutcome:
    status: str
    result: dict[str, Any] | None = None
    reason_code: str | None = None
    error_code: str | None = None


class MappingManagementService:
    """Wrap domain services into a permissioned management MCP tool surface.

    Calls go through the domain services; nothing reaches SQLite or
    TerminusDB directly here. Reads are audited fail-open after completion,
    writes are audited fail-closed with invoked/completed phases. The caller
    identity and its capability tiers are resolved by the transport layer and
    enforced server-side by capability set membership.
    """

    def __init__(
        self,
        *,
        formal_query: FormalQueryService,
        candidate_service: MappingCandidateService,
        caller_capabilities: dict[str, frozenset[str]],
        audit_connection: sqlite3.Connection | None = None,
        service_name: str = "mapping-management",
        review_service=None,
        formalization_service=None,
        sqlite_store=None,
        candidate_reader=None,
        prereview_log=None,
        merged_candidate_service=None,
        governance_events=None,
    ) -> None:
        self._formal_query = formal_query
        self._candidate_service = candidate_service
        self._review_service = review_service
        self._formalization_service = formalization_service
        self._sqlite = sqlite_store
        self._candidate_reader = candidate_reader
        self._prereview_log = prereview_log
        self._merged_candidate_service = merged_candidate_service
        self._capabilities = caller_capabilities
        self._audit = audit_connection
        self._service = service_name
        self._governance_events = governance_events or NoopGovernanceEventPublisher()

    def call_tool(self, tool: str, arguments: dict[str, Any], *, actor_id: str, channel_id: str = "mcp", caller_type: str = "agent") -> ManagementCallOutcome:
        handler = self._handlers().get(tool)
        if handler is None:
            return ManagementCallOutcome("error", reason_code="unknown_tool", error_code="unknown_tool")
        try:
            self._require_authorized(tool, actor_id)
        except ManagementDenied:
            return ManagementCallOutcome("denied", reason_code="forbidden", error_code="forbidden")
        if tool in _WRITE_TOOLS:
            return self._audited_write(handler, tool, arguments, actor_id, channel_id, caller_type)
        return self._audited_read(handler, tool, arguments, actor_id, channel_id, caller_type)

    def _handlers(self) -> dict[str, Any]:
        handlers: dict[str, Any] = {
            "get_formal_mapping": self._get_formal_mapping,
            "get_formal_mapping_at_revision": self._get_formal_mapping_at_revision,
            "list_candidates": self._list_candidates,
            "submit_candidate": self._submit_candidate,
        }
        if self._candidate_reader is not None:
            handlers["list_reviewable_candidates"] = self._list_reviewable_candidates
        if self._review_service is not None:
            handlers["preview_candidate"] = self._preview_candidate
            handlers["create_merge_request"] = self._create_merge_request
            handlers["record_review"] = self._record_review
        if self._formalization_service is not None:
            handlers["formalize_candidate"] = self._formalize_candidate
            handlers["reconcile_formalization"] = self._reconcile_formalization
        if self._prereview_log is not None:
            handlers["append_prereview_log"] = self._append_prereview_log
        if self._merged_candidate_service is not None:
            handlers["create_merged_candidate"] = self._create_merged_candidate
        return handlers

    def _create_merged_candidate(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        """Create one merged candidate branch from source candidates.

        Only a new branch is created; existing candidates are never edited.
        The author field records every source author and source authors get
        no operation rights; merged candidates may not be merged again.
        """
        if self._merged_candidate_service is None:
            raise RuntimeError("merged_candidate_service is not configured")
        change_set = arguments.get("change_set")
        if not isinstance(change_set, dict):
            raise ValueError("change_set is required")
        source_proposal_ids = arguments.get("source_proposal_ids")
        if not isinstance(source_proposal_ids, list) or not source_proposal_ids:
            raise ValueError("source_proposal_ids is required and must be a non-empty array")
        result = self._merged_candidate_service.create_merged(
            mapping_domain_id=_required(arguments, "mapping_domain_id"),
            source_proposal_ids=[str(item) for item in source_proposal_ids],
            base_formal_revision_id=_required(arguments, "base_formal_revision_id"),
            change_set=change_set,
            idempotency_key=_required(arguments, "idempotency_key"),
        )
        return _candidate_result(result)

    def _append_prereview_log(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        """Append one prereview report, or one invalidation decision.

        ``reason`` present means a decision row is appended (head_moved or
        base_moved); otherwise a report row is appended under the
        candidate-head-rules unique key. Both paths stay append-only.
        """
        if self._prereview_log is None:
            raise RuntimeError("prereview_log is not configured")
        candidate_id = _required(arguments, "candidate_id")
        candidate_head = _required(arguments, "candidate_head")
        reason = arguments.get("reason")
        if isinstance(reason, str) and reason:
            outcome = self._prereview_log.append_decision(
                candidate_id=candidate_id,
                candidate_head=candidate_head,
                reason=reason,
                superseding_report_id=arguments.get("superseding_report_id"),
            )
            return {
                "status": outcome.status,
                "decision_id": outcome.decision_id,
                "report_id": outcome.report_id,
                "candidate_id": outcome.candidate_id,
                "duplicate": outcome.duplicate,
                "reason_code": outcome.reason_code,
            }
        base = arguments.get("base_formal_revision_id")
        rule_set_version = _required(arguments, "rule_set_version")
        verdict = _required(arguments, "verdict")
        checks = arguments.get("checks")
        if not isinstance(checks, list):
            raise ValueError("checks must be an array")
        conflict_matrix = arguments.get("conflict_matrix")
        if conflict_matrix is not None and not isinstance(conflict_matrix, list):
            raise ValueError("conflict_matrix must be an array")
        outcome = self._prereview_log.append_report(
            candidate_id=candidate_id,
            candidate_head=candidate_head,
            base_formal_revision_id=base if isinstance(base, str) and base else None,
            rule_set_version=rule_set_version,
            checks=checks,
            verdict=verdict,
            conflict_matrix=conflict_matrix,
        )
        return {
            "status": outcome.status,
            "report_id": outcome.report_id,
            "candidate_id": outcome.candidate_id,
            "duplicate": outcome.duplicate,
            "reason_code": outcome.reason_code,
        }

    def _require_authorized(self, tool: str, actor_id: str) -> None:
        required = _TOOL_CAPABILITIES[tool]
        granted = self._capabilities.get(actor_id, frozenset())
        if not required & granted:
            raise ManagementDenied(tool)

    def _audited_read(self, handler, tool, arguments, actor_id, channel_id, caller_type):
        args_digest = _digest(arguments)
        try:
            outcome = handler(arguments, actor_id)
        except ManagementDenied:
            raise
        except Exception as error:
            reason = getattr(error, "reason_code", None) or _classify(error)
            if self._audit is not None:
                try:
                    record_attempted(self._audit, _record_for(
                        caller_id=actor_id, channel_id=channel_id, caller_type=caller_type,
                        service=self._service, tool=tool, args_digest=args_digest,
                        error_code=reason, target_object_type=_target_type(tool),
                        target_object_id=_target_id(arguments, tool),
                    ))
                except AuditValidationError:
                    raise
                except Exception:
                    pass
            return ManagementCallOutcome("error", reason_code=reason, error_code=reason)
        if self._audit is not None:
            try:
                record_attempted(self._audit, _record_for(
                    caller_id=actor_id, channel_id=channel_id, caller_type=caller_type,
                    service=self._service, tool=tool, args_digest=args_digest,
                    target_object_type=_target_type(tool), target_object_id=_target_id(arguments, tool),
                ))
            except AuditValidationError:
                raise
            except Exception:
                pass
        return ManagementCallOutcome("ok", result=outcome)

    def _audited_write(self, handler, tool, arguments, actor_id, channel_id, caller_type):
        args_digest = _digest(arguments)
        record = _record_for(
            caller_id=actor_id, channel_id=channel_id, caller_type=caller_type,
            service=self._service, tool=tool, args_digest=args_digest,
            target_object_type=_target_type(tool), target_object_id=_target_id(arguments, tool),
        )
        if self._audit is not None:
            try:
                call_id = begin_call(self._audit, record)
            except (AuditUnavailableError, AuditValidationError):
                return ManagementCallOutcome("error", reason_code="audit_unavailable", error_code="audit_unavailable")
        else:
            call_id = None
        try:
            outcome = handler(arguments, actor_id)
        except ManagementDenied:
            raise
        except Exception as error:
            reason = getattr(error, "reason_code", None) or _classify(error)
            if call_id is not None and self._audit is not None:
                finish_call(self._audit, call_id, result="error", error_code=reason)
            return ManagementCallOutcome("error", reason_code=reason, error_code=reason)
        if call_id is not None and self._audit is not None:
            finish_call(self._audit, call_id, result="ok")
        return ManagementCallOutcome("ok", result=outcome)

    def _get_formal_mapping(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        domain_id = _required(arguments, "mapping_domain_id")
        result = self._formal_query.get_current(domain_id)
        return _formal_query_result(result)

    def _get_formal_mapping_at_revision(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        domain_id = _required(arguments, "mapping_domain_id")
        revision_id = _required(arguments, "formal_revision_id")
        result = self._formal_query.get_by_revision(domain_id, revision_id)
        return _formal_query_result(result)

    def _list_candidates(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        submission_id = _required(arguments, "submission_id")
        if self._sqlite is None:
            return {"submission_id": submission_id, "candidate": None}
        record = self._sqlite.get_candidate_for_submission(submission_id)
        if record is None:
            return {"submission_id": submission_id, "candidate": None}
        return {"submission_id": submission_id, "candidate": record}

    def _list_reviewable_candidates(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        domain_id = _required(arguments, "mapping_domain_id")
        if self._candidate_reader is None:
            raise RuntimeError("candidate_reader is not configured")
        candidates: list[dict[str, Any]] = []
        for item in self._candidate_reader.list_reviewable(domain_id):
            candidate: dict[str, Any] = {
                "submission_id": item.submission_id,
                "proposal_id": item.proposal_id,
                "submitter_id": item.submitter_id,
                "base_formal_revision_id": item.base_formal_revision_id,
                "candidate_commit_id": item.candidate_commit_id,
                "candidate_head": item.candidate_head,
                "proposal_status": item.proposal_status,
                "snapshot_status": item.snapshot_status,
                "reason_code": item.reason_code,
                "documents": list(item.documents),
            }
            if self._prereview_log is not None and item.candidate_head:
                # Owner-visible prereview gate state (ai4-a2ba): the candidate
                # blocks on a missing or stale report. candidate_id is the
                # submission id, matching the governance-event target identity.
                candidate["prereview_status"] = self._prereview_log.status_for_candidate(
                    item.submission_id, item.candidate_head,
                )
            candidates.append(candidate)
        return {"mapping_domain_id": domain_id, "candidates": candidates}

    def _submit_candidate(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        change_set = arguments.get("change_set")
        idempotency_key = _required(arguments, "idempotency_key")
        if not isinstance(change_set, dict):
            raise ValueError("change_set is required")
        result = self._candidate_service.submit(change_set, idempotency_key)
        if result.status in {"submitted", "confirmed", "ok"}:
            domain_id = str(change_set.get("mapping_domain_id") or arguments.get("mapping_domain_id") or "")
            self._publish_safely(
                candidate_event(
                    mapping_domain_id=domain_id,
                    submission_id=result.submission_id,
                    proposal_id=result.proposal_id,
                    candidate_head=result.commit_hash or result.candidate_commit_id,
                )
            )
        return _candidate_result(result)

    def _preview_candidate(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        preview = self._review_service.preview(
            _required(arguments, "proposal_id"),
            _required(arguments, "base_formal_revision_id"),
            _required(arguments, "candidate_head"),
        )
        return {
            "status": preview.status,
            "reason_code": preview.reason_code,
            "preview_id": preview.preview_id,
            "evidence_id": preview.evidence_id,
            "changes": list(preview.changes),
            "affected_objects": list(preview.affected_objects),
            "route_impact": preview.route_impact,
        }

    def _create_merge_request(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        """Lock one ready preview into a merge-request buffer.

        Until this tool existed, `create_buffer` was only reachable from tests
        and a demo script, so the buffer id that `record_review` and
        `formalize_candidate` take could not be produced through MCP at all: the
        Wiki side had `create_wiki_merge_request` and the Mapping side did not.
        A Project Owner holding `candidate_review` could preview a candidate and
        then had nowhere to send the decision.

        The buffer id stays derived from the preview (``create_buffer`` already
        computes it as a digest, so the same preview yields the same buffer, and
        a retry after a crash is idempotent). That is why the caller passes the
        preview and not an id: an owner-chosen id would make the pairing between
        preview and buffer a matter of caller discipline.
        """
        buffer = self._review_service.create_buffer(_required(arguments, "preview_id"))
        return {
            "buffer_id": buffer.buffer_id,
            "preview_id": buffer.preview_id,
            "proposal_id": buffer.proposal_id,
            "base_formal_revision_id": buffer.base_formal_revision_id,
            "candidate_head": buffer.candidate_commit_hash,
            "status": "pending",
        }

    def _record_review(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        decision = self._review_service.record_review(
            _required(arguments, "buffer_id"),
            actor_id,
            _required(arguments, "decision"),
            _required(arguments, "reason"),
        )
        return {
            "event_id": decision.event_id,
            "buffer_id": decision.buffer_id,
            "actor_id": decision.actor_id,
            "decision": decision.decision,
            "reason": decision.reason,
            "occurred_at": decision.occurred_at,
        }

    def _formalize_candidate(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        outcome = self._formalization_service.formalize(
            _required(arguments, "merge_request_id"),
            _required(arguments, "operation_id"),
        )
        if outcome.status == "succeeded" and outcome.formal_revision_id:
            # Prefer the domain persisted alongside the activation over the
            # optional tool argument: callers legitimately omit
            # ``mapping_domain_id`` (React's IDE/CLI only know the merge request),
            # and publishing with an empty domain leaves the coordinator blind to
            # the new revision so root-task dispatch silently no-ops for that
            # domain. Fall back to the argument only when the outcome lacks it.
            domain = outcome.mapping_domain_id or _text(arguments.get("mapping_domain_id")) or ""
            self._publish_safely(
                formal_revision_event(
                    mapping_domain_id=domain,
                    formal_revision_id=outcome.formal_revision_id,
                    merge_request_id=arguments.get("merge_request_id"),
                )
            )
        return _formalization_outcome(outcome)

    def _publish_safely(self, event) -> None:
        """Publish one governance event without breaking the domain write.

        A queue outage must not roll back an already-persisted governance fact;
        the event is best-effort notification and Centre Agent recovers via
        full-snapshot scans and formal-revision events.
        """
        try:
            self._governance_events.publish(event)
        except Exception:
            return

    def _reconcile_formalization(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        outcome = self._formalization_service.reconcile(_required(arguments, "operation_id"))
        return _formalization_outcome(outcome)


_WRITE_TOOLS = frozenset({
    "submit_candidate",
    "preview_candidate",
    "create_merge_request",
    "record_review",
    "formalize_candidate",
    "reconcile_formalization",
    "append_prereview_log",
    "create_merged_candidate",
})

_TOOL_CAPABILITIES = {
    "get_formal_mapping": _READ_CAPABILITIES,
    "get_formal_mapping_at_revision": _READ_CAPABILITIES,
    "list_candidates": _READ_CAPABILITIES,
    "list_reviewable_candidates": _CENTRE_CAPABILITIES,
    "submit_candidate": _CANDIDATE_SUBMIT_CAPABILITIES,
    "preview_candidate": _CANDIDATE_REVIEW_CAPABILITIES,
    "create_merge_request": _CANDIDATE_REVIEW_CAPABILITIES,
    "record_review": _CANDIDATE_REVIEW_CAPABILITIES,
    "formalize_candidate": _FORMALIZE_CAPABILITIES,
    "reconcile_formalization": _FORMALIZE_CAPABILITIES,
    "append_prereview_log": _PREREVIEW_LOG_CAPABILITIES,
    "create_merged_candidate": _MERGED_CANDIDATE_CAPABILITIES,
}

TOOL_DEFINITIONS = [
    {
        "name": "get_formal_mapping",
        "description": "Read the current formal Research Mapping graph for a domain. Requires the read or centre capability.",
        "inputSchema": {
            "type": "object",
            "required": ["mapping_domain_id"],
            "properties": {"mapping_domain_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_formal_mapping_at_revision",
        "description": "Read the exact formal Research Mapping snapshot pinned by a specific formal_revision_id (historical activated revision), using the same consistency gates as the current pointer read. Requires the read or centre capability.",
        "inputSchema": {
            "type": "object",
            "required": ["mapping_domain_id", "formal_revision_id"],
            "properties": {
                "mapping_domain_id": {"type": "string"},
                "formal_revision_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "list_candidates",
        "description": "Read the candidate record associated with a submission. Requires the read or centre capability.",
        "inputSchema": {
            "type": "object",
            "required": ["submission_id"],
            "properties": {"submission_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "list_reviewable_candidates",
        "description": "Read the same-time reviewable candidate set (not merged, rejected or abandoned) with exact candidate head, base formal revision and immutable content snapshot. Requires the centre capability; this is a central pre-review queue, not a researcher read.",
        "inputSchema": {
            "type": "object",
            "required": ["mapping_domain_id"],
            "properties": {"mapping_domain_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "submit_candidate",
        "description": "Submit a Mapping candidate change set against the exact formal base. Requires the candidate_submit capability.",
        "inputSchema": {
            "type": "object",
            "required": ["change_set", "idempotency_key"],
            "properties": {
                "change_set": {"type": "object"},
                "idempotency_key": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "preview_candidate",
        "description": "Build immutable diff review evidence for a fixed candidate head. Requires the candidate_review capability.",
        "inputSchema": {
            "type": "object",
            "required": ["proposal_id", "base_formal_revision_id", "candidate_head"],
            "properties": {
                "proposal_id": {"type": "string"},
                "base_formal_revision_id": {"type": "string"},
                "candidate_head": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "create_merge_request",
        "description": "Lock a ready candidate preview into a merge-request buffer and return its buffer_id. Requires the candidate_review capability.",
        "inputSchema": {
            "type": "object",
            "required": ["preview_id"],
            "properties": {"preview_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "record_review",
        "description": "Record a review decision for a merge-request buffer. Requires the candidate_review capability.",
        "inputSchema": {
            "type": "object",
            "required": ["buffer_id", "decision", "reason"],
            "properties": {
                "buffer_id": {"type": "string"},
                "decision": {"type": "string", "enum": ["approved", "returned", "rejected"]},
                "reason": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "formalize_candidate",
        "description": "Promote an Owner-approved candidate through atomic SQLite activation. Requires the formalize capability.",
        "inputSchema": {
            "type": "object",
            "required": ["merge_request_id", "operation_id"],
            "properties": {
                "merge_request_id": {"type": "string"},
                "operation_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "reconcile_formalization",
        "description": "Resume the same formalization operation identity. Requires the formalize capability.",
        "inputSchema": {
            "type": "object",
            "required": ["operation_id"],
            "properties": {"operation_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "append_prereview_log",
        "description": "Append one prereview report, or one invalidation decision, to the Mapping governance log. Append-only: reports and decisions are never edited. Passing ``reason`` (head_moved/base_moved) appends an invalidation decision; otherwise a report row is appended under the (candidate_id, candidate_head, rule_set_version, base_formal_revision_id) unique key. Requires the centre capability.",
        "inputSchema": {
            "type": "object",
            "required": ["candidate_id", "candidate_head"],
            "properties": {
                "candidate_id": {"type": "string"},
                "candidate_head": {"type": "string"},
                "base_formal_revision_id": {"type": ["string", "null"]},
                "rule_set_version": {"type": "string"},
                "verdict": {"type": "string", "enum": ["passed", "failed"]},
                "checks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "verdict": {"type": "string"},
                            "reason_code": {"type": ["string", "null"]},
                            "evidence_summary": {"type": ["string", "null"]},
                        },
                    },
                },
                "conflict_matrix": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "candidate_id": {"type": "string"},
                            "overlap": {"type": "string"},
                        },
                    },
                },
                "reason": {"type": "string", "enum": ["head_moved", "base_moved"]},
                "superseding_report_id": {"type": ["string", "null"]},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "create_merged_candidate",
        "description": "Create one merged Mapping candidate branch from source candidates on the same formal base. Only creates a new branch; existing candidates are never edited. The author field records every source author; source authors get no operation rights; a merged candidate may not be merged again. Requires the merged_candidate capability.",
        "inputSchema": {
            "type": "object",
            "required": ["mapping_domain_id", "source_proposal_ids", "base_formal_revision_id", "change_set", "idempotency_key"],
            "properties": {
                "mapping_domain_id": {"type": "string"},
                "source_proposal_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "base_formal_revision_id": {"type": "string"},
                "change_set": {
                    "type": "object",
                    "properties": {
                        "submission_id": {"type": "string"},
                        "proposal_id": {"type": "string"},
                        "nodes": {"type": "array"},
                        "edges": {"type": "array"},
                    },
                },
                "idempotency_key": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
]


def _required(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _digest(arguments: dict[str, Any]) -> str:
    from .canonical import sha256_json
    return sha256_json(arguments)


def _formal_query_result(result: FormalQueryResult) -> dict[str, Any]:
    if result.status != "available":
        # Failure shapes stay exactly as they were: there is no revision, so
        # there is no published_by to report, and callers key their handling
        # off the absence of graph content rather than off a null field.
        return {"status": result.status, "reason_code": result.reason_code}
    return {
        "status": result.status,
        "reason_code": result.reason_code,
        "mapping_domain_id": result.mapping_domain_id,
        "formal_revision_id": result.formal_revision_id,
        "store_id": result.store_id,
        "branch_id": result.branch_id,
        "commit_hash": result.commit_hash,
        "content_digest": result.content_digest,
        # Both formal entry points share this projection, so exposing the
        # approver here is what keeps get_formal_mapping and
        # get_formal_mapping_at_revision from disagreeing (ai4-2raq).
        "published_by": result.published_by,
        "documents": list(result.documents),
    }


def _candidate_result(result: CandidateSubmissionResult) -> dict[str, Any]:
    payload = asdict(result)
    return {key: value for key, value in payload.items() if value is not None}


def _formalization_outcome(outcome) -> dict[str, Any]:
    return {
        "status": outcome.status,
        "formalization_operation_id": outcome.formalization_operation_id,
        "result_id": outcome.result_id,
        "formal_revision_id": outcome.formal_revision_id,
        "reason_code": outcome.reason_code,
        "attempt_number": outcome.attempt_number,
    }


def _classify(error: Exception) -> str:
    if isinstance(error, (ValueError, TypeError)):
        return "invalid_arguments"
    if isinstance(error, sqlite3.Error):
        return "store_error"
    return "internal"


def _target_type(tool: str) -> str:
    return {
        "get_formal_mapping": "MappingDomain",
        "get_formal_mapping_at_revision": "MappingFormalRevision",
        "list_candidates": "MappingSubmission",
        "list_reviewable_candidates": "MappingDomain",
        "submit_candidate": "MappingSubmission",
        "preview_candidate": "MappingCandidate",
        "create_merge_request": "MappingMergeRequest",
        "record_review": "MappingMergeRequest",
        "formalize_candidate": "MappingMergeRequest",
        "reconcile_formalization": "MappingFormalizationOperation",
        "append_prereview_log": "MappingPrereviewReport",
        "create_merged_candidate": "MappingCandidate",
    }.get(tool)


def _target_id(arguments: dict[str, Any], tool: str) -> str | None:
    if tool == "get_formal_mapping":
        return _text(arguments.get("mapping_domain_id"))
    if tool == "get_formal_mapping_at_revision":
        return _text(arguments.get("formal_revision_id"))
    if tool == "list_candidates":
        return _text(arguments.get("submission_id"))
    if tool == "list_reviewable_candidates":
        return _text(arguments.get("mapping_domain_id"))
    if tool == "submit_candidate":
        return _text(arguments.get("idempotency_key"))
    if tool == "create_merge_request":
        return _text(arguments.get("preview_id"))
    if tool in {"preview_candidate", "record_review", "formalize_candidate"}:
        return _text(arguments.get("proposal_id")) or _text(arguments.get("buffer_id")) or _text(arguments.get("merge_request_id"))
    if tool == "reconcile_formalization":
        return _text(arguments.get("operation_id"))
    if tool == "append_prereview_log":
        return _text(arguments.get("candidate_id"))
    if tool == "create_merged_candidate":
        return _text(arguments.get("idempotency_key"))
    return None


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def open_audit_database(path: str) -> sqlite3.Connection:
    connection = open_connection(path)
    init_audit_table(connection)
    return connection
