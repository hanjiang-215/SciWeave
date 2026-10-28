"""Runtime loop tests for the coordinator process entry point (ai4-3gvf).

``src/main.py`` is the process entry point, not part of the installed package,
so it is loaded from its path instead of by module name. These tests cover the
two rules the loop owns: commit the batch position whatever the batch
contained, and never let one event kill the loop.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from coordinator.adapter_events import GovernanceEventConsumer

_MAIN_PATH = Path(__file__).resolve().parents[1] / "src" / "main.py"
_spec = importlib.util.spec_from_file_location("coordinator_entry_point", _MAIN_PATH)
assert _spec is not None and _spec.loader is not None
_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_main)

CoordinatorRuntime = _main.CoordinatorRuntime


class _RecordingService:
    def __init__(self, explode_on: str | None = None) -> None:
        self.formal_revisions: list[tuple[str, str]] = []
        self.completions: list[tuple[str, str, str]] = []
        self.explode_on = explode_on
        self.retried = 0
        self.scanned = 0

    def startup_scan(self) -> None:
        self.scanned += 1

    def on_formal_revision_published(self, mapping_domain_id: str, formal_revision_id: str) -> None:
        if self.explode_on == formal_revision_id:
            raise RuntimeError("poison event")
        self.formal_revisions.append((mapping_domain_id, formal_revision_id))

    def on_task_completed(self, mapping_domain_id: str, task_node_id: str, version_ref: str) -> None:
        self.completions.append((mapping_domain_id, task_node_id, version_ref))

    def retry_pending_dispatches(self) -> int:
        self.retried += 1
        return 0


class _FakeEvents:
    def __init__(self, *batches: list[dict]) -> None:
        self.batches = [list(batch) for batch in batches]
        self.commits = 0
        self.closed = False

    def poll(self, timeout_ms: int = 100) -> list[dict]:
        return self.batches.pop(0) if self.batches else []

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        self.closed = True


class _FakePublisher:
    def close(self) -> None:
        return None


def _runtime(service: _RecordingService, events: _FakeEvents) -> CoordinatorRuntime:
    return CoordinatorRuntime(
        service=service,
        publisher=_FakePublisher(),
        connection=None,
        poll_seconds=0.0,
        events=events,
        event_router=GovernanceEventConsumer(service),
    )


def test_batch_position_is_committed_even_when_no_event_routes():
    """A batch of events nobody consumes still advances the offset.

    Otherwise every restart replays the whole topic from the last commit, and
    the consumer position never reflects what has been read.
    """
    events = _FakeEvents([{"event_type": "candidate_created", "mapping_domain_id": "iris"}])
    runtime = _runtime(_RecordingService(), events)

    assert runtime.on_event_batch() == 0
    assert events.commits == 1


def test_a_poison_event_does_not_stop_the_batch():
    events = _FakeEvents(
        [
            {
                "event_type": "formal_revision_published",
                "mapping_domain_id": "iris",
                "payload": {"formal_revision_id": "rev-1"},
            },
            {
                "event_type": "formal_revision_published",
                "mapping_domain_id": "iris",
                "payload": {"formal_revision_id": "rev-2"},
            },
        ]
    )
    service = _RecordingService(explode_on="rev-1")
    runtime = _runtime(service, events)

    assert runtime.on_event_batch() == 1
    assert service.formal_revisions == [("iris", "rev-2")]
    assert events.commits == 1


def test_an_empty_poll_does_not_commit():
    events = _FakeEvents()
    runtime = _runtime(_RecordingService(), events)

    assert runtime.on_event_batch() == 0
    assert events.commits == 0


def test_poll_once_retries_non_terminal_dispatches():
    """The poll loop retries through the public service method, not a private one."""
    service = _RecordingService()
    runtime = _runtime(service, _FakeEvents())

    runtime.poll_once()

    assert service.retried == 1


class _OutageEvents:
    """Broker is unreachable for the first N polls, then stops the loop."""

    def __init__(self, failures: int = 3) -> None:
        self.failures = failures
        self.polls = 0
        self.closed = False
        self.runtime: object | None = None

    def poll(self, timeout_ms: int = 100) -> list[dict]:
        self.polls += 1
        if self.polls <= self.failures:
            raise RuntimeError("kafka: broker is not available")
        if self.runtime is not None:
            self.runtime._running = False  # type: ignore[attr-defined]
        return []

    def commit(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _FakeConnection:
    def close(self) -> None:
        return None


def test_a_broker_outage_does_not_kill_the_loop():
    """ai4-xncm: one unreachable-broker poll used to terminate the process.

    supervisord then restarted it into the same outage, so the handoff chain
    stood still for as long as the broker was down. The loop must keep going.
    """
    import threading

    service = _RecordingService()
    events = _OutageEvents(failures=3)
    runtime = CoordinatorRuntime(
        service=service,
        publisher=_FakePublisher(),
        connection=_FakeConnection(),
        poll_seconds=0.0,
        events=events,
        event_router=GovernanceEventConsumer(service),
        max_poll_backoff_seconds=0.01,
    )
    events.runtime = runtime
    runtime._running = True

    thread = threading.Thread(target=runtime.serve_forever, daemon=True)
    thread.start()
    thread.join(timeout=10)

    assert not thread.is_alive(), "the loop did not stop when asked"
    assert events.polls >= 4, "the loop gave up after the first poll failure"
    assert service.scanned == 1
    assert events.closed is True


def test_governance_group_defaults_to_plain_coordinator(monkeypatch):
    monkeypatch.delenv("SCIWEAVE_COORDINATOR_KAFKA_GROUP_ID", raising=False)
    monkeypatch.delenv("SCIWEAVE_DEPLOYMENT_ENV", raising=False)
    assert _main._resolve_governance_group() == "coordinator"


def test_governance_group_uses_deployment_env_prefix(monkeypatch):
    monkeypatch.delenv("SCIWEAVE_COORDINATOR_KAFKA_GROUP_ID", raising=False)
    monkeypatch.setenv("SCIWEAVE_DEPLOYMENT_ENV", "native")
    assert _main._resolve_governance_group() == "coordinator-native"


def test_explicit_group_id_wins_over_deployment_env(monkeypatch):
    monkeypatch.setenv("SCIWEAVE_COORDINATOR_KAFKA_GROUP_ID", "  custom-group ")
    monkeypatch.setenv("SCIWEAVE_DEPLOYMENT_ENV", "native")
    assert _main._resolve_governance_group() == "custom-group"
