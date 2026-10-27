"""Task Agent gateway/subscriber service-template entry point.

Outbound consumer: connects to the central Redpanda queue and drives the Work
Agent runtime.  Configuration comes entirely from the environment; when queue
bootstrap and consumer group are configured the real kafka-python client is
used, otherwise the deterministic FakeQueue keeps local tests and demos running
without a broker.

When ``DATABASE_PATH`` is set, inbound messages are durably recorded in the
inbox before any execution, a missing workflow binding keeps the message
``awaiting_workflow_binding``, and ``queued`` rows left by a previous run are
re-driven at startup.

The subscriber deliberately holds **no draft-box credentials** and never writes
drafts itself (ai4-z3z4, ai4-4zjz). Drafts are written by the agent inside the
worker through the draft-box MCP server injected into its fast-agent config, so
this process only drives the state machine.

Envelope reading is deliberately name-based across positions (ai4-u9gj). The
repo currently carries three hand-written envelope shapes and the
``message-envelope`` package has no caller at all (ai4-derq), so the producer
that exists today omits ``target``, ``event_id`` and ``schema_version``
entirely. Reading only one layout meant ``target_id`` fell back to the Kafka
key, which is ``"{task_node_id}:{target_node_version_ref}"`` — a compound string
that defeated the Worker Lease and leaked into the draft box as
``source_target_node_id``.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Mapping

from work_agent_runtime import (
    InboxStore,
    KafkaQueueClient,
    WorkerLease,
    WorkAgentRuntime,
)
from work_agent_runtime.worker_dispatch import LeaveQueued, WorkerSubprocess

#: Envelope positions this consumer understands. ``payload``-nested first: that
#: is the shape ``message-envelope`` defines, and the flat one is what the
#: coordinator publishes today.
_PAYLOAD = "payload"


class EnvelopeError(ValueError):
    """An inbound message is missing something the runtime needs to run it."""


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value or not value.strip():
        raise SystemExit(f"{name} must be configured through the environment")
    return value.strip()


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def field(envelope: Mapping[str, Any], name: str) -> str:
    """Read ``name`` from the payload, then from the envelope top level.

    A field is looked up by name rather than by position because the two live
    envelope shapes disagree only on nesting. Returns "" when absent.
    """
    payload = envelope.get(_PAYLOAD)
    if isinstance(payload, Mapping):
        value = _text(payload.get(name))
        if value:
            return value
    return _text(envelope.get(name))


def routing_field(envelope: Mapping[str, Any], name: str) -> str:
    """Read a routing field: ``routing.<name>``, then the top level."""
    routing = envelope.get("routing")
    if isinstance(routing, Mapping):
        value = _text(routing.get(name))
        if value:
            return value
    return _text(envelope.get(name))


def task_node_id(envelope: Mapping[str, Any]) -> str:
    """The TaskNode this handoff is for; never the Kafka key.

    ``message.key`` is not a fallback on purpose: the coordinator sets it to
    ``"{task_node_id}:{target_node_version_ref}"``, so falling back silently
    turns one TaskNode into one target per version.
    """
    value = field(envelope, "task_node_id")
    if not value:
        raise EnvelopeError("task_node_id is missing from the envelope payload")
    return value


def message_id(envelope: Mapping[str, Any], key: str | None, offset: int) -> str:
    """The event identity: ``message_id``, then ``event_id``, then the key.

    The offset is the last resort and is process-local, so a restart can
    re-attribute the same message; the inbox ``dedupe_key`` still blocks the
    rerun, and the alternative is dropping the message.
    """
    return field(envelope, "message_id") or field(envelope, "event_id") or (key or "") or str(offset)


#: Where a producer might put the text this handoff asks for. There is no
#: single answer yet: the message-envelope package defines none, and the
#: coordinator publishes none (ai4-derq arbitrates the shape, ai4-1e9e the
#: storage). Reading the names a producer plausibly chose is a stopgap, and
#: `TASK_TEXT_FIELDS` being a list at all is the record that the protocol has
#: a hole.
TASK_TEXT_FIELDS = ("task_text", "command_text", "task_brief", "instruction", "task_description")


def task_text(envelope: Mapping[str, Any]) -> str:
    """The handoff's instruction text, or "" when the producer sent none.

    Empty is a fact, not a failure: every message published today carries no
    task text, so raising here would refuse every real handoff. The subscriber
    records the emptiness and `worker_shell.task_instruction` turns it into an
    explicit "only a node reference arrived" instruction rather than letting
    the node id masquerade as one.
    """
    for name in TASK_TEXT_FIELDS:
        value = field(envelope, name)
        if value:
            return value
    return ""


def build_runtime() -> WorkAgentRuntime:
    """Assemble the subscriber-side runtime: inbox, lease and worker dispatch.

    Never a draft writer: the draft box belongs to the worker (ai4-z3z4,
    ai4-4zjz). The subscriber's job is to claim the handoff, keep the Worker
    Lease, start one worker process and commit the offset (ai4-0fwc).

    Dispatch is on only when ``DATABASE_PATH`` is configured. Without a durable
    inbox there is no row for a worker subprocess to pick up, so the in-memory
    demo path keeps running inline; that is a deliberate split rather than a
    silent fallback, and `build_runtime` says which mode it chose.
    """
    runtime = WorkAgentRuntime()
    db_path = os.environ.get("DATABASE_PATH", "").strip()
    if not db_path:
        print(
            "notice: DATABASE_PATH is unset; running inline with the in-memory "
            "runtime and no worker subprocess",
            flush=True,
        )
        return runtime
    runtime.inbox = InboxStore(db_path)
    # Same file as the inbox: the lease, the inbox and the execution store must
    # not disagree about which database is current.
    runtime.lease = WorkerLease(db_path)
    runtime.dispatcher = build_dispatcher()
    return runtime


def build_dispatcher():
    """The callable that runs one handoff in a worker subprocess.

    ``SCIWEAVE_WORKER_DISPATCH=0`` turns it off, which is how a deployment runs
    the subscriber and the worker as two ordinary services instead of the
    subscriber starting one per message.
    """
    if os.environ.get("SCIWEAVE_WORKER_DISPATCH", "1").strip() == "0":
        print("notice: worker dispatch is disabled; handoffs stay queued", flush=True)
        # Not None: falling back to the inline path would write a fabricated
        # draft and mark the row processed, which is the opposite of handing it
        # to a separate worker service.
        return LeaveQueued()
    return WorkerSubprocess()


def build_queue(agent_id: str):
    bootstrap = os.environ.get("QUEUE_URL", "").strip()
    group = os.environ.get("QUEUE_CONSUMER_GROUP", "").strip()
    if bootstrap and group:
        return KafkaQueueClient(bootstrap, group)
    from work_agent_runtime import FakeQueue

    return FakeQueue()


def run_loop(runtime: WorkAgentRuntime, queue, topics: list[str], *, poll_timeout_ms: int = 1000, max_messages: int | None = None, agent_id: str = "", supported_schema_version: int = 1) -> int:
    """Poll the queue, hand each accepted message to the inbox-first runtime, then commit.

    Returns the number of messages processed.  Offsets are committed only after
    the runtime has fully handled the message; a crash replays messages and the
    inbox ``dedupe_key`` (plus the business key) blocks duplicates.

    A message this process cannot act on is committed past and reported, never
    silently dropped and never allowed to stall the partition.

    ``schema_version`` is enforced when present. It is *absent* on every message
    the coordinator publishes today (ai4-derq), so treating absence as a
    rejection would refuse every real handoff; treating it as acceptance keeps
    the contract's tolerant-reading rule ("same schema version is always
    consumable"). The tradeoff is logged once per process instead of being
    papered over.
    """
    processed = 0
    version_absent_reported = False
    while max_messages is None or processed < max_messages:
        messages = queue.poll(poll_timeout_ms)
        if not messages:
            if max_messages is not None:
                break
            continue
        for message in messages:
            envelope = message.payload or {}
            target_agent = routing_field(envelope, "target_agent_id")
            if target_agent and agent_id and target_agent != agent_id:
                print(f"skip {message.offset}: target_agent_id mismatch", flush=True)
                queue.commit()
                continue
            schema_version = envelope.get("schema_version")
            if schema_version is None:
                if not version_absent_reported:
                    print(
                        "notice: envelope carries no schema_version; accepting "
                        f"without a version check (expected {supported_schema_version})",
                        flush=True,
                    )
                    version_absent_reported = True
            elif schema_version != supported_schema_version:
                print(f"skip {message.offset}: schema_version unsupported", flush=True)
                queue.commit()
                continue
            try:
                target_id = task_node_id(envelope)
            except EnvelopeError as error:
                print(f"skip {message.offset}: {error}", flush=True)
                queue.commit()
                continue
            runtime.handle_inbound(
                target_id,
                message_id(envelope, message.key, message.offset),
                task_text=task_text(envelope),
            )
            queue.commit()
            processed += 1
    return processed


def main() -> None:
    agent_id = required("SCIWEAVE_AGENT_ID")
    topics = [topic.strip() for topic in required("SCIWEAVE_SUBSCRIBER_TOPICS").split(",") if topic.strip()]
    if not topics:
        raise SystemExit("SCIWEAVE_SUBSCRIBER_TOPICS must list at least one topic")
    runtime = build_runtime()
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