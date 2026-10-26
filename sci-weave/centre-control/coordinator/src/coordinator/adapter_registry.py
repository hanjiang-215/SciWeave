"""AgentAvailabilityPort implementation over the central Registry MCP.

Reads workflow-agent registration and runtime-instance facts through the
Registry ``get_agent_registration`` tool (Streamable HTTP MCP). The Registry
never authorizes: an agent is "available" only when its registration is
``active`` and at least one instance reports ``online``. The coordinator uses
this strictly for the routing decision (publish task_handoff_ready vs keep
waiting and notify a human), never as an execution-rights check.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from typing import Any

_MCP_PROTOCOL_VERSION = "2025-03-26"

_ACTIVE = "active"
_ONLINE = "online"


class RegistryMcpAvailabilityPort:
    """Query one executor agent's availability through the Registry management MCP."""

    def __init__(
        self,
        *,
        endpoint: str,
        token: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not endpoint or not token:
            raise ValueError("registry MCP endpoint and token are required")
        self.endpoint = endpoint
        self.token = token
        self.timeout_seconds = timeout_seconds

    def is_available(self, agent_id: str) -> bool:
        """True when the agent is registered active and has an online instance.

        Registry facts are authoritative for availability/liveness only;
        execution eligibility still comes from the formal mapping's
        ``executor_refs``. On any registry failure we answer False so the
        coordinator keeps the waiting fact and notifies a human instead of
        dispatching blindly.
        """
        if not agent_id or not agent_id.strip():
            return False
        try:
            registration = self._call("get_agent_registration", {"agent_id": agent_id})
        except (urllib.error.URLError, OSError, ValueError):
            return False
        if registration is None:
            return False
        status = registration.get("status")
        if status != _ACTIVE:
            return False
        instances = registration.get("agent_instances") or []
        if not isinstance(instances, list):
            return False
        return any(
            isinstance(item, dict) and item.get("runtime_status") == _ONLINE for item in instances
        )

    def _call(self, tool: str, arguments: dict[str, Any]) -> dict | None:
        import urllib.error as url_error
        import urllib.request as url_request

        initialize = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
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
            raise

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
            raise
        if not isinstance(payload, dict) or payload.get("error"):
            return None
        content = (payload.get("result") or {}).get("content") or []
        text = next(
            (block.get("text") for block in content if isinstance(block.get("text"), str)),
            "{}",
        )
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            return None
        return result if isinstance(result, dict) else None