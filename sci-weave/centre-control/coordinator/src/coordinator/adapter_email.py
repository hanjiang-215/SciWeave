"""NotificationPublisherPort implementation over the central email-service MCP.

Submits ``human_notification_intent`` / ``task_terminal_summary`` intents
through the email-service ``send_notification`` tool (Streamable HTTP MCP).
The email service owns delivery and dedupe; the coordinator only records the
intent. A transient failure raises so the coordinator keeps the dispatch in
``result_unknown`` and retries on startup.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from typing import Any

from .ports import NotificationIntent, NotificationPublisherPort

_MCP_PROTOCOL_VERSION = "2025-03-26"


class EmailMcpNotificationPublisher(NotificationPublisherPort):
    """POST ``send_notification`` intents to the email-service MCP endpoint."""

    def __init__(
        self,
        *,
        endpoint: str,
        token: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not endpoint or not token:
            raise ValueError("email-service MCP endpoint and token are required")
        self.endpoint = endpoint
        self.token = token
        self.timeout_seconds = timeout_seconds

    def publish(self, intent: NotificationIntent) -> None:
        recipients = [{"principal_id": recipient} for recipient in intent.recipients]
        notification_id = "notification-" + uuid.uuid4().hex
        dedupe_key = _dedupe_key(intent)
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/call",
                "params": {
                    "name": "send_notification",
                    "arguments": {
                        "notification_id": notification_id,
                        "dedupe_key": dedupe_key,
                        "notification_kind": intent.notification_kind,
                        "recipients": recipients,
                        "subject": intent.subject,
                        "body": intent.body,
                        "related": dict(intent.related),
                        "schema_version": "1",
                    },
                },
            }
        ).encode()
        self._initialize()
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
            with urllib.request.urlopen(http, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError) as exc:
            raise RuntimeError("notification_unavailable") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("notification_invalid_response") from exc
        if not isinstance(payload, dict) or payload.get("error"):
            raise RuntimeError("notification_submission_failed")

    def _initialize(self) -> None:
        import urllib.error as url_error
        import urllib.request as url_request

        body = json.dumps(
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
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            method="POST",
        )
        try:
            url_request.urlopen(http, timeout=self.timeout_seconds).read()
        except (url_error.URLError, OSError) as exc:
            raise RuntimeError("notification_unavailable") from exc


def _dedupe_key(intent: NotificationIntent) -> str:
    related = intent.related
    task_node_id = related.get("task_node_id")
    pending_handoff_id = related.get("pending_handoff_id")
    formal_revision_id = related.get("formal_revision_id")
    identity = task_node_id or pending_handoff_id or formal_revision_id or ""
    return f"{intent.notification_kind}:{identity}"