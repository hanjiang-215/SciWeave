"""Domain management MCP client boundary for the Centre Agent ingest role.

The ingest consumer talks only to the two isolated domain management MCP
surfaces.  ``DomainMCPClient`` is the port; the Streamable HTTP implementation
and the recording fake used by tests sit next to it.  Nothing here knows about
Kafka or the governance envelope -- that belongs to the consumer service.
"""

from __future__ import annotations

import json
import typing
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Protocol


class DomainMCPError(RuntimeError):
    """Stable failure from the domain management MCP surface."""


@dataclass(frozen=True)
class ReviewableCandidate:
    """One candidate snapshot as returned by ``list_reviewable_candidates``."""

    candidate_id: str
    candidate_head: str
    base_formal_revision_id: str | None
    prereview_status: dict[str, Any]

    @classmethod
    def from_dict(cls, item: dict[str, Any]) -> "ReviewableCandidate":
        return cls(
            candidate_id=str(item.get("submission_id") or item.get("candidate_id") or ""),
            candidate_head=str(item.get("candidate_head") or ""),
            base_formal_revision_id=(
                str(item["base_formal_revision_id"]) if item.get("base_formal_revision_id") else None
            ),
            prereview_status=item.get("prereview_status") or {},
        )


class DomainMCPClient(Protocol):
    """Port: read reviewable candidates and append prereview decisions."""

    def list_reviewable_candidates(self, domain_id: str) -> list[ReviewableCandidate]: ...
    def append_base_moved(self, domain_id: str, candidate_id: str, candidate_head: str) -> None: ...


class BufferMGatewayMCPClient:
    """Streamable HTTP client for one domain management MCP endpoint.

    Endpoint, token and namespace come from the environment in the CLI
    assembly; the client itself never hard-codes addresses or credentials.
    Reuses the MCP ``initialize`` + ``tools/call`` handshake of the draft-box
    writer: a JSON-RPC initialize on first use, then tool calls.
    """

    def __init__(self, *, endpoint: str, token: str, timeout_seconds: float = 10.0) -> None:
        if not endpoint or not token:
            raise ValueError("domain MCP endpoint and token are required")
        self.endpoint = endpoint
        self.token = token
        self.timeout_seconds = timeout_seconds

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        http = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(http, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except (urllib.error.URLError, OSError) as exc:
            raise DomainMCPError(f"domain_mcp_unavailable: {exc}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DomainMCPError("domain_mcp_invalid_response") from exc
        if payload.get("error"):
            raise DomainMCPError("domain_mcp_tool_error")
        return payload

    def _tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        _ = self._post(
            {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "sciweave-centre-agent-ingest", "version": "0.1.0"},
                },
            }
        )
        payload = self._post(
            {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        result = payload.get("result") or {}
        content = result.get("content") or []
        text = next((block.get("text") for block in content if isinstance(block.get("text"), str)), None)
        if text is None:
            raise DomainMCPError("domain_mcp_invalid_response")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise DomainMCPError("domain_mcp_invalid_response") from exc

    def list_reviewable_candidates(self, domain_id: str) -> list[ReviewableCandidate]:
        payload = self._tool(
            "list_reviewable_candidates",
            {"mapping_domain_id": domain_id},
        )
        items = payload.get("candidates") or []
        if not isinstance(items, list):
            raise DomainMCPError("domain_mcp_invalid_response")
        return [ReviewableCandidate.from_dict(item) for item in items if isinstance(item, dict)]

    def append_base_moved(self, domain_id: str, candidate_id: str, candidate_head: str) -> None:
        self._tool(
            "append_prereview_log",
            {
                "mapping_domain_id": domain_id,
                "candidate_id": candidate_id,
                "candidate_head": candidate_head,
                "reason": "base_moved",
            },
        )


class RecordingDomainMCPClient:
    """In-memory fake used by tests: records calls, serves a candidate list."""

    def __init__(self, candidates: list[ReviewableCandidate] | None = None) -> None:
        self.candidates = list(candidates or [])
        self.base_moved: list[tuple[str, str, str]] = []

    def list_reviewable_candidates(self, domain_id: str) -> list[ReviewableCandidate]:
        return list(self.candidates)

    def append_base_moved(self, domain_id: str, candidate_id: str, candidate_head: str) -> None:
        self.base_moved.append((domain_id, candidate_id, candidate_head))


if typing.TYPE_CHECKING:
    _: type[DomainMCPClient] = BufferMGatewayMCPClient
    _: type[DomainMCPClient] = RecordingDomainMCPClient