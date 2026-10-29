"""Publish ``task_completed`` governance events (B6).

The coordinator already consumes ``task_completed`` (``adapter_events`` →
``service.on_task_completed``) to write a completion fact and release the
downstream nodes, but nothing in the project ever published one, so a finished
node never released its successors. This module is that missing producer.

The envelope mirrors the shared ``message_envelope`` ``task_completed`` shape
(the same way the coordinator's ``task_handoff_ready`` producer builds a plain
dict), and additionally carries the ``node_version_ref`` / ``formal_revision_id``
aliases the coordinator's router reads. It is emitted as a plain JSON dict to
keep the subscriber free of a cross-workspace dependency. Publishing is
best-effort: a broker hiccup must not fail an execution that already completed,
so failures are logged, not raised.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Protocol

logger = logging.getLogger("gateway_subscriber")

_GOVERNANCE_TOPIC = "sciweave.governance-events"


class CompletionPublishError(Exception):
    """Raised when a ``task_completed`` event could not be confirmed by the broker.

    The outbox drain treats this as "still pending" and retries later, so the
    error must mean the event was NOT accepted -- not merely slow (ai4-odwi).
    """


class CompletionPublisher(Protocol):
    def publish(self, *, execution: dict[str, Any]) -> None:
        """Publish one ``task_completed`` for a terminal successful execution.

        Must raise :class:`CompletionPublishError` if the broker did not confirm
        the write, so the transactional outbox can retry it.
        """


def _split_business_key(business_key: str | None) -> tuple[str, str]:
    """Return ``(target_node_version_ref, trigger_revision_id)`` from a business key.

    ``handle_message`` builds it as ``task_node_id:target_node_version_ref:
    trigger_revision_id``; any part may be empty.
    """
    if not business_key:
        return "", ""
    parts = business_key.split(":", 3)
    version_ref = parts[1] if len(parts) > 1 else ""
    trigger_revision = parts[2] if len(parts) > 2 else ""
    return version_ref, trigger_revision


class KafkaCompletionPublisher:
    """Publish ``task_completed`` envelopes to the governance-events topic."""

    def __init__(
        self,
        bootstrap_servers: str,
        producer_factory: Any | None = None,
        send_timeout_seconds: float = 10.0,
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self._producer_factory = producer_factory
        self._send_timeout_seconds = send_timeout_seconds
        self._producer = None

    def _lazy_producer(self):
        if self._producer is None:
            if self._producer_factory is not None:
                self._producer = self._producer_factory(self.bootstrap_servers)
            else:
                from kafka import KafkaProducer  # lazily imported so tests run broker-free

                self._producer = KafkaProducer(bootstrap_servers=self.bootstrap_servers)
        return self._producer

    def build_envelope(self, execution: dict[str, Any]) -> tuple[bytes, str]:
        """Build ``(encoded_envelope, partition_key)`` for one completed execution."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        mapping_domain_id = str(execution.get("mapping_domain_id") or "")
        task_node_id = str(execution.get("task_node_id") or "")
        execution_id = str(execution.get("execution_id") or "")
        draft_id = execution.get("draft_id")
        finished_at = str(execution.get("finished_at") or now)
        version_ref, trigger_revision = _split_business_key(execution.get("business_key"))
        # The coordinator router looks for node_version_ref / task_node_version_ref
        # / target_node_version_ref. Emit node_version_ref alongside the schema's
        # completed_version_ref so neither side has to guess the other's name.
        payload = {
            "mapping_domain_id": mapping_domain_id,
            "task_node_id": task_node_id,
            "completed_version_ref": version_ref,
            "node_version_ref": version_ref,
            "execution_id": execution_id,
            "draft_id": draft_id,
            "completed_at": finished_at,
            "result_ref": draft_id or execution_id,
            "formal_revision_id": trigger_revision,
        }
        envelope = {
            "message_id": f"task_completed:{execution_id}",
            "message_type": "task_completed",
            "schema_version": 1,
            "dedupe_key": f"{mapping_domain_id}:{task_node_id}:{version_ref}:task_completed",
            "occurred_at": finished_at,
            "published_at": now,
            "producer": {"service": "gateway-subscriber"},
            "routing": {"partition_key": f"{task_node_id}:{version_ref}"},
            # Business fields kept flat as well so a coordinator that reads them
            # off the envelope (like the handoff producer's siblings) still works.
            "event_id": f"task_completed:{execution_id}",
            "event_type": "task_completed",
            "mapping_domain_id": mapping_domain_id,
            "target": {"kind": "task_node", "id": task_node_id},
            "payload": payload,
        }
        body = json.dumps(envelope, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return body, f"{task_node_id}:{version_ref}"

    def publish(self, *, execution: dict[str, Any]) -> None:
        """Send one ``task_completed`` and confirm the broker accepted it.

        Raises :class:`CompletionPublishError` on any failure so the outbox keeps
        the event pending for a later retry (ai4-odwi). ``send()`` alone is
        fire-and-forget; waiting on the returned future is what makes "published"
        mean the broker actually took the record.
        """
        try:
            body, key = self.build_envelope(execution)
            future = self._lazy_producer().send(
                _GOVERNANCE_TOPIC, key=key.encode("utf-8"), value=body
            )
            get = getattr(future, "get", None)
            if callable(get):
                get(timeout=self._send_timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - surface as a retryable failure
            raise CompletionPublishError(
                f"task_completed publish failed for execution={execution.get('execution_id')}: {exc}"
            ) from exc

    def close(self) -> None:
        if self._producer is not None:
            try:
                self._producer.close()
            except Exception:  # noqa: BLE001
                pass
            self._producer = None
