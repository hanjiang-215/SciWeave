"""Queue client boundary for one Work Agent subscriber.

The subscriber connects outbound to the central queue.  ``QueueClient`` is the
port; ``FakeQueueClient`` drives deterministic behavior tests without a broker,
and ``KafkaQueueClient`` wraps ``kafka-python`` against the local Redpanda
service.

Offset commit discipline follows the message-queue contract:

- the consumer group holds offsets across restarts;
- ``auto.offset.reset=earliest`` for new groups;
- offsets are committed only after the Worker loop has fully ended, so a crash
  replays messages and the business key blocks duplicates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class QueueMessage:
    """One envelope pulled from a topic partition."""

    topic: str
    partition: int
    offset: int
    key: str | None
    payload: dict  # decoded envelope body


class QueueClient(Protocol):
    def subscribe(self, topics: list[str]) -> None: ...
    def poll(self, timeout_ms: int) -> list[QueueMessage]: ...
    def commit(self) -> None: ...
    def close(self) -> None: ...


class FakeQueueClient:
    """In-memory deterministic queue used by behavior tests and local demos."""

    def __init__(self) -> None:
        self.topics: list[str] = []
        self.messages: list[QueueMessage] = []
        self.committed = False

    def publish(self, topic: str, key: str, payload: dict) -> QueueMessage:
        message = QueueMessage(
            topic=topic,
            partition=0,
            offset=len(self.messages),
            key=key,
            payload=payload,
        )
        self.messages.append(message)
        return message

    def subscribe(self, topics: list[str]) -> None:
        self.topics = list(topics)

    def poll(self, timeout_ms: int = 0) -> list[QueueMessage]:
        batch, self.messages = self.messages, []
        return batch

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.topics = []


class KafkaQueueClient:
    """Thin kafka-python adapter for the local single-node Redpanda service."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        *,
        auto_offset_reset: str = "earliest",
        session_timeout_ms: int = 10_000,
    ) -> None:
        from kafka import KafkaConsumer  # imported lazily so tests can run without it

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