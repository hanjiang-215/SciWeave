"""HandoffPublisherPort implementation over the central Redpanda queue.

Publishes ``task_handoff_ready`` envelopes to the per-executor topic
``sciweave.task-handoff.<agent_id>`` (fixed physical topic per the
message-delivery-recovery contract; the logical TaskNode channel is expressed
by the routing key/payload, not by a dynamic topic). Offset discipline belongs
to the consuming subscriber; this side only produces with a kafka-python
producer and reports transient failures back to the coordinator for retry.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .ports import HandoffPublisherPort, HandoffReadyMessage

_log = logging.getLogger(__name__)

_TASK_HANDOFF_TOPIC_PREFIX = "sciweave.task-handoff."


class KafkaHandoffPublisher(HandoffPublisherPort):
    """kafka-python producer for task_handoff_ready envelopes."""

    def __init__(
        self,
        bootstrap_servers: str,
        *,
        timeout_seconds: float = 5.0,
        allow_unknown_agent_topic: bool = False,
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.timeout_seconds = timeout_seconds
        self.allow_unknown_agent_topic = allow_unknown_agent_topic
        self._producer = None

    def _lazy_producer(self):
        if self._producer is None:
            from kafka import KafkaProducer  # lazily imported so tests run broker-free

            self._producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"),
            )
        return self._producer

    def publish(self, message: HandoffReadyMessage) -> None:
        topic = self._topic_for(message.target_agent_id)
        if topic is None:
            if self.allow_unknown_agent_topic:
                # ai4-2hv6: the caller marks the dispatch published as soon as this
                # returns, so a silent return loses the handoff with no trace.
                # Warn, and only stay silent because the flag was set explicitly.
                _log.warning(
                    "no task-handoff topic for agent %r; dropping handoff for %s",
                    message.target_agent_id, message.task_node_id,
                )
                return
            raise RuntimeError(f"no task-handoff topic for agent {message.target_agent_id!r}")
        envelope: dict[str, Any] = {
            # NOTE: the per-agent subscriber expects the shared governance-event
            # envelope shape ({event_id, target:{kind,id}, payload:{...}}), the
            # same one research-map/wiki/gateway-ingest emit. A previous flat
            # envelope (message_type/task_node_id/...) made the subscriber crash
            # with "id is required" because it reads envelope["target"]["id"].
            "event_id": f"task-handoff:{message.pending_handoff_id}:{message.target_node_version_ref}",
            "event_type": "task_handoff_ready",
            "message_type": "task_handoff_ready",
            "mapping_domain_id": message.mapping_domain_id,
            "target": {"kind": "task_node", "id": message.task_node_id},
            "task_node_id": message.task_node_id,
            "target_node_version_ref": message.target_node_version_ref,
            "target_agent_id": message.target_agent_id,
            "pending_handoff_id": message.pending_handoff_id,
            "trigger_revision_id": message.trigger_revision_id,
            "payload": {
                "formal_revision_id": message.trigger_revision_id,
                "target_node_version_ref": message.target_node_version_ref,
                "task_node_id": message.task_node_id,
                "pending_handoff_id": message.pending_handoff_id,
            },
        }
        key = f"{message.task_node_id}:{message.target_node_version_ref}".encode("utf-8")
        self._lazy_producer().send(topic, key=key, value=envelope).get(timeout=self.timeout_seconds)

    def close(self) -> None:
        if self._producer is not None:
            self._producer.close()
            self._producer = None

    @staticmethod
    def _topic_for(agent_id: str) -> str | None:
        if not agent_id or not agent_id.strip():
            return None
        return f"{_TASK_HANDOFF_TOPIC_PREFIX}{agent_id.strip()}"