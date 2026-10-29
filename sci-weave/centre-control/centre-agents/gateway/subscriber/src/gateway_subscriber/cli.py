"""Subscriber console-script entry point.

Reads all configuration from the environment (``uv run --env-file .env``), then
runs the fixed loop:

    poll -> persist queued record -> run Worker -> commit offset

The offset is committed only after the Worker loop fully ended, so a crash
replays the message and the business key blocks the duplicate.
"""

from __future__ import annotations

import logging
import os
import sys
import threading

from task_agent_worker.assembly import CentreConfigError
from task_agent_worker.config import WorkerSettings
from task_agent_worker.runtime import FastAgentDeepSeekRuntime, FastAgentPassthroughRuntime
from task_agent_worker.store import ExecutionStore

from .dashboard_source import build_queue_fragment, create_queue_dashboard_server
from .completion_publisher import KafkaCompletionPublisher
from .draft_writer import BufferMCPDraftWriter
from .queue import FakeQueueClient, KafkaQueueClient, QueueClient
from .service import SubscriberService
from .worker_runner import SubscriberWorkerRunner

_log = logging.getLogger("gateway_subscriber")


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

    ai4-349h: the real runtime reads ``definitions/``, ``libs/mcp-libs/`` and
    ``rules/`` in its constructor, so a broken definition stops the subscriber at
    startup with the variable and path named. Before that it stopped on the first
    execution, as ``fast_agent_runtime_error``.
    """
    if settings.api_key:
        try:
            return FastAgentDeepSeekRuntime(settings)
        except CentreConfigError as error:
            raise SystemExit(f"centre agent configuration is unusable: {error}") from error
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
            # A malformed/poison message must not kill the whole consumer: log
            # it, skip (commit past) it, and keep serving later messages. Before
            # this guard a single bad envelope (e.g. a producer using a different
            # schema) raised ValueError and crashed the subscriber process, so
            # every subsequent handoff went unprocessed.
            try:
                service.handle_message(message)
            except Exception as exc:  # noqa: BLE001 - poison-pill isolation
                # Nothing was persisted, so there is no queued record to re-pick:
                # commit past it and leave a trace (ai4-onvr).
                _log.warning(
                    "skipping unprocessable queue message topic=%s partition=%s offset=%s: %s",
                    message.topic, message.partition, message.offset, exc,
                )
            else:
                for target in service.queued_targets():
                    try:
                        runner.run_once(target)
                    except Exception:
                        # One broken target must not stop the others in the batch;
                        # its queued record stays so the next poll retries it.
                        _log.exception(
                            "subscriber worker failed for target=%s; leaving it queued", target,
                        )
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


def build_completion_publisher():
    """Publish ``task_completed`` to the governance topic when configured (B6).

    Opt-in: without ``SCIWEAVE_GOVERNANCE_KAFKA_BOOTSTRAP`` the subscriber runs
    exactly as before (no producer), so deployments that do not run a
    coordinator are unchanged.
    """
    bootstrap = os.environ.get("SCIWEAVE_GOVERNANCE_KAFKA_BOOTSTRAP", "").strip()
    if not bootstrap:
        return None
    return KafkaCompletionPublisher(bootstrap)


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
    completion_publisher = build_completion_publisher()
    runner = SubscriberWorkerRunner(
        store, service, build_runtime(settings), build_draft_writer(), completion_publisher
    )
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
        if completion_publisher is not None:
            completion_publisher.close()
        queue.close()
        store.close()


if __name__ == "__main__":
    sys.exit(main())