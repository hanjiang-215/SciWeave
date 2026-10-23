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

_READ_CAPABILITIES = frozenset({"read", "centre"})
_CANDIDATE_SUBMIT_CAPABILITIES = frozenset({"candidate_submit", "centre"})


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
            "get_formal_wiki": self._get_formal_wiki,
            "submit_wiki_candidate": self._submit_wiki_candidate,
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

    def _submit_wiki_candidate(self, arguments: dict[str, Any], actor_id: str) -> dict[str, Any]:
        document_change = arguments.get("document_change")
        idempotency_key = _required(arguments, "idempotency_key")
        if not isinstance(document_change, dict):
            raise ValueError("document_change is required")
        result = self._candidate_service.submit(document_change, idempotency_key)
        return _candidate_result(result)


_WRITE_TOOLS = frozenset({"submit_wiki_candidate"})

_TOOL_CAPABILITIES = {
    "get_formal_wiki": _READ_CAPABILITIES,
    "submit_wiki_candidate": _CANDIDATE_SUBMIT_CAPABILITIES,
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
        "name": "submit_wiki_candidate",
        "description": "Submit a Wiki document change with its full reference set against the exact formal base. Requires candidate_submit or centre capability.",
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


def _target_type(tool: str) -> str:
    return {
        "get_formal_wiki": "WikiDomain",
        "submit_wiki_candidate": "WikiSubmission",
    }.get(tool)


def _target_id(arguments: dict[str, Any], tool: str) -> str | None:
    if tool == "get_formal_wiki":
        return _text(arguments.get("wiki_domain_id"))
    if tool == "submit_wiki_candidate":
        return _text(arguments.get("idempotency_key"))
    return None


def open_audit_database(path: str) -> sqlite3.Connection:
    connection = open_connection(path)
    init_audit_table(connection)
    return connection
