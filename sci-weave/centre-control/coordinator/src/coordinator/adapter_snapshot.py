"""FormalSnapshotPort implementation over the research-map management MCP.

Reads a version-consistent formal mapping snapshot through the domain
management MCP ``get_formal_mapping_at_revision`` tool (Streamable HTTP,
``POST /mcp``), per the ai4-2982 contract. The coordinator never opens the
Mapping SQLite/TerminusDB; all reads go through the MCP surface with the same
consistency gates the domain services already enforce.

The adapter translates the MCP envelope into the coordinator's
``FormalSnapshot`` document model. TaskNode documents carry
``logical_id``/``version_id``/``task_owner_id``/``executor_refs``;
DependencyEdge documents carry ``source_node_version_ref`` and
``target_node_version_ref`` pointing at ``{logical_id, version_id, mapping_domain_id}``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from typing import Any

from .ports import (
    FormalSnapshot,
    FormalSnapshotPort,
    DependencyEdgeDoc,
    NoSuchRevisionError,
    SnapshotInconsistentError,
    SnapshotUnavailableError,
    TaskNodeDoc,
)

_MCP_PROTOCOL_VERSION = "2025-03-26"


class ResearchMapMcpSnapshotPort(FormalSnapshotPort):
    """Read one formal mapping revision through the research-map management MCP."""

    def __init__(
        self,
        *,
        endpoint: str,
        token: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not endpoint or not token:
            raise ValueError("research-map MCP endpoint and token are required")
        self.endpoint = endpoint
        self.token = token
        self.timeout_seconds = timeout_seconds

    def get_formal_mapping_at_revision(
        self, mapping_domain_id: str, formal_revision_id: str
    ) -> FormalSnapshot:
        envelope = self._call(
            "get_formal_mapping_at_revision",
            {
                "mapping_domain_id": mapping_domain_id,
                "formal_revision_id": formal_revision_id,
            },
        )
        if envelope is None:
            raise SnapshotUnavailableError("mcp_no_response")
        if envelope.get("error"):
            reason = (envelope.get("error") or {}).get("message") or "rpc_error"
            raise SnapshotUnavailableError(str(reason))
        text = self._first_text(envelope)
        try:
            result = json.loads(text) if text else {}
        except json.JSONDecodeError as exc:
            raise SnapshotUnavailableError("invalid_mcp_response") from exc
        status = result.get("status")
        reason_code = result.get("reason_code")
        if status == "no_such_revision" or "revision_not_found" in str(reason_code):
            raise NoSuchRevisionError(str(reason_code or "no_such_revision"))
        if status in {"inconsistent", "unavailable"} or status != "available":
            if status == "inconsistent":
                raise SnapshotInconsistentError(str(reason_code or "inconsistent"))
            raise SnapshotUnavailableError(str(reason_code or "unavailable"))
        documents = result.get("documents")
        if not isinstance(documents, list):
            raise SnapshotUnavailableError("documents_missing")
        return _build_snapshot(
            mapping_domain_id=mapping_domain_id,
            formal_revision_id=formal_revision_id,
            documents=documents,
            latest_published_by=result.get("published_by"),
        )

    # ------------------------------------------------------------------ http

    def _call(self, tool: str, arguments: dict[str, Any]) -> dict | None:
        import urllib.error as url_error
        import urllib.request as url_request

        request_id = str(uuid.uuid4())
        initialize = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": _MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "sciweave-handoff-coordinator", "version": "0.1.0"},
                },
            }
        ).encode()
        http = url_request.Request(
            self.endpoint,
            data=initialize,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            method="POST",
        )
        try:
            url_request.urlopen(http, timeout=self.timeout_seconds).read()
        except (url_error.URLError, OSError):
            raise SnapshotUnavailableError("mcp_unavailable")

        call_body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments},
            }
        ).encode()
        http = url_request.Request(
            self.endpoint,
            data=call_body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            method="POST",
        )
        try:
            with url_request.urlopen(http, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (url_error.URLError, OSError):
            raise SnapshotUnavailableError("mcp_unavailable")
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise SnapshotUnavailableError("invalid_mcp_response")
        if not isinstance(payload, dict):
            raise SnapshotUnavailableError("invalid_mcp_response")
        return payload

    @staticmethod
    def _first_text(payload: dict) -> str:
        content = (payload.get("result") or {}).get("content") or []
        return next(
            (block.get("text") for block in content if isinstance(block.get("text"), str)),
            "",
        )


def _build_snapshot(
    *, mapping_domain_id: str, formal_revision_id: str, documents: list[dict[str, Any]],
    latest_published_by: str | None = None,
) -> FormalSnapshot:
    nodes: list[TaskNodeDoc] = []
    edges: list[DependencyEdgeDoc] = []
    for document in documents:
        dtype = str(document.get("@type") or "").rstrip(">").rsplit("/", 1)[-1]
        if dtype == "TaskNode":
            nodes.append(
                TaskNodeDoc(
                    task_node_id=_text(document.get("logical_id")),
                    version_id=_text(document.get("version_id")),
                    executor_refs=tuple(
                        str(item) for item in (document.get("executor_refs") or [])
                        if str(item).strip()
                    ),
                    task_owner_id=_text(document.get("task_owner_id")),
                )
            )
        elif dtype == "DependencyEdge":
            source = _parse_ref(document.get("source_node_version_ref"))
            target = _parse_ref(document.get("target_node_version_ref"))
            # ai4-quvy: the four judgement fields are projected whole now --
            # dependency_kind, activation_condition, required_outputs and
            # blocks_until -- so the coordinator can follow ai4-te1v's
            # dependency-kind rules instead of treating every edge the same.
            edges.append(
                DependencyEdgeDoc(
                    logical_id=_text(document.get("logical_id")),
                    version_id=_text(document.get("version_id")),
                    source_node_id=_text(source.get("logical_id")),
                    source_version_id=_text(source.get("version_id")),
                    target_node_id=_text(target.get("logical_id")),
                    target_version_id=_text(target.get("version_id")),
                    dependency_kind=_text(document.get("dependency_kind")) or "information",
                    activation_condition=(
                        _text(document.get("activation_condition")) or None
                    ),
                    required_outputs=tuple(
                        str(item) for item in (document.get("required_outputs") or [])
                        if str(item).strip()
                    ),
                    blocks_until=_text(document.get("blocks_until")) or None,
                    alternative_group_id=(
                        _text(document.get("alternative_group_id")) or None
                    ),
                )
            )
    return FormalSnapshot(
        mapping_domain_id=mapping_domain_id,
        formal_revision_id=formal_revision_id,
        nodes=tuple(node for node in nodes if node.task_node_id),
        edges=tuple(edge for edge in edges if edge.logical_id),
        latest_published_by=_text(latest_published_by) or None,
    )


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _parse_ref(value: Any) -> dict[str, Any]:
    """Normalize a node-version ref from a DependencyEdge document.

    TerminusDB stores complex fields as JSON text (the demo pipeline seeds
    ``source_node_version_ref`` with ``json.dumps``), so the value may arrive
    as a JSON string instead of an inline dict. Accept both shapes.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}