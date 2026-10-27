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
import threading

from task_agent_worker.config import WorkerSettings
from task_agent_worker.runtime import FastAgentDeepSeekRuntime, FastAgentPassthroughRuntime
from task_agent_worker.store import ExecutionStore

from .dashboard_source import build_queue_fragment, create_queue_dashboard_server
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
    """Pick the real model runtime, or the passthrough one when explicitly asked.

    ai4-c61f: the passthrough runtime writes a stub history and reports
    ``completed``, so falling back to it on a missing key made an unconfigured
    subscriber look like a working one. It now requires
    ``SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME=1``; otherwise the caller fails fast.
    """
    if settings.api_key:
        return FastAgentDeepSeekRuntime(settings)
    if os.environ.get("SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME") == "1":
        return FastAgentPassthroughRuntime(
            str(settings.home), settings.connection_scope, settings.session_dir
        )
    raise SystemExit(
        "no Worker runtime: the DeepSeek API key is unset and the passthrough "
        "runtime is not enabled (SCIWEAVE_GATEWAY_PASSTHROUGH_RUNTIME=1)"
    )


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
            queue.commit(message)
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


def start_dashboard_server(
    store: ExecutionStore,
    topics: list[str],
    group_id: str | None,
    queue_kind: str,
):
    """Serve the read-only queue dashboard source when a port is configured.

    ai4-nvuj: ``dashboard-api`` has a ``queue`` source slot that nothing served,
    so the Web dashboard's listener area was permanently unavailable. The
    endpoint is opt-in (``SCIWEAVE_SUBSCRIBER_DASHBOARD_PORT``) to keep existing
    subscriber deployments unchanged.
    """
    port_text = os.environ.get("SCIWEAVE_SUBSCRIBER_DASHBOARD_PORT", "").strip()
    if not port_text:
        return None
    host = os.environ.get("SCIWEAVE_SUBSCRIBER_DASHBOARD_HOST", "127.0.0.1").strip() or "127.0.0.1"
    token = os.environ.get("SCIWEAVE_SUBSCRIBER_DASHBOARD_TOKEN", "").strip() or None
    server = create_queue_dashboard_server(
        lambda: build_queue_fragment(
            store=store, topics=topics, group_id=group_id, queue_kind=queue_kind
        ),
        host=host,
        port=int(port_text),
        token=token,
    )
    threading.Thread(target=server.serve_forever, name="queue-dashboard", daemon=True).start()
    return server


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
    queue_kind = "kafka" if isinstance(queue, KafkaQueueClient) else "fake"
    queue.subscribe(topics)
    service = SubscriberService(store, agent_id)
    runner = SubscriberWorkerRunner(store, service, build_runtime(settings), build_draft_writer())
    dashboard = start_dashboard_server(
        store,
        topics,
        os.environ.get("SCIWEAVE_QUEUE_GROUP_ID", "").strip() or None,
        queue_kind,
    )
    try:
        run_loop(service, runner, queue)
    finally:
        if dashboard is not None:
            dashboard.shutdown()
            dashboard.server_close()
        queue.close()
        store.close()


if __name__ == "__main__":
    sys.exit(main())