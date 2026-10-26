"""Task Agent gateway/subscriber service-template entry point.

Outbound consumer: connects to the central Redpanda queue and drives the Work
Agent runtime.  Configuration comes entirely from the environment; when queue
bootstrap and consumer group are configured the real kafka-python client is
used, otherwise the deterministic FakeQueue keeps local tests and demos running
without a broker.

When ``DATABASE_PATH`` is set, inbound messages are durably recorded in the
inbox before any execution, a missing workflow binding keeps the message
``awaiting_workflow_binding``, and ``queued`` rows left by a previous run are
re-driven at startup.  When ``DRAFT_BUFFER_MCP_URL``/``DRAFT_BUFFER_MCP_TOKEN``
are set, execution results are written to the real central draft box instead
of the fake one.
"""

from __future__ import annotations

import os
import sys

from work_agent_runtime import BufferMCPDraftWriter, InboxStore, KafkaQueueClient, WorkAgentRuntime


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value or not value.strip():
        raise SystemExit(f"{name} must be configured through the environment")
    return value.strip()


def build_runtime(agent_id: str, namespace: str) -> WorkAgentRuntime:
    runtime = WorkAgentRuntime()
    db_path = os.environ.get("DATABASE_PATH", "").strip()
    if db_path:
        runtime.inbox = InboxStore(db_path)
    draft_url = os.environ.get("DRAFT_BUFFER_MCP_URL", "").strip()
    draft_token = os.environ.get("DRAFT_BUFFER_MCP_TOKEN", "").strip()
    if draft_url and draft_token:
        runtime.drafts = BufferMCPDraftWriter(
            endpoint=draft_url,
            token=draft_token,
            namespace=namespace,
            submitter_id=agent_id,
        )
    return runtime


def build_queue(agent_id: str):
    bootstrap = os.environ.get("QUEUE_URL", "").strip()
    group = os.environ.get("QUEUE_CONSUMER_GROUP", "").strip()
    if bootstrap and group:
        return KafkaQueueClient(bootstrap, group)
    from work_agent_runtime import FakeQueue

    return FakeQueue()


def run_loop(runtime: WorkAgentRuntime, queue, topics: list[str], *, poll_timeout_ms: int = 1000, max_messages: int | None = None, agent_id: str = "", supported_schema_version: str = "1") -> int:
    """Poll the queue, hand each accepted message to the inbox-first runtime, then commit.

    Returns the number of messages processed.  Offsets are committed only after
    the runtime has fully handled the message; a crash replays messages and the
    inbox ``dedupe_key`` (plus the business key) blocks duplicates.

    Messages are accepted only when they are addressed to this agent and carry
    a compatible envelope schema.  Guard fields are optional in the envelope:
    when present they are enforced, when absent the message is accepted (the
    topic already scopes delivery to this agent).
    """
    processed = 0
    while max_messages is None or processed < max_messages:
        messages = queue.poll(poll_timeout_ms)
        if not messages:
            if max_messages is not None:
                break
            continue
        for message in messages:
            envelope = message.payload or {}
            target = envelope.get("target") or {}
            target_agent = target.get("agent_id")
            if target_agent and agent_id and str(target_agent) != agent_id:
                print(f"skip {message.offset}: target_agent_id mismatch", flush=True)
                queue.commit()
                continue
            schema_version = envelope.get("schema_version")
            if schema_version is not None and str(schema_version) != supported_schema_version:
                print(f"skip {message.offset}: schema_version unsupported", flush=True)
                queue.commit()
                continue
            target_id = target.get("id") or (message.key or "")
            event_id = str(envelope.get("event_id") or message.key or message.offset)
            runtime.handle_inbound(str(target_id), event_id)
            queue.commit()
            processed += 1
    return processed


def main() -> None:
    agent_id = required("SCIWEAVE_AGENT_ID")
    namespace = os.environ.get("SCIWEAVE_DRAFT_NAMESPACE", "mapping").strip() or "mapping"
    topics = [topic.strip() for topic in required("SCIWEAVE_SUBSCRIBER_TOPICS").split(",") if topic.strip()]
    if not topics:
        raise SystemExit("SCIWEAVE_SUBSCRIBER_TOPICS must list at least one topic")
    runtime = build_runtime(agent_id, namespace)
    # Restart recovery: re-drive any queued inbox rows left by a previous run.
    recovered = runtime.drain_queued()
    if recovered:
        print(f"recovered {len(recovered)} queued message(s) from inbox", flush=True)
    queue = build_queue(agent_id)
    queue.subscribe(topics)
    try:
        run_loop(runtime, queue, topics)
    finally:
        queue.close()


if __name__ == "__main__":
    sys.exit(main())