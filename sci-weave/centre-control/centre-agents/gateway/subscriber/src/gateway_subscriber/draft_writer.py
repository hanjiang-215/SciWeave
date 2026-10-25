"""Execution 转换为中央草稿箱草稿的写入器。

该写入器以 Worker 内 agent 的身份调用中央草稿箱的 MCP ``create_draft``，
把一轮执行的结果写成草稿。Gateway 自身不持有草稿箱凭据；本模块的端点和
令牌来自环境变量，只提供给 Worker 运行路径使用。
"""

from __future__ import annotations

import json
import typing
import uuid
from typing import Any

from .worker_runner import DraftWriteError

_MCP_PROTOCOL_VERSION = "2025-03-26"


class BufferMCPDraftWriter:
    """POST ``create_draft`` to the central draft buffer MCP endpoint.

    端点、令牌、命名空间与提交者全部从环境变量读取；配置缺失时构造失败，
    调用即抛 ``DraftWriteError``，绝不携带凭据进执行记录。
    """

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

    def write(self, *, execution: dict[str, Any], result_summary: str) -> str:
        import urllib.error
        import urllib.request

        request_id = str(uuid.uuid4())
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": _MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "sciweave-gateway-subscriber", "version": "0.1.0"},
                },
            }
        ).encode()
        http = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            method="POST",
        )
        try:
            urllib.request.urlopen(http, timeout=self.timeout_seconds).read()
        except (urllib.error.URLError, OSError):
            raise DraftWriteError("draft_unavailable")

        arguments = {
            "namespace": self.namespace,
            "kind": "mapping_change" if self.namespace == "mapping" else "wiki_document",
            "title": f"execution-{execution['execution_id']}",
            "payload": {"result_summary": result_summary, **{k: v for k, v in execution.items() if k in {"trigger", "trigger_ref", "business_key"}}},
            "submitted_by": self.submitter_id,
            "idempotency_key": f"draft:{execution['execution_id']}",
            "base_formal_revision_id": self.base_formal_revision_id,
            "source_task_node_id": execution.get("task_node_id"),
            "source_execution_record_id": execution["execution_id"],
        }
        call_body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/call",
                "params": {"name": "create_draft", "arguments": arguments},
            }
        ).encode()
        http = urllib.request.Request(
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
            with urllib.request.urlopen(http, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError):
            raise DraftWriteError("draft_unavailable")
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise DraftWriteError("draft_invalid_response")
        content = (payload.get("result") or {}).get("content") or []
        text = next(
            (block.get("text") for block in content if isinstance(block.get("text"), str)),
            "{}",
        )
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            raise DraftWriteError("draft_invalid_response")
        if payload.get("error") or data.get("error") or data.get("status") in {"error", "invalid_something"}:
            raise DraftWriteError("draft_submission_failed")
        draft_id = data.get("draft_id")
        if not draft_id:
            raise DraftWriteError("draft_submission_failed")
        return draft_id