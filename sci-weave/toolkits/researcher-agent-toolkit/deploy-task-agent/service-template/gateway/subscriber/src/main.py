"""Task Agent gateway/subscriber service-template entry point.

Outbound consumer: connects to the central Redpanda queue and drives the Work
Agent runtime.  Configuration comes entirely from the environment; when queue
bootstrap and consumer group are configured the real kafka-python client is
used, otherwise the deterministic FakeQueue keeps local tests and demos running
without a broker.
"""

from __future__ import annotations

import os
import sys

from work_agent_runtime import KafkaQueueClient, WorkAgentRuntime


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value or not value.strip():
        raise SystemExit(f"{name} must be configured through the environment")
    return value.strip()


def build_queue(agent_id: str):
    bootstrap = os.environ.get("QUEUE_URL", "").strip()
    group = os.environ.get("QUEUE_CONSUMER_GROUP", "").strip()
    if bootstrap and group:
        return KafkaQueueClient(bootstrap, group)
    from work_agent_runtime import FakeQueue

    return FakeQueue()


def run_loop(runtime: WorkAgentRuntime, queue, topics: list[str], *, poll_timeout_ms: int = 1000, max_messages: int | None = None) -> int:
    """Poll the queue, hand each message to the runtime, then commit offset.

    Returns the number of messages processed.  Offsets are committed only after
    the runtime has fully handled the message (replay is blocked by the
    business key).
    """
    processed = 0
    while max_messages is None or processed < max_messages:
        messages = queue.poll(poll_timeout_ms)
        if not messages:
            if max_messages is not None:
                break
            continue
        for message in messages:
            target_id = ((message.payload.get("target") or {}).get("id")) or (message.key or "")
            event_id = str(message.payload.get("event_id") or message.key or message.offset)
            runtime.handle_message(str(target_id), event_id)
            queue.commit()
            processed += 1
    return processed


def main() -> None:
    agent_id = required("SCIWEAVE_AGENT_ID")
    topics = [topic.strip() for topic in required("SCIWEAVE_SUBSCRIBER_TOPICS").split(",") if topic.strip()]
    if not topics:
        raise SystemExit("SCIWEAVE_SUBSCRIBER_TOPICS must list at least one topic")
    runtime = WorkAgentRuntime()
    queue = build_queue(agent_id)
    queue.subscribe(topics)
    try:
        run_loop(runtime, queue, topics)
    finally:
        queue.close()


if __name__ == "__main__":
    sys.exit(main())