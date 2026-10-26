"""Queue client boundary for a researcher-owned Work Agent.

The subscriber connects outbound to the central Redpanda queue.  ``FakeQueue``
keeps its deterministic in-memory behavior (used by the runtime tests), and
``KafkaQueueClient`` wraps ``kafka-python`` for real central-queue consumption.

Offset commit discipline follows the message-queue contract: offsets are
committed only after the Worker loop has fully ended; a crash replays messages
and the business key blocks duplicates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass(frozen=True)
class QueueMessage:
    topic: str
    partition: int
    offset: int
    key: str | None
    payload: dict


class QueueClient(Protocol):
    def subscribe(self, topics: list[str]) -> None: ...
    def poll(self, timeout_ms: int) -> list[QueueMessage]: ...
    def commit(self) -> None: ...
    def close(self) -> None: ...


class FakeQueue:
    """Deterministic in-memory queue retained for tests and local demos."""

    def __init__(self) -> None:
        self._handler: Callable[[str, str], object] | None = None
        self.messages: list[QueueMessage] = []
        self.committed = False

    def subscribe(self, handler: Callable[[str, str], object]) -> None:
        self._handler = handler

    def deliver(self, target_id: str, event_id: str) -> object:
        if self._handler is None:
            raise RuntimeError("subscriber is not configured")
        return self._handler(target_id, event_id)

    def poll(self, timeout_ms: int = 0) -> list[QueueMessage]:
        batch, self.messages = self.messages, []
        return batch

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self._handler = None


class KafkaQueueClient:
    """Thin kafka-python adapter for the central single-node Redpanda service."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        *,
        auto_offset_reset: str = "earliest",
        session_timeout_ms: int = 10_000,
    ) -> None:
        from kafka import KafkaConsumer  # lazy import keeps runtime tests broker-free

        self.consumer = KafkaConsumer(
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            auto_offset_reset=auto_offset_reset,
            enable_auto_commit=False,
            session_timeout_ms=session_timeout_ms,
            value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
        )

    def subscribe(self, topics: list[str]) -> None:
        self.consumer.subscribe(topics)

    def poll(self, timeout_ms: int = 1000) -> list[QueueMessage]:
        records = self.consumer.poll(timeout_ms=timeout_ms, max_records=100)
        batch: list[QueueMessage] = []
        for topic_partition, partition_messages in records.items():
            for raw in partition_messages:
                batch.append(
                    QueueMessage(
                        topic=topic_partition.topic,
                        partition=topic_partition.partition,
                        offset=raw.offset,
                        key=raw.key.decode("utf-8") if raw.key else None,
                        payload=raw.value,
                    )
                )
        return batch

    def commit(self) -> None:
        self.consumer.commit()

    def close(self) -> None:
        self.consumer.close()