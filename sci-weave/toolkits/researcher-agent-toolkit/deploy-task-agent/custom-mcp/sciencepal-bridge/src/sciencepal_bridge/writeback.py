"""ExecutionReport write-back to the central draft buffer (ai4-roow).

The bridge never writes the formal Research Mapping.  It creates a Mapping
draft (namespace ``mapping``, kind ``mapping_change``) carrying the report and
the proposed change set; a TaskNode Owner reviews it, a human submits it, and
the Project Owner formalizes it.  Audit correlation ids (execution_id, run_id,
draft_id, candidate_id, formal_revision_id) are surfaced through the result so
the caller can thread them through the governance log.

Transport: the draft buffer MCP answers JSON-RPC over ``POST /mcp`` with a
bearer token (Streamable HTTP in JSON-response mode).  The caller identity is
injected by that transport, so ``actor_id`` is never a client argument.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from .report import proposed_change_set


class WriteBackError(RuntimeError):
    """A stable write-back failure; code is safe to show to an agent."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class DraftBufferWriteBack:
    """Write ExecutionReports into the central draft buffer via its MCP."""

    def __init__(self, url: str, token: str, timeout_seconds: float = 30.0) -> None:
        if not url:
            raise WriteBackError("draft_buffer_not_configured", "draft buffer MCP url is not configured")
        if not token:
            raise WriteBackError("draft_buffer_token_missing", "draft buffer MCP token is not configured")
        self.url = url
        self.token = token
        self.timeout_seconds = timeout_seconds
        self._next_id = 0

    def create_draft(self, *, report: dict[str, Any], submitted_by: str, idempotency_key: str) -> dict[str, Any]:
        """Create one mapping_change draft for a report (idempotent by key)."""
        arguments = {
            "namespace": "mapping",
            "kind": "mapping_change",
            "title": f"SciencePal execution report {report.get('execution_id')}",
            "payload": {
                "report": report,
                "proposed_change_set": proposed_change_set(report),
            },
            "submitted_by": submitted_by,
            "source_task_node_id": report.get("task_node_id"),
            "source_execution_record_id": report.get("execution_id"),
            "idempotency_key": idempotency_key,
        }
        outcome = self._call("create_draft", arguments)
        return self._with_correlation(outcome, report)

    def read_draft(self, draft_id: str) -> dict[str, Any]:
        """Read one draft back, so the caller can prove the payload round-trips.

        The draft buffer restricts ``read_draft`` to the namespace reviewer, so
        this is the TaskNode Owner's verification path rather than the harness's.
        The draft buffer answers ``{"draft": {...}}``.
        """
        return self._call("read_draft", {"draft_id": draft_id})

    # -- transport -----------------------------------------------------

    def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        body = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds) as http:
                response = http.post(self.url, json=body, headers=headers)
        except (httpx.HTTPError, OSError) as exc:
            raise WriteBackError("draft_buffer_unavailable", f"draft buffer unreachable: {exc}") from exc

        if response.status_code == 401:
            raise WriteBackError("draft_buffer_denied", "draft buffer rejected the bearer token")
        if response.status_code != 200:
            raise WriteBackError(
                "draft_buffer_unavailable",
                f"draft buffer returned HTTP {response.status_code}",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise WriteBackError("draft_buffer_invalid_response", "draft buffer returned non-JSON") from exc

        if isinstance(payload, list):
            payload = next((item for item in payload if isinstance(item, dict) and "result" in item), {})
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            error = payload.get("error") if isinstance(payload, dict) else None
            code = "draft_buffer_invalid_response"
            if isinstance(error, dict) and isinstance(error.get("code"), int):
                code = f"draft_buffer_rpc_{error['code']}"
            raise WriteBackError(code, f"draft buffer call {name} failed")

        structured = result.get("structuredContent")
        if isinstance(structured, dict) and structured:
            if result.get("isError"):
                raise WriteBackError(
                    str(structured.get("code") or "draft_buffer_rejected"),
                    str(structured.get("message") or "draft buffer rejected the draft"),
                )
            return structured
        if result.get("isError"):
            code, message = _error_from_text(_first_text(result))
            raise WriteBackError(code, message)
        raise WriteBackError("draft_buffer_invalid_response", "draft buffer returned no usable payload")

    @staticmethod
    def _with_correlation(outcome: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
        """Attach audit correlation ids (ai4-roow AC4).

        The ledger and governance log can then link execution_id, run_id and
        draft_id; candidate_id and formal_revision_id are added by the
        review/formalize stages the caller drives after the draft is created.
        """
        enriched = dict(outcome)
        enriched.setdefault("execution_id", report.get("execution_id"))
        enriched.setdefault("run_id", report.get("sciencepal", {}).get("run_id"))
        enriched.setdefault("task_node_id", report.get("task_node_id"))
        return enriched


def _first_text(result: dict[str, Any]) -> str | None:
    for item in result.get("content") or ():
        text = item.get("text") if isinstance(item, dict) else None
        if isinstance(text, str):
            return text
    return None


def _error_from_text(text: str | None) -> tuple[str, str]:
    """Recover the draft buffer's stable error code from an isError payload."""
    if not text:
        return "draft_buffer_rejected", "draft buffer rejected the draft"
    try:
        decoded = json.loads(text)
    except ValueError:
        return "draft_buffer_rejected", text
    if isinstance(decoded, dict):
        code = decoded.get("code")
        message = decoded.get("message")
        return (
            str(code) if isinstance(code, str) and code else "draft_buffer_rejected",
            str(message) if isinstance(message, str) and message else "draft buffer rejected the draft",
        )
    return "draft_buffer_rejected", text


__all__ = ["DraftBufferWriteBack", "WriteBackError"]
