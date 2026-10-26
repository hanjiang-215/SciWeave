"""Centre Agent governance-event ingest console-script entry point.

Subscribes to ``sciweave.governance-events`` (consumer group
``sciweave.centre-workflow.<workflow_id>``, ``auto.offset.reset=earliest``),
drives ``CentreGovernanceConsumer`` per message and commits the offset only
after the message was fully handled, following the ai4-te1v message contract.

All configuration comes from the environment; never hard-coded.  With queue
bootstrap and group id configured the real kafka-python client is used,
otherwise a FakeQueue keeps local tests and demos broker-free.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Protocol

from .service import GovernanceEnvelopeError

from .domain_mcp import BufferMGatewayMCPClient
from .service import CentreGovernanceConsumer, SqliteProcessedKeyStore


def required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value or not value.strip():
        raise SystemExit(f"{name} must be configured through the environment")
    return value.strip()


class QueueMessage(Protocol):
    topic: str
    partition: int
    offset: int
    key: str | None
    payload: dict[str, Any]


class QueueClient(Protocol):
    def subscribe(self, topics: list[str]) -> None: ...
    def poll(self, timeout_ms: int) -> list[QueueMessage]: ...
    def commit(self, message: QueueMessage | None = None) -> None: ...
    def close(self) -> None: ...


class FakeQueue:
    """Deterministic in-memory queue for tests and local demos."""

    def __init__(self) -> None:
        self.messages: list[QueueMessage] = []
        self.committed = False
        self.commits: list[Any] = []

    def subscribe(self, topics: list[str]) -> None:
        return

    def poll(self, timeout_ms: int = 0) -> list[QueueMessage]:
        batch, self.messages = self.messages, []
        return batch

    def commit(self, message: QueueMessage | None = None) -> None:
        self.committed = True
        self.commits.append(None if message is None else (message.topic, message.partition, message.offset))

    def close(self) -> None:
        self.messages = []


class KafkaQueueClient:
    """Thin kafka-python adapter for the central single-node Redpanda service."""

    def __init__(self, bootstrap_servers: str, group_id: str, *, auto_offset_reset: str = "earliest") -> None:
        from kafka import KafkaConsumer  # lazy import keeps tests broker-free

        self.consumer = KafkaConsumer(
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            auto_offset_reset=auto_offset_reset,
            enable_auto_commit=False,
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
                    _RawMessage(
                        topic=topic_partition.topic,
                        partition=topic_partition.partition,
                        offset=raw.offset,
                        key=raw.key.decode("utf-8") if raw.key else None,
                        payload=raw.value,
                    )
                )
        return batch

    def commit(self, message: QueueMessage | None = None) -> None:
        """Commit one record's offset, not the whole polled batch.

        `consumer.commit()` commits the consumer position, which is the end
        of the batch: crashing after the first of 100 records would mark the
        other 99 consumed and lose them.
        """
        if message is None:
            self.consumer.commit()
            return
        from kafka import OffsetAndMetadata, TopicPartition

        self.consumer.commit(
            {
                TopicPartition(message.topic, message.partition): OffsetAndMetadata(
                    message.offset + 1, None
                )
            }
        )

    def close(self) -> None:
        self.consumer.close()


@dataclass(frozen=True)
class _RawMessage:
    topic: str
    partition: int
    offset: int
    key: str | None
    payload: dict[str, Any]


def build_queue(group_id: str) -> QueueClient:
    bootstrap = os.environ.get("SCIWEAVE_QUEUE_BOOTSTRAP_SERVERS", "").strip()
    group = os.environ.get("SCIWEAVE_QUEUE_GROUP_ID", "").strip()
    if bootstrap and group:
        return KafkaQueueClient(bootstrap, group)
    return FakeQueue()


def build_consumer(mcp_url: str, mcp_token: str, db_path: str) -> CentreGovernanceConsumer:
    mcp = BufferMGatewayMCPClient(endpoint=mcp_url, token=mcp_token)
    keys = SqliteProcessedKeyStore(db_path)
    return CentreGovernanceConsumer(mcp, keys)


def run_loop(
    consumer: CentreGovernanceConsumer,
    queue: QueueClient,
    *,
    poll_timeout_ms: int = 1000,
    max_messages: int | None = None,
) -> int:
    """Run the ingest loop: poll -> consume -> commit.

    Returns the number of messages consumed.  Each record's offset is committed
    on its own after the consumer handled it, so a crash mid-batch replays only
    the unhandled records.  A malformed envelope is a permanent property of
    that record: it is recorded by the consumer, committed past, and does not
    stop the loop -- otherwise one bad event pins the partition forever.
    """
    consumed = 0
    while max_messages is None or consumed < max_messages:
        batch = queue.poll(poll_timeout_ms)
        if not batch:
            if max_messages is not None:
                break
            continue
        for message in batch:
            envelope = message.payload if isinstance(message.payload, dict) else {}
            try:
                consumer.consume(envelope)
            except GovernanceEnvelopeError:
                queue.commit(message)
                consumed += 1
                continue
            queue.commit(message)
            consumed += 1
    return consumed


def main() -> None:
    group_id = required_environment("SCIWEAVE_QUEUE_GROUP_ID")
    topics = [
        topic.strip()
        for topic in required_environment("SCIWEAVE_SUBSCRIBER_TOPICS").split(",")
        if topic.strip()
    ]
    if not topics:
        raise SystemExit("SCIWEAVE_SUBSCRIBER_TOPICS must list at least one topic")
    mcp_url = required_environment("SCIWEAVE_DOMAIN_MCP_URL")
    mcp_token = required_environment("SCIWEAVE_DOMAIN_MCP_TOKEN")
    db_path = required_environment("SCIWEAVE_INGEST_DB")

    queue = build_queue(group_id)
    queue.subscribe(topics)
    consumer = build_consumer(mcp_url, mcp_token, db_path)
    try:
        run_loop(consumer, queue)
    finally:
        queue.close()


if __name__ == "__main__":
    sys.exit(main())