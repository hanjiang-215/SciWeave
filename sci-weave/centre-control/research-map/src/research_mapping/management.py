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

_READ_CAPABILITIES = frozenset({"read", "centre"})
_CANDIDATE_SUBMIT_CAPABILITIES = frozenset({"candidate_submit", "centre"})


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
    ) -> None:
        self._formal_query = formal_query
        self._candidate_service = candidate_service
        self._capabilities = caller_capabilities
        self._audit = audit_connection
        self._service = service_name

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
        return {
            "get_formal_mapping": self._get_formal_mapping,
            "list_candidates": self._list_candidates,
            "submit_candidate": self._submit_candidate,
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

    def _list_candidates(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        submission = _required(arguments, "submission_id")
        return {"submission_id": submission, "candidate": None}

    def _submit_candidate(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        change_set = arguments.get("change_set")
        idempotency_key = _required(arguments, "idempotency_key")
        if not isinstance(change_set, dict):
            raise ValueError("change_set is required")
        result = self._candidate_service.submit(change_set, idempotency_key)
        return _candidate_result(result)


_WRITE_TOOLS = frozenset({"submit_candidate"})

_TOOL_CAPABILITIES = {
    "get_formal_mapping": _READ_CAPABILITIES,
    "list_candidates": _READ_CAPABILITIES,
    "submit_candidate": _CANDIDATE_SUBMIT_CAPABILITIES,
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
        "name": "submit_candidate",
        "description": "Submit a Mapping candidate change set against the exact formal base. Requires candidate_submit or centre capability.",
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
        "documents": list(result.documents),
    }


def _candidate_result(result: CandidateSubmissionResult) -> dict[str, Any]:
    payload = asdict(result)
    return {key: value for key, value in payload.items() if value is not None}


def _classify(error: Exception) -> str:
    if isinstance(error, (ValueError, TypeError)):
        return "invalid_arguments"
    if isinstance(error, sqlite3.Error):
        return "store_error"
    return "internal"


def _target_type(tool: str) -> str:
    return {
        "get_formal_mapping": "MappingDomain",
        "list_candidates": "MappingSubmission",
        "submit_candidate": "MappingSubmission",
    }.get(tool)


def _target_id(arguments: dict[str, Any], tool: str) -> str | None:
    if tool == "get_formal_mapping":
        return _text(arguments.get("mapping_domain_id"))
    if tool == "list_candidates":
        return _text(arguments.get("submission_id"))
    if tool == "submit_candidate":
        return _text(arguments.get("idempotency_key"))
    return None


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def open_audit_database(path: str) -> sqlite3.Connection:
    connection = open_connection(path)
    init_audit_table(connection)
    return connection
