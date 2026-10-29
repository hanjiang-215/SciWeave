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
    finish_call,
    init_audit_table,
    open_connection,
    record_attempted,
)

from .candidate_submission import WikiCandidateService
from .formal_domain import WikiFormalQueryResult
from .formal_query import WikiFormalQueryService
from .governance_events import (
    NoopGovernanceEventPublisher,
    candidate_event,
    formal_revision_event,
)

_READ_CAPABILITIES = frozenset({"read", "centre"})
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


@dataclass(frozen=True)
class ManagementCallOutcome:
    status: str
    result: dict[str, Any] | None = None
    reason_code: str | None = None
    error_code: str | None = None


def _record_for(*, caller_id: str, channel_id: str, caller_type: str, service: str, tool: str,
                target_object_type: str | None = None, target_object_id: str | None = None,
                args_digest: str | None = None, refs: str | None = None) -> CallRecord:
    return CallRecord(
        caller_id=caller_id, channel_id=channel_id, caller_type=caller_type,
        service=service, tool=tool, target_object_type=target_object_type,
        target_object_id=target_object_id, args_digest=args_digest, refs=refs,
    )


def _digest(arguments: dict[str, Any]) -> str:
    from .canonical import sha256_json
    return sha256_json(arguments)


def _required(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _classify(error: Exception) -> str:
    if isinstance(error, (ValueError, TypeError)):
        return "invalid_arguments"
    if isinstance(error, sqlite3.Error):
        return "store_error"
    return "internal"


class WikiManagementService:
    """Wrap Wiki domain services into a permissioned management MCP surface.

    Mirrors MappingManagementService: calls go through the domain services,
    reads are audited fail-open after completion, writes are audited fail-closed
    with invoked/completed phases, and capability tiers are enforced
    server-side by the transport layer.
    """

    def __init__(
        self,
        *,
        formal_query: WikiFormalQueryService,
        candidate_service: WikiCandidateService,
        caller_capabilities: dict[str, frozenset[str]],
        audit_connection: sqlite3.Connection | None = None,
        service_name: str = "wiki-management",
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
            "get_formal_wiki": self._get_formal_wiki,
            "list_wiki_candidates": self._list_wiki_candidates,
            "submit_wiki_candidate": self._submit_wiki_candidate,
        }
        if self._candidate_reader is not None:
            handlers["list_reviewable_wiki_candidates"] = self._list_reviewable_wiki_candidates
        if self._review_service is not None:
            handlers["preview_wiki_review"] = self._preview_wiki_review
            handlers["create_wiki_merge_request"] = self._create_wiki_merge_request
            handlers["decide_wiki_review"] = self._decide_wiki_review
        if self._formalization_service is not None:
            handlers["formalize_wiki"] = self._formalize_wiki
            handlers["reconcile_wiki_formalization"] = self._reconcile_wiki_formalization
        if self._prereview_log is not None:
            handlers["append_prereview_log"] = self._append_prereview_log
        if self._merged_candidate_service is not None:
            handlers["create_merged_candidate"] = self._create_merged_candidate
        return handlers

    def _create_merged_candidate(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        """Create one merged Wiki candidate branch from source candidates.

        Only a new branch is created; existing candidates are never edited.
        The author field records every source author and source authors get
        no operation rights; merged candidates may not be merged again.
        """
        if self._merged_candidate_service is None:
            raise RuntimeError("merged_candidate_service is not configured")
        document_change = arguments.get("document_change")
        if not isinstance(document_change, dict):
            raise ValueError("document_change is required")
        source_proposal_ids = arguments.get("source_proposal_ids")
        if not isinstance(source_proposal_ids, list) or not source_proposal_ids:
            raise ValueError("source_proposal_ids is required and must be a non-empty array")
        result = self._merged_candidate_service.create_merged(
            wiki_domain_id=_required(arguments, "wiki_domain_id"),
            source_proposal_ids=[str(item) for item in source_proposal_ids],
            base_formal_revision_id=_required(arguments, "base_formal_revision_id"),
            document_change=document_change,
            idempotency_key=_required(arguments, "idempotency_key"),
        )
        return _candidate_result(result)

    def _append_prereview_log(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        """Append one Wiki prereview report, or one invalidation decision.

        ``reason`` present means a decision row (head_moved/base_moved);
        otherwise a report row under the candidate-head-rules unique key.
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

    def _get_formal_wiki(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        domain_id = _required(arguments, "wiki_domain_id")
        result = self._formal_query.get_current(domain_id)
        return _formal_wiki_result(result)

    def _list_wiki_candidates(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        domain_id = _required(arguments, "wiki_domain_id")
        if self._sqlite is None:
            return {"wiki_domain_id": domain_id, "candidates": []}
        submissions = self._sqlite.list_candidate_submissions(domain_id)
        return {
            "wiki_domain_id": domain_id,
            "candidates": [
                {
                    "submission_id": item.submission_id,
                    "wiki_domain_id": item.wiki_domain_id,
                    "submitter_id": item.submitter_id,
                    "base_formal_revision_id": item.base_formal_revision_id,
                    "proposal_id": item.proposal_id,
                    "submitted_at": item.submitted_at,
                    "status": item.status,
                }
                for item in submissions
            ],
        }

    def _submit_wiki_candidate(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        document_change = arguments.get("document_change")
        idempotency_key = _required(arguments, "idempotency_key")
        if not isinstance(document_change, dict):
            raise ValueError("document_change is required")
        result = self._candidate_service.submit(document_change, idempotency_key)
        if result.status in {"submitted", "confirmed", "ok"}:
            domain_id = str(document_change.get("wiki_domain_id") or arguments.get("wiki_domain_id") or "")
            self._publish_safely(
                candidate_event(
                    wiki_domain_id=domain_id,
                    submission_id=result.submission_id,
                    proposal_id=result.proposal_id,
                    candidate_head=result.commit_hash,
                )
            )
        return _candidate_result(result)

    def _list_reviewable_wiki_candidates(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        domain_id = _required(arguments, "wiki_domain_id")
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
        return {"wiki_domain_id": domain_id, "candidates": candidates}

    def _preview_wiki_review(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        result = self._review_service.preview(_required(arguments, "proposal_id"))
        return {
            "status": result.status,
            "reason_code": result.reason_code,
            "preview_id": result.preview_id,
            "proposal_id": result.proposal_id,
            "base_formal_revision_id": result.base_formal_revision_id,
            "candidate_head": result.candidate_head,
            "evidence": list(result.evidence),
        }

    def _create_wiki_merge_request(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        result = self._review_service.create_merge_request(
            _required(arguments, "proposal_id"),
            _required(arguments, "merge_request_id"),
            actor_id,
        )
        return {
            "status": result.status,
            "reason_code": result.reason_code,
            "preview_id": result.preview_id,
            "candidate_head": result.candidate_head,
        }

    def _decide_wiki_review(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        result = self._review_service.decide(
            _required(arguments, "merge_request_id"),
            actor_id=actor_id,
            decision=_required(arguments, "decision"),
            reason=_required(arguments, "reason"),
            selected_solution_id=_required(arguments, "selected_solution_id"),
            expected_owner_event_id=arguments.get("expected_owner_event_id") or None,
        )
        return {
            "status": result.status,
            "reason_code": result.reason_code,
            "audit_event_id": result.audit_event_id,
        }

    def _formalize_wiki(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        result = self._formalization_service.formalize(
            _required(arguments, "merge_request_id"),
            _required(arguments, "operation_id"),
        )
        if result.status == "succeeded" and getattr(result, "formal_wiki_revision_id", None):
            self._publish_safely(
                formal_revision_event(
                    wiki_domain_id=_text(arguments.get("wiki_domain_id")) or "",
                    formal_wiki_revision_id=result.formal_wiki_revision_id,
                    merge_request_id=arguments.get("merge_request_id"),
                )
            )
        return _wiki_formalization_outcome(result)

    def _reconcile_wiki_formalization(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        result = self._formalization_service.reconcile(_required(arguments, "operation_id"))
        return _wiki_formalization_outcome(result)

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


_WRITE_TOOLS = frozenset({
    "submit_wiki_candidate",
    "create_wiki_merge_request",
    "decide_wiki_review",
    "formalize_wiki",
    "reconcile_wiki_formalization",
    "append_prereview_log",
    "create_merged_candidate",
})

_TOOL_CAPABILITIES = {
    "get_formal_wiki": _READ_CAPABILITIES,
    "list_wiki_candidates": _READ_CAPABILITIES,
    "list_reviewable_wiki_candidates": _READ_CAPABILITIES,
    "submit_wiki_candidate": _CANDIDATE_SUBMIT_CAPABILITIES,
    "preview_wiki_review": _CANDIDATE_REVIEW_CAPABILITIES,
    "create_wiki_merge_request": _CANDIDATE_REVIEW_CAPABILITIES,
    "decide_wiki_review": _FORMALIZE_CAPABILITIES,
    "formalize_wiki": _FORMALIZE_CAPABILITIES,
    "reconcile_wiki_formalization": _FORMALIZE_CAPABILITIES,
    "append_prereview_log": _PREREVIEW_LOG_CAPABILITIES,
    "create_merged_candidate": _MERGED_CANDIDATE_CAPABILITIES,
}

TOOL_DEFINITIONS = [
    {
        "name": "get_formal_wiki",
        "description": "Read the current formal Wiki revision for a domain. Requires the read or centre capability.",
        "inputSchema": {
            "type": "object",
            "required": ["wiki_domain_id"],
            "properties": {"wiki_domain_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "list_wiki_candidates",
        "description": "Read candidate submissions for a Wiki domain. Requires the read or centre capability.",
        "inputSchema": {
            "type": "object",
            "required": ["wiki_domain_id"],
            "properties": {"wiki_domain_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "list_reviewable_wiki_candidates",
        "description": "Read the same-time reviewable Wiki candidate set (not merged, rejected or abandoned) with exact candidate head, base formal revision and immutable content snapshot. Requires the read or centre capability.",
        "inputSchema": {
            "type": "object",
            "required": ["wiki_domain_id"],
            "properties": {"wiki_domain_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "submit_wiki_candidate",
        "description": "Submit a Wiki document change with its full reference set against the exact formal base. Requires the candidate_submit capability.",
        "inputSchema": {
            "type": "object",
            "required": ["document_change", "idempotency_key"],
            "properties": {
                "document_change": {"type": "object"},
                "idempotency_key": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "preview_wiki_review",
        "description": "Build the review preview for a Wiki proposal. Requires the candidate_review capability.",
        "inputSchema": {
            "type": "object",
            "required": ["proposal_id"],
            "properties": {"proposal_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "create_wiki_merge_request",
        "description": "Lock a ready Wiki preview into a merge-request buffer for owner review. Requires the candidate_review capability.",
        "inputSchema": {
            "type": "object",
            "required": ["proposal_id", "merge_request_id"],
            "properties": {
                "proposal_id": {"type": "string"},
                "merge_request_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "decide_wiki_review",
        "description": "Record the Project Owner decision for a Wiki merge request. Requires the formalize capability.",
        "inputSchema": {
            "type": "object",
            "required": ["merge_request_id", "decision", "reason", "selected_solution_id"],
            "properties": {
                "merge_request_id": {"type": "string"},
                "decision": {"type": "string", "enum": ["approved", "rejected"]},
                "reason": {"type": "string"},
                "selected_solution_id": {"type": "string"},
                "expected_owner_event_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "formalize_wiki",
        "description": "Promote an Owner-approved Wiki candidate through atomic SQLite activation. Requires the formalize capability.",
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
        "name": "reconcile_wiki_formalization",
        "description": "Resume the same Wiki formalization operation identity. Requires the formalize capability.",
        "inputSchema": {
            "type": "object",
            "required": ["operation_id"],
            "properties": {"operation_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "append_prereview_log",
        "description": "Append one Wiki prereview report, or one invalidation decision, to the Wiki governance log. Append-only: reports and decisions are never edited. Passing ``reason`` (head_moved/base_moved) appends an invalidation decision; otherwise a report row is appended under the (candidate_id, candidate_head, rule_set_version, base_formal_revision_id) unique key. Requires the prereview_log capability.",
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
        "description": "Create one merged Wiki candidate branch from source candidates on the same formal base. Only creates a new branch; existing candidates are never edited. The author field records every source author; source authors get no operation rights; a merged candidate may not be merged again. Requires the merged_candidate capability.",
        "inputSchema": {
            "type": "object",
            "required": ["wiki_domain_id", "source_proposal_ids", "base_formal_revision_id", "document_change", "idempotency_key"],
            "properties": {
                "wiki_domain_id": {"type": "string"},
                "source_proposal_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "base_formal_revision_id": {"type": "string"},
                "document_change": {
                    "type": "object",
                    "properties": {
                        "submission_id": {"type": "string"},
                        "proposal_id": {"type": "string"},
                        "document": {"type": "object"},
                        "references": {"type": "array"},
                    },
                },
                "idempotency_key": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
]


def _formal_wiki_result(result: WikiFormalQueryResult) -> dict[str, Any]:
    if result.status != "available":
        return {"status": result.status, "reason_code": result.reason_code}
    return {
        "status": result.status,
        "reason_code": result.reason_code,
        "wiki_domain_id": result.wiki_domain_id,
        "formal_wiki_revision_id": result.formal_wiki_revision_id,
        "terminus_store_id": result.terminus_store_id,
        "formal_branch_id": result.formal_branch_id,
        "formal_commit_hash": result.formal_commit_hash,
        "content_digest": result.content_digest,
        "title": result.title,
        "description": result.description,
        "body_markdown": result.body_markdown,
        "references": [_formal_reference(reference) for reference in result.references],
    }


def _formal_reference(reference) -> dict[str, Any]:
    return {
        "reference_id": reference.reference_id,
        "target_resource_version_id": reference.target_resource_version_id,
        "target_wiki_revision_id": reference.target_wiki_revision_id,
        "reference_role": reference.reference_role,
        "body_locator": reference.body_locator,
        "qualification_status": getattr(reference.qualification, "status", None),
    }


def _candidate_result(result) -> dict[str, Any]:
    payload = asdict(result)
    return {key: value for key, value in payload.items() if value is not None}


def _wiki_formalization_outcome(result) -> dict[str, Any]:
    return {
        "status": result.status,
        "reason_code": result.reason_code,
        "formal_wiki_revision_id": result.formal_wiki_revision_id,
        "operation_id": result.operation_id,
        "commit_hash": result.commit_hash,
    }


def _target_type(tool: str) -> str:
    return {
        "get_formal_wiki": "WikiDomain",
        "list_wiki_candidates": "WikiDomain",
        "list_reviewable_wiki_candidates": "WikiDomain",
        "submit_wiki_candidate": "WikiSubmission",
        "preview_wiki_review": "WikiProposal",
        "create_wiki_merge_request": "WikiMergeRequest",
        "decide_wiki_review": "WikiMergeRequest",
        "formalize_wiki": "WikiMergeRequest",
        "reconcile_wiki_formalization": "WikiFormalizationOperation",
        "append_prereview_log": "WikiPrereviewReport",
        "create_merged_candidate": "WikiCandidate",
    }.get(tool)


def _target_id(arguments: dict[str, Any], tool: str) -> str | None:
    if tool in {"get_formal_wiki", "list_wiki_candidates", "list_reviewable_wiki_candidates"}:
        return _text(arguments.get("wiki_domain_id"))
    if tool == "submit_wiki_candidate":
        return _text(arguments.get("idempotency_key"))
    if tool == "preview_wiki_review":
        return _text(arguments.get("proposal_id"))
    if tool in {"create_wiki_merge_request", "decide_wiki_review", "formalize_wiki"}:
        return _text(arguments.get("merge_request_id"))
    if tool == "reconcile_wiki_formalization":
        return _text(arguments.get("operation_id"))
    if tool == "append_prereview_log":
        return _text(arguments.get("candidate_id"))
    if tool == "create_merged_candidate":
        return _text(arguments.get("idempotency_key"))
    return None


def open_audit_database(path: str) -> sqlite3.Connection:
    connection = open_connection(path)
    init_audit_table(connection)
    return connection
