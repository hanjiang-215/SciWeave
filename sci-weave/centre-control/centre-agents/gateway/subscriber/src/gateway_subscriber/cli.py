"""Subscriber console-script entry point.

Reads all configuration from the environment (``uv run --env-file .env``), then
runs the fixed loop:

    poll -> persist queued record -> run Worker -> commit offset

The offset is committed only after the Worker loop fully ended, so a crash
replays the message and the business key blocks the duplicate.
"""

from __future__ import annotations

import os
import sys

from task_agent_worker.config import WorkerSettings
from task_agent_worker.runtime import FastAgentDeepSeekRuntime, FastAgentPassthroughRuntime
from task_agent_worker.store import ExecutionStore

from .draft_writer import BufferMCPDraftWriter
from .queue import FakeQueueClient, KafkaQueueClient, QueueClient
from .service import SubscriberService
from .worker_runner import SubscriberWorkerRunner


def required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} must be configured through the environment")
    return value


def build_runtime(settings: WorkerSettings):
    """Pick the credential-free passthrough runtime or the real model runtime."""
    if settings.api_key:
        return FastAgentDeepSeekRuntime(settings)
    return FastAgentPassthroughRuntime(str(settings.home), settings.connection_scope, settings.session_dir)


def build_queue(agent_id: str) -> QueueClient:
    bootstrap = os.environ.get("SCIWEAVE_QUEUE_BOOTSTRAP_SERVERS", "").strip()
    group = os.environ.get("SCIWEAVE_QUEUE_GROUP_ID", "").strip()
    if bootstrap and group:
        return KafkaQueueClient(bootstrap, group)
    return FakeQueueClient()


def run_loop(
    service: SubscriberService,
    runner: SubscriberWorkerRunner,
    queue: QueueClient,
    *,
    poll_timeout_ms: int = 1000,
    max_messages: int | None = None,
) -> int:
    """Run the subscriber loop until ``max_messages`` (or forever when ``None``).

    Returns the number of messages processed.  Each message is handled in order:
    persist -> run Worker -> commit offset.
    """
    processed = 0
    while max_messages is None or processed < max_messages:
        batch = queue.poll(poll_timeout_ms)
        if not batch:
            if max_messages is not None:
                break
            continue
        for message in batch:
            service.handle_message(message)
            for target in service.queued_targets():
                runner.run_once(target)
            queue.commit()
            processed += 1
    return processed


def build_draft_writer():
    """Central draft buffer writer only when the endpoint is configured."""
    endpoint = os.environ.get("SCIWEAVE_DRAFT_BUFFER_ENDPOINT", "").strip()
    token = os.environ.get("SCIWEAVE_DRAFT_BUFFER_TOKEN", "").strip()
    namespace = os.environ.get("SCIWEAVE_DRAFT_BUFFER_NAMESPACE", "").strip()
    submitter = os.environ.get("SCIWEAVE_DRAFT_BUFFER_SUBMITTER_ID", "").strip()
    if not endpoint or not token:
        return None
    return BufferMCPDraftWriter(
        endpoint=endpoint,
        token=token,
        namespace=namespace,
        submitter_id=submitter,
        base_formal_revision_id=os.environ.get("SCIWEAVE_DRAFT_BUFFER_BASE_REVISION", "").strip() or None,
    )


def main() -> None:
    agent_id = required_environment("SCIWEAVE_AGENT_ID")
    topics = [
        topic.strip()
        for topic in required_environment("SCIWEAVE_SUBSCRIBER_TOPICS").split(",")
        if topic.strip()
    ]
    if not topics:
        raise SystemExit("SCIWEAVE_SUBSCRIBER_TOPICS must list at least one topic")

    store = ExecutionStore(required_environment("SCIWEAVE_GATEWAY_DB"))
    settings = WorkerSettings.from_environment()
    settings.validate_runtime(require_api_key=bool(settings.api_key))

    queue = build_queue(agent_id)
    queue.subscribe(topics)
    service = SubscriberService(store, agent_id)
    runner = SubscriberWorkerRunner(store, service, build_runtime(settings), build_draft_writer())
    try:
        run_loop(service, runner, queue)
    finally:
        queue.close()
        store.close()


if __name__ == "__main__":
    sys.exit(main())