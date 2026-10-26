"""Draft-box writer for the researcher-owned Work Agent.

Pushes one execution result into the central draft buffer MCP endpoint (the
"draft box") over Streamable HTTP.  Endpoint, token, namespace and submitter
come entirely from the environment; the researcher template never hard-codes
or logs credentials.  When configuration is missing the writer fails to
construct, so a misconfigured deployment fails fast instead of writing
half-shaped drafts.

``FakeDraftBox`` (``runtime.py``) remains the demo/test default; the service
templates swap in ``BufferMCPDraftWriter.from_env`` only when
``DRAFT_BUFFER_MCP_URL`` and ``DRAFT_BUFFER_MCP_TOKEN`` are present.
"""

from __future__ import annotations

import json
import os
import typing
import uuid
from typing import Any

_MCP_PROTOCOL_VERSION = "2025-03-26"


class DraftWriteError(RuntimeError):
    """Stable error raised when the central draft box rejects or drops the write."""


if typing.TYPE_CHECKING:
    from .runtime import FakeDraftBox


class BufferMCPDraftWriter:
    """POST ``create_draft`` to the central draft buffer MCP endpoint."""

    def __init__(
        self,
        *,
        endpoint: str,
        token: str,
        namespace: str,
        submitter_id: str,
        base_formal_revision_id: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not endpoint or not token:
            raise ValueError("draft buffer endpoint and token are required")
        self.endpoint = endpoint
        self.token = token
        self.namespace = namespace.strip()
        self.submitter_id = submitter_id.strip()
        self.base_formal_revision_id = base_formal_revision_id
        self.timeout_seconds = timeout_seconds
        if not self.namespace or not self.submitter_id:
            raise ValueError("draft namespace and submitter are required")

    @classmethod
    def from_env(cls, *, namespace: str, submitter_id: str) -> "BufferMCPDraftWriter":
        """Build from the researcher environment; raises ``ValueError`` when unset."""
        return cls(
            endpoint=os.environ.get("DRAFT_BUFFER_MCP_URL", "").strip(),
            token=os.environ.get("DRAFT_BUFFER_MCP_TOKEN", "").strip(),
            namespace=namespace,
            submitter_id=submitter_id,
        )

    def write(self, *, target_id: str, payload: str) -> str:
        import urllib.error
        import urllib.request

        def _post(body: dict[str, Any]) -> dict[str, Any]:
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
            except (urllib.error.URLError, OSError):
                raise DraftWriteError("draft_unavailable")
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise DraftWriteError("draft_invalid_response")
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                raise DraftWriteError("draft_invalid_response")

        _post(
            {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "initialize",
                "params": {
                    "protocolVersion": _MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "sciweave-task-agent-subscriber", "version": "0.1.0"},
                },
            }
        )

        payload_json = _post(
            {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/call",
                "params": {
                    "name": "create_draft",
                    "arguments": {
                        "namespace": self.namespace,
                        "kind": "mapping_change" if self.namespace == "mapping" else "wiki_document",
                        "title": f"execution-{target_id}",
                        "payload": {"result_summary": payload},
                        "submitted_by": self.submitter_id,
                        "idempotency_key": f"draft:{target_id}",
                        "base_formal_revision_id": self.base_formal_revision_id,
                        "source_target_node_id": target_id,
                    },
                },
            }
        )

        if payload_json.get("error"):
            raise DraftWriteError("draft_submission_failed")
        content = (payload_json.get("result") or {}).get("content") or []
        text = next(
            (block.get("text") for block in content if isinstance(block.get("text"), str)),
            "{}",
        )
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            raise DraftWriteError("draft_invalid_response")
        if data.get("error") or data.get("status") in {"error", "invalid_something"}:
            raise DraftWriteError("draft_submission_failed")
        draft_id = data.get("draft_id")
        if not draft_id:
            raise DraftWriteError("draft_submission_failed")
        return draft_id