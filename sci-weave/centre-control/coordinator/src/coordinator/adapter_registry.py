"""AgentAvailabilityPort implementation over the central Registry MCP.

Reads workflow-agent registration and runtime-instance facts through the
Registry ``get_agent_registration`` tool (Streamable HTTP MCP). The Registry
never authorizes: an agent is "available" only when its registration is
``active`` and at least one instance reports ``online``. The coordinator uses
this strictly for the routing decision (publish task_handoff_ready vs keep
waiting and notify a human), never as an execution-rights check.

The four-way answer exists because the task owner is told what to do next
(ai4-xkbd): an agent the Registry has never heard of means the mapping names
a bad id, an agent that exists but cannot run means ops work, and a Registry
we could not reach means we know nothing and must not claim the agent is
gone.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from typing import Any

from .ports import AgentState

_MCP_PROTOCOL_VERSION = "2025-03-26"

_ACTIVE = "active"
_ONLINE = "online"
#: The Registry's code for "no such workflow_agent row". Only this one is a
#: statement about the agent; every other failure is a statement about us.
_AGENT_NOT_FOUND = "agent_not_found"


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

    def state_of(self, agent_id: str) -> AgentState:
        """What the Registry knows about this executor ref.

        Registry facts are authoritative for availability/liveness only;
        execution eligibility still comes from the formal mapping's
        ``executor_refs``. On any Registry failure we answer UNKNOWN rather
        than UNREGISTERED: an outage is not evidence about the agent.
        """
        if not agent_id or not agent_id.strip():
            # A blank ref lists nothing usable, which is a mapping defect, not
            # an agent that went away.
            return AgentState.UNREGISTERED
        try:
            registration, error = self._call("get_agent_registration", {"agent_id": agent_id})
        except (urllib.error.URLError, OSError, ValueError):
            return AgentState.UNKNOWN
        if error is not None:
            return AgentState.UNREGISTERED if error == _AGENT_NOT_FOUND else AgentState.UNKNOWN
        if not isinstance(registration, dict):
            return AgentState.UNKNOWN
        # The Registry answers with the registration row and its instances
        # nested; reading top-level "status"/"agent_instances" silently saw
        # nothing and reported every agent as unusable.
        agent = registration.get("agent")
        instances = registration.get("instances")
        if not isinstance(agent, dict) or not isinstance(instances, list):
            return AgentState.UNKNOWN
        if agent.get("status") != _ACTIVE:
            return AgentState.UNAVAILABLE
        if any(
            isinstance(item, dict) and item.get("runtime_status") == _ONLINE
            for item in instances
        ):
            return AgentState.AVAILABLE
        return AgentState.UNAVAILABLE

    def is_available(self, agent_id: str) -> bool:
        """True when the agent is registered active and has an online instance."""
        return self.state_of(agent_id) is AgentState.AVAILABLE

    def _call(self, tool: str, arguments: dict[str, Any]) -> tuple[dict | None, str | None]:
        """Return ``(result, error_code)``; transport failures raise instead.

        Keeping the code lets callers separate "the Registry answered: no such
        agent" from "we never got an answer", which is the difference between
        telling an owner their mapping is wrong and telling them nothing.
        """
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
        if not isinstance(payload, dict):
            return None, "malformed_response"
        error = payload.get("error")
        if error:
            # The Registry reports domain failures as JSON-RPC errors, so the
            # code is the only place "no such agent" can be told apart from
            # "you are not allowed" or "storage is down".
            code = error.get("code") if isinstance(error, dict) else None
            return None, str(code) if code else "error"
        content = (payload.get("result") or {}).get("content") or []
        text = next(
            (block.get("text") for block in content if isinstance(block.get("text"), str)),
            "{}",
        )
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            return None, "malformed_response"
        return (result, None) if isinstance(result, dict) else (None, "malformed_response")