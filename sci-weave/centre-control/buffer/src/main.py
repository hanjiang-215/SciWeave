from __future__ import annotations

import json
import os
import sys
import uuid
from typing import Any

from . import BufferError, call_tool
from .config import BufferConfig
from .mcp_server import run
from .service import DraftBufferService
from .store import TerminusDBDraftStore


def build_service(config: BufferConfig | None = None) -> DraftBufferService:
    config = config or BufferConfig.from_environment()
    store = TerminusDBDraftStore(
        base_url=config.terminusdb_url,
        database=config.terminusdb_database,
        username=config.terminusdb_username,
        password=config.terminusdb_password,
        token=config.terminusdb_token,
        timeout=config.request_timeout_seconds,
    )
    return DraftBufferService(store, config.reviewers)


def dispatch(service: DraftBufferService, request: dict[str, Any]) -> dict[str, Any]:
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "protocolVersion": request.get("params", {}).get("protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "sciweave-draft-buffer", "version": "0.1.0"},
        }}
    if method == "notifications/initialized":
        return {}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": _tool_definitions()}}
    if method == "tools/call":
        params = request.get("params") or {}
        try:
            result = call_tool(service, params.get("name", ""), params.get("arguments") or {})
            return {"jsonrpc": "2.0", "id": request_id, "result": {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                "structuredContent": result,
                "isError": False,
            }}
        except BufferError as error:
            return {"jsonrpc": "2.0", "id": request_id, "result": {
                "content": [{"type": "text", "text": json.dumps({"code": error.code, "message": str(error)}, ensure_ascii=False)}],
                "isError": True,
            }}
        except (TypeError, ValueError) as error:
            return {"jsonrpc": "2.0", "id": request_id, "result": {
                "content": [{"type": "text", "text": json.dumps({"code": "invalid_arguments", "message": str(error)}, ensure_ascii=False)}],
                "isError": True,
            }}
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "method_not_found"}}


def _tool_definitions() -> list[dict[str, Any]]:
    common = {"type": "object", "additionalProperties": False}
    schemas = {
        "create_draft": {"type": "object", "required": ["namespace", "kind", "title", "payload", "submitted_by", "idempotency_key"], "properties": {"namespace": {"type": "string", "enum": ["mapping", "wiki"]}, "kind": {"type": "string"}, "title": {"type": "string"}, "payload": {}, "submitted_by": {"type": "string"}, "base_formal_revision_id": {"type": ["string", "null"]}, "source_task_node_id": {"type": ["string", "null"]}, "source_execution_record_id": {"type": ["string", "null"]}, "idempotency_key": {"type": "string"}}},
        "update_draft": {"type": "object", "required": ["draft_id", "actor_id", "idempotency_key"], "properties": {"draft_id": {"type": "string"}, "actor_id": {"type": "string"}, "idempotency_key": {"type": "string"}, "title": {"type": ["string", "null"]}, "payload": {}}},
        "submit_draft": {"type": "object", "required": ["draft_id", "actor_id", "idempotency_key"], "properties": {"draft_id": {"type": "string"}, "actor_id": {"type": "string"}, "idempotency_key": {"type": "string"}}},
        "list_drafts": {"type": "object", "properties": {"namespace": {"type": ["string", "null"]}, "status": {"type": ["string", "null"]}, "submitted_by": {"type": ["string", "null"]}, "actor_id": {"type": "string"}}},
        "read_draft": {"type": "object", "required": ["draft_id", "actor_id"], "properties": {"draft_id": {"type": "string"}, "actor_id": {"type": "string"}, "submitted_commit": {"type": ["string", "null"]}}},
        "review_draft": {"type": "object", "required": ["draft_id", "actor_id", "decision", "reason", "idempotency_key"], "properties": {"draft_id": {"type": "string"}, "actor_id": {"type": "string"}, "decision": {"type": "string", "enum": ["accept", "reject"]}, "reason": {"type": "string"}, "idempotency_key": {"type": "string"}}},
        "mark_promoted": {"type": "object", "required": ["draft_id", "actor_id", "candidate_id", "candidate_commit", "idempotency_key"], "properties": {"draft_id": {"type": "string"}, "actor_id": {"type": "string"}, "candidate_id": {"type": "string"}, "candidate_commit": {"type": "string"}, "idempotency_key": {"type": "string"}}},
    }
    descriptions = {
        "create_draft": "Create a Mapping or Wiki draft under a stable idempotency key.",
        "update_draft": "Update a draft owned by the authenticated submitter while it is editable.",
        "submit_draft": "Freeze the exact TerminusDB commit for human review.",
        "list_drafts": "List drafts visible in the caller's authorized namespace.",
        "read_draft": "Read draft metadata and current or submitted-commit content.",
        "review_draft": "Accept or reject a submitted draft as its configured namespace reviewer.",
        "mark_promoted": "Record the exact candidate ID and commit created by a domain MCP caller.",
    }
    return [{"name": name, "description": descriptions[name], "inputSchema": {**common, **schema}} for name, schema in schemas.items()]


def main() -> int:
    if os.environ.get("SCIWEAVE_BUFFER_DEMO") == "1":
        print(json.dumps({"status": "ready", "protocol": "stdio JSON-RPC", "tools": 7}))
        return 0
    try:
        service = build_service()
    except BufferError as error:
        print(json.dumps({"status": "error", "code": error.code, "message": str(error)}), file=sys.stderr)
        return 2
    run(lambda request: dispatch(service, request))
    return 0
