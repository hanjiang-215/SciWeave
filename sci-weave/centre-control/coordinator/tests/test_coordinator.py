"""Coordinator core tests (ai4-1y6q core regression + ai4-10ja defect fixes).

The fixture set mirrors the ai4-1y6q sandbox plus the ai4-10ja defect scenes:
root nodes are never auto-dispatched (only ``dispatch_root_task``), the
dispatch idempotency key excludes the trigger revision, ``done`` is terminal,
and ``executor_refs`` selects the first available agent.
"""

import sqlite3
from pathlib import Path

import pytest

from coordinator.ports import (
    AgentState,
    DependencyEdgeDoc,
    FormalSnapshot,
    HandoffReadyMessage,
    NoSuchRevisionError,
    NotificationIntent,
    PrincipalState,
    SnapshotInconsistentError,
    SnapshotUnavailableError,
    TaskNodeDoc,
)
from coordinator.service import CoordinatorService
from coordinator.store import (
    DISPATCH_DEAD,
    DISPATCH_FAILED,
    DISPATCH_PUBLISHED,
    DISPATCH_RESULT_UNKNOWN,
    MSG_HANDOFF_READY,
    MSG_HUMAN_NOTIFICATION,
    MSG_TERMINAL_SUMMARY,
    PENDING_DISPATCHED_UNKNOWN,
    PENDING_DONE,
    PENDING_READY,
    PENDING_SUPERSEDED,
    PENDING_WAITING,
    CoordinatorStore,
)


class FakeSnapshotPort:
    def __init__(self, snapshots: dict[str, FormalSnapshot] | None = None) -> None:
        self.snapshots = snapshots or {}
        self.calls: list[tuple[str, str]] = []

    def set(self, mapping_domain_id: str, formal_revision_id: str, snapshot: FormalSnapshot) -> None:
        self.snapshots[(mapping_domain_id, formal_revision_id)] = snapshot

    def fail_revision(self, mapping_domain_id: str, formal_revision_id: str, error: Exception) -> None:
        self.snapshots[(mapping_domain_id, formal_revision_id)] = error

    def get_formal_mapping_at_revision(self, mapping_domain_id: str, formal_revision_id: str) -> FormalSnapshot:
        self.calls.append((mapping_domain_id, formal_revision_id))
        value = self.snapshots.get((mapping_domain_id, formal_revision_id))
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise NoSuchRevisionError()
        return value


class FakeHandoffPublisher:
    def __init__(self) -> None:
        self.published: list[HandoffReadyMessage] = []
        self.fail_next = 0

    def publish(self, message: HandoffReadyMessage) -> None:
        if self.fail_next > 0:
            self.fail_next -= 1
            raise RuntimeError("redpanda unavailable")
        self.published.append(message)


class FakeNotificationPublisher:
    def __init__(self) -> None:
        self.published: list[NotificationIntent] = []
        self.fail_next = 0

    def publish(self, intent: NotificationIntent) -> None:
        if self.fail_next > 0:
            self.fail_next -= 1
            raise RuntimeError("email unavailable")
        self.published.append(intent)


class FakeAgentAvailability:
    """Registry stand-in keyed by the three states the coordinator acts on.

    `unregistered` is separate from the default (registered but unusable)
    because the notification kind, and therefore the owner's next step,
    depends on the difference.
    """

    def __init__(self, available: set[str], unregistered: set[str] | None = None) -> None:
        self.available = available
        self.unregistered = unregistered or set()

    def state_of(self, agent_id: str) -> AgentState:
        if agent_id in self.available:
            return AgentState.AVAILABLE
        if agent_id in self.unregistered:
            return AgentState.UNREGISTERED
        return AgentState.UNAVAILABLE


def make_service(connection, snapshot_port, publisher, notifications, agents, **kwargs) -> CoordinatorService:
    return CoordinatorService(
        CoordinatorStore(connection), snapshot_port, publisher, notifications, agents, **kwargs
    )


@pytest.fixture
def store():
    connection = sqlite3.connect(":memory:")
    yield CoordinatorStore(connection)
    connection.close()


def node(task_node_id: str, version_id: str, executor_refs: tuple[str, ...] = (),
         task_owner_id: str | None = None):
    return TaskNodeDoc(
        task_node_id=task_node_id, version_id=version_id,
        executor_refs=executor_refs, task_owner_id=task_owner_id,
    )


def edge(edge_id: str, source: str, target: str, source_v: str, target_v: str, **kwargs):
    """Versioned edge; edge_id is the logical identity, the version defaults to it.

    ``kwargs`` flow through to the judgment fields (dependency_kind,
    activation_condition, ...) for the ai4-quvy cases.
    """
    return DependencyEdgeDoc(
        logical_id=edge_id,
        version_id=f"{edge_id}-v1",
        source_node_id=source,
        source_version_id=source_v,
        target_node_id=target,
        target_version_id=target_v,
        **kwargs,
    )


# --------------------------------------------------------- root task dispatch

def test_root_node_is_not_auto_dispatched_on_publication():
    """ai4-10ja#4: a zero-inbound node must not auto-dispatch on any formal-revision event."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-1",)),),
        latest_published_by="owner-1",
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    service = make_service(
        connection, snapshot_port, publisher, FakeNotificationPublisher(), FakeAgentAvailability({"agent-1"})
    )
    service.on_formal_revision_published("map-1", "rev-1")
    assert publisher.published == []
    connection.close()


def test_dispatch_root_task_publishes_and_is_idempotent():
    """ai4-te1v dispatch_root_task publishes a root once; repeat is a no-op."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-1",)),),
        latest_published_by="owner-1",
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    notifications = FakeNotificationPublisher()
    service = make_service(
        connection, snapshot_port, publisher, notifications, FakeAgentAvailability({"agent-1"})
    )
    service.store.set_latest_revision("map-1", "rev-1")
    assert service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1") is True
    assert [m.task_node_id for m in publisher.published] == ["T1"]
    assert publisher.published[0].target_agent_id == "agent-1"
    pending = service.store.get_pending_handoff("map-1", "T1", "v1")
    assert pending.status == PENDING_DONE
    # repeat is idempotent (dedupe key excludes trigger revision)
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-2")
    assert len(publisher.published) == 1
    assert [i.notification_kind for i in notifications.published] == ["task_terminal_summary"]
    connection.close()


def test_dispatch_root_task_rejects_non_root_node():
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-1",)), node("T2", "v2", ("agent-2",))),
        edges=(edge("e1", "T1", "T2", "v1", "v2"),),
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    service = make_service(
        connection, snapshot_port, FakeHandoffPublisher(), FakeNotificationPublisher(), FakeAgentAvailability({"agent-1"})
    )
    service.store.set_latest_revision("map-1", "rev-1")
    with pytest.raises(ValueError):
        service.dispatch_root_task("map-1", "T2", "v2", trigger_revision_id="rev-1")
    connection.close()


def test_downstream_unblocks_after_task_completed():
    """Root T1 dispatched explicitly; T2 unblocks once T1 completion is recorded."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(
            node("T1", "v1", ("agent-1",)),
            node("T2", "v2", ("agent-2",)),
        ),
        edges=(edge("e1", "T1", "T2", "v1", "v2"),),
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    service = make_service(
        connection,
        snapshot_port,
        publisher,
        FakeNotificationPublisher(),
        FakeAgentAvailability({"agent-1", "agent-2"}),
    )
    service.on_formal_revision_published("map-1", "rev-1")
    assert publisher.published == []  # root T1 not auto-dispatched
    service.store.set_latest_revision("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    assert [m.task_node_id for m in publisher.published] == ["T1"]
    service.on_task_completed("map-1", "T1", "v1")
    assert [m.task_node_id for m in publisher.published] == ["T1", "T2"]
    pending_t2 = service.store.get_pending_handoff("map-1", "T2", "v2")
    assert pending_t2.status == PENDING_DONE
    connection.close()


def test_duplicate_formal_revision_does_not_redispatch():
    """ai4-10ja#1: a downstream node is dispatched once across two revisions."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(
            node("T1", "v1", ("agent-1",)),
            node("T2", "v2", ("agent-2",)),
        ),
        edges=(edge("e1", "T1", "T2", "v1", "v2"),),
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    snapshot_port.set("map-1", "rev-2", FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-2",
        nodes=(
            node("T1", "v1", ("agent-1",)),
            node("T2", "v2", ("agent-2",)),
        ),
        edges=(edge("e1", "T1", "T2", "v1", "v2"),),
    ))
    publisher = FakeHandoffPublisher()
    service = make_service(
        connection,
        snapshot_port,
        publisher,
        FakeNotificationPublisher(),
        FakeAgentAvailability({"agent-1", "agent-2"}),
    )
    service.on_formal_revision_published("map-1", "rev-1")
    service.store.set_latest_revision("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    service.on_task_completed("map-1", "T1", "v1")
    assert [m.task_node_id for m in publisher.published] == ["T1", "T2"]
    # rev-2 arrives; recompute must not re-dispatch T2 (already done)
    service.on_formal_revision_published("map-1", "rev-2")
    assert [m.task_node_id for m in publisher.published] == ["T1", "T2"]
    dispatch_rows = service.store.list_dispatches()
    handoff_rows = [d for d in dispatch_rows if d.message_type == MSG_HANDOFF_READY and d.target_agent_id]
    assert len(handoff_rows) == 2
    connection.close()


def test_done_is_terminal_after_upstream_moves():
    """ai4-10ja#2: an existing done PendingHandoff is never rolled back to waiting."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(
            node("T1", "v1", ("agent-1",)),
            node("T2", "v2", ("agent-2",)),
        ),
        edges=(edge("e1", "T1", "T2", "v1", "v2"),),
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    service = make_service(
        connection,
        snapshot_port,
        publisher,
        FakeNotificationPublisher(),
        FakeAgentAvailability({"agent-1", "agent-2"}),
    )
    service.on_formal_revision_published("map-1", "rev-1")
    service.store.set_latest_revision("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    service.on_task_completed("map-1", "T1", "v1")
    pending_t2 = service.store.get_pending_handoff("map-1", "T2", "v2")
    assert pending_t2.status == PENDING_DONE
    # upstream version moves to a new revision; recompute must not roll back
    snapshot_port.set("map-1", "rev-3", FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-3",
        nodes=(
            node("T1", "v1", ("agent-1",)),
            node("T2", "v2", ("agent-2",)),
        ),
        edges=(edge("e1", "T1", "T2", "v1", "v2"),),
    ))
    service.on_formal_revision_published("map-1", "rev-3")
    pending_t2 = service.store.get_pending_handoff("map-1", "T2", "v2")
    assert pending_t2.status == PENDING_DONE
    connection.close()


# ------------------------------------------------------------- executor refs

def test_executor_refs_selects_first_available():
    """ai4-10ja#3: executor_refs=(a1,a2) with only a2 online dispatches to a2."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-a1", "agent-a2"), task_owner_id="owner-1"),),
        latest_published_by="owner-1",
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    notifications = FakeNotificationPublisher()
    service = make_service(
        connection, snapshot_port, publisher, notifications, FakeAgentAvailability({"agent-a2"})
    )
    service.store.set_latest_revision("map-1", "rev-1")
    assert service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1") is True
    assert publisher.published[0].target_agent_id == "agent-a2"
    # The snapshot keeps the whole list: "nobody else was configured" and
    # "the wrong one was picked" must stay distinguishable after the fact.
    assert publisher.published[0].executor_ref_snapshot == ("agent-a1", "agent-a2")
    assert [i.notification_kind for i in notifications.published] == ["task_terminal_summary"]
    connection.close()


def test_all_executors_unavailable_keeps_waiting_and_notifies_human():
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-ghost", "agent-ghost2"), task_owner_id="owner-1"),),
        latest_published_by="owner-1",
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    notifications = FakeNotificationPublisher()
    service = make_service(
        connection, snapshot_port, FakeHandoffPublisher(), notifications, FakeAgentAvailability(set())
    )
    service.store.set_latest_revision("map-1", "rev-1")
    assert service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1") is False
    pending = service.store.get_pending_handoff("map-1", "T1", "v1")
    assert pending.status == PENDING_WAITING
    assert [i.notification_kind for i in notifications.published] == ["agent_unavailable"]
    assert notifications.published[0].recipients == ("owner-1",)
    connection.close()


def test_human_notification_recipient_is_task_owner_principal():
    """ai4-10ja#6: the human notification carries the principal id, not the domain."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", (), task_owner_id="principal-researcher"),),
        latest_published_by="owner-1",
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    notifications = FakeNotificationPublisher()
    service = make_service(
        connection, snapshot_port, FakeHandoffPublisher(), notifications, FakeAgentAvailability(set())
    )
    service.store.set_latest_revision("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    published = [i for i in notifications.published if i.notification_kind != "task_terminal_summary"]
    assert published[0].recipients == ("principal-researcher",)
    connection.close()


def test_missing_task_owner_keeps_waiting_without_notification():
    """ai4-10ja#6: missing task_owner_id means no guessing; keep waiting + record gap."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-ghost",), task_owner_id=None),),
        latest_published_by="owner-1",
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    notifications = FakeNotificationPublisher()
    service = make_service(
        connection, snapshot_port, FakeHandoffPublisher(), notifications, FakeAgentAvailability(set())
    )
    service.store.set_latest_revision("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    pending = service.store.get_pending_handoff("map-1", "T1", "v1")
    assert pending.status == PENDING_WAITING
    assert notifications.published == []
    unresolved = [d for d in service.store.list_dispatches() if "recipient_unresolved" in (d.error_summary or "")]
    assert any("task_owner_id_missing" in (d.error_summary or "") for d in unresolved)
    connection.close()


# ------------------------------------------------------------ retry / dead

def test_max_attempts_reaches_dead_and_is_not_replayed():
    """ai4-10ja#5: a dispatch hitting max_attempts goes dead and is not retried."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-1",)),),
        latest_published_by="owner-1",
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    service = make_service(
        connection, snapshot_port, publisher, FakeNotificationPublisher(),
        FakeAgentAvailability({"agent-1"}), max_attempts=2,
    )
    service.store.set_latest_revision("map-1", "rev-1")
    publisher.fail_next = 100  # every publish fails
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    unknown = service.store.list_dispatches(statuses=(DISPATCH_RESULT_UNKNOWN,))
    assert len(unknown) == 1
    # attempt 1 exceeds max_attempts=2? attempts: 1 -> retry -> 2 -> dead
    service.startup_scan()
    dead = service.store.list_dispatches(statuses=(DISPATCH_DEAD,))
    assert len(dead) == 1
    assert "max_attempts_exceeded" in (dead[0].error_summary or "")
    connection.close()


def test_snapshot_unavailable_keeps_waiting():
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot_port.fail_revision("map-1", "rev-1", SnapshotUnavailableError())
    service = make_service(
        connection, snapshot_port, FakeHandoffPublisher(), FakeNotificationPublisher(), FakeAgentAvailability(set())
    )
    service.on_formal_revision_published("map-1", "rev-1")
    assert service.store.list_pending_handoffs() == []
    assert service.store.get_latest_revision("map-1") is None
    connection.close()


def test_startup_scan_recovers_waiting_from_latest_revision():
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(
            node("T1", "v1", ("agent-1",)),
            node("T2", "v2", ("agent-2",)),
        ),
        edges=(edge("e1", "T1", "T2", "v1", "v2"),),
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    service = make_service(
        connection,
        snapshot_port,
        publisher,
        FakeNotificationPublisher(),
        FakeAgentAvailability({"agent-1", "agent-2"}),
    )
    service.on_formal_revision_published("map-1", "rev-1")
    assert publisher.published == []
    service.store.set_latest_revision("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    # scan keeps the waiting T2 without re-dispatching
    service.startup_scan()
    pending_t2 = service.store.get_pending_handoff("map-1", "T2", "v2")
    assert pending_t2.status == PENDING_WAITING
    assert [m.task_node_id for m in publisher.published] == ["T1"]
    connection.close()


def test_terminal_summary_goes_to_latest_publisher():
    """ai4-10ja#6: task_terminal_summary recipient is latest_published_by (ADR-0004)."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(
            node("T1", "v1", ("agent-1",)),
            node("T2", "v2", ("agent-2",)),
            node("T3", "v3", ("agent-3",)),
        ),
        edges=(
            edge("e1", "T1", "T2", "v1", "v2"),
            edge("e2", "T2", "T3", "v2", "v3"),
        ),
        latest_published_by="po-principal-1",
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    notifications = FakeNotificationPublisher()
    service = make_service(
        connection,
        snapshot_port,
        FakeHandoffPublisher(),
        notifications,
        FakeAgentAvailability({"agent-1", "agent-2", "agent-3"}),
    )
    service.store.set_latest_revision("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    service.on_task_completed("map-1", "T1", "v1")
    service.on_task_completed("map-1", "T2", "v2")
    terminal = [i for i in notifications.published if i.notification_kind == "task_terminal_summary"]
    assert len(terminal) == 1
    assert terminal[0].recipients == ("po-principal-1",)
    assert terminal[0].related["task_node_id"] == "T3"
    connection.close()

# ------------------------------------------------- notification kinds (ai4-xkbd)

class _StubDirectory:
    """Principal directory stand-in: unknown ids are ABSENT unless unreachable."""

    def __init__(self, known: dict[str, PrincipalState], reachable: bool = True) -> None:
        self.known = known
        self.reachable = reachable

    def state_of(self, principal_id: str) -> PrincipalState:
        if not self.reachable:
            return PrincipalState.UNKNOWN
        return self.known.get(principal_id, PrincipalState.ABSENT)


def _root_dispatch(executor_refs, agents, *, principals=None):
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", executor_refs, task_owner_id="owner-1"),),
        latest_published_by="owner-1",
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    notifications = FakeNotificationPublisher()
    kwargs = {} if principals is None else {"principals": principals}
    service = make_service(
        connection, snapshot_port, FakeHandoffPublisher(), notifications, agents, **kwargs
    )
    service.store.set_latest_revision("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    return connection, service, notifications


def test_empty_executor_refs_ask_the_owner_to_bind_a_workflow():
    connection, service, notifications = _root_dispatch((), FakeAgentAvailability(set()))
    assert [i.notification_kind for i in notifications.published] == ["workflow_binding_required"]
    assert notifications.published[0].recipients == ("owner-1",)
    assert "executor_refs 为空" in notifications.published[0].body
    connection.close()


def test_unregistered_executor_refs_ask_the_owner_to_fix_the_mapping():
    connection, service, notifications = _root_dispatch(
        ("agent-typo",), FakeAgentAvailability(set(), unregistered={"agent-typo"})
    )
    assert [i.notification_kind for i in notifications.published] == ["workflow_load_failed"]
    assert notifications.published[0].recipients == ("owner-1",)
    assert "agent-typo" in notifications.published[0].body
    connection.close()


def test_registered_but_offline_executor_reports_agent_unavailable():
    connection, service, notifications = _root_dispatch(("agent-1",), FakeAgentAvailability(set()))
    assert [i.notification_kind for i in notifications.published] == ["agent_unavailable"]
    connection.close()


def test_a_mix_of_unregistered_and_offline_refs_reports_agent_unavailable():
    # At least one ref exists as an agent, so the workflow is real and the
    # problem is availability; sending the owner to fix ids would be wrong.
    connection, service, notifications = _root_dispatch(
        ("agent-typo", "agent-offline"),
        FakeAgentAvailability(set(), unregistered={"agent-typo"}),
    )
    assert [i.notification_kind for i in notifications.published] == ["agent_unavailable"]
    connection.close()


def test_absent_recipient_principal_suppresses_the_send_and_keeps_waiting():
    connection, service, notifications = _root_dispatch(
        ("agent-1",),
        FakeAgentAvailability(set()),
        principals=_StubDirectory({"owner-1": PrincipalState.ABSENT}),
    )
    assert notifications.published == []
    pending = service.store.get_pending_handoff("map-1", "T1", "v1")
    assert pending.status == PENDING_WAITING
    failed = [d for d in service.store.list_dispatches() if d.status == DISPATCH_FAILED]
    assert [d.error_summary for d in failed] == ["recipient_unresolved:principal_absent"]
    connection.close()


def test_unreachable_principal_directory_fails_open_and_still_sends():
    connection, service, notifications = _root_dispatch(
        ("agent-1",),
        FakeAgentAvailability(set()),
        principals=_StubDirectory({}, reachable=False),
    )
    assert [i.notification_kind for i in notifications.published] == ["agent_unavailable"]
    connection.close()


def test_each_notification_kind_states_a_different_next_step():
    bodies = set()
    for refs, agents in (
        ((), FakeAgentAvailability(set())),
        (("agent-typo",), FakeAgentAvailability(set(), unregistered={"agent-typo"})),
        (("agent-1",), FakeAgentAvailability(set())),
    ):
        connection, _service, notifications = _root_dispatch(refs, agents)
        bodies.add(notifications.published[0].body)
        connection.close()
    assert len(bodies) == 3

# --------------------------------------- snapshot failures and root facts (ai4-98ye / ai4-hgq6)

def test_startup_scan_records_an_unreadable_snapshot_instead_of_skipping_it():
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot_port.fail_revision("map-1", "rev-1", SnapshotUnavailableError())
    service = make_service(
        connection, snapshot_port, FakeHandoffPublisher(), FakeNotificationPublisher(), FakeAgentAvailability(set())
    )
    service.store.set_latest_revision("map-1", "rev-1")

    service.startup_scan()

    failures = service.store.list_snapshot_failures()
    assert [(f["mapping_domain_id"], f["formal_revision_id"]) for f in failures] == [("map-1", "rev-1")]
    assert "SnapshotUnavailableError" in failures[0]["reason"]
    connection.close()


def test_a_readable_snapshot_clears_the_recorded_failure():
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot_port.fail_revision("map-1", "rev-1", SnapshotInconsistentError())
    service = make_service(
        connection, snapshot_port, FakeHandoffPublisher(), FakeNotificationPublisher(), FakeAgentAvailability(set())
    )
    service.store.set_latest_revision("map-1", "rev-1")
    service.startup_scan()
    assert service.store.list_snapshot_failures()

    snapshot_port.set("map-1", "rev-1", FormalSnapshot(mapping_domain_id="map-1", formal_revision_id="rev-1"))
    service.startup_scan()

    assert service.store.list_snapshot_failures() == []
    connection.close()


def test_retry_keeps_result_unknown_for_the_same_snapshot_errors():
    """ai4-98ye: unreadable and definitely-failed must stay different states."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-1",), task_owner_id="owner-1"),),
        latest_published_by="owner-1",
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    publisher.fail_next = 1
    service = make_service(
        connection, snapshot_port, publisher, FakeNotificationPublisher(), FakeAgentAvailability({"agent-1"})
    )
    service.store.set_latest_revision("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    assert [d.status for d in service.store.list_dispatches()] == [DISPATCH_RESULT_UNKNOWN]

    snapshot_port.fail_revision("map-1", "rev-1", NoSuchRevisionError())
    service.startup_scan()

    assert [d.status for d in service.store.list_dispatches()] == [DISPATCH_RESULT_UNKNOWN]
    assert [f["formal_revision_id"] for f in service.store.list_snapshot_failures()] == ["rev-1"]
    connection.close()


def test_root_node_leaves_a_waiting_fact_after_publication():
    """ai4-hgq6: not dispatching a root must not mean not recording it."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-1",), task_owner_id="owner-1"),),
        latest_published_by="owner-1",
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    service = make_service(
        connection, snapshot_port, publisher, FakeNotificationPublisher(), FakeAgentAvailability({"agent-1"})
    )

    service.on_formal_revision_published("map-1", "rev-1")

    pending = service.store.get_pending_handoff("map-1", "T1", "v1")
    assert pending.status == PENDING_WAITING
    assert publisher.published == []
    connection.close()


def test_a_completed_root_does_not_return_to_waiting_on_the_next_revision():
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    root = node("T1", "v1", ("agent-1",), task_owner_id="owner-1")
    snapshot_port.set(
        "map-1", "rev-1",
        FormalSnapshot(mapping_domain_id="map-1", formal_revision_id="rev-1", nodes=(root,), latest_published_by="owner-1"),
    )
    snapshot_port.set(
        "map-1", "rev-2",
        FormalSnapshot(mapping_domain_id="map-1", formal_revision_id="rev-2", nodes=(root,), latest_published_by="owner-1"),
    )
    service = make_service(
        connection, snapshot_port, FakeHandoffPublisher(), FakeNotificationPublisher(), FakeAgentAvailability({"agent-1"})
    )
    service.store.set_latest_revision("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    assert service.store.get_pending_handoff("map-1", "T1", "v1").status == PENDING_DONE

    service.on_formal_revision_published("map-1", "rev-2")

    assert service.store.get_pending_handoff("map-1", "T1", "v1").status == PENDING_DONE
    connection.close()

@pytest.mark.parametrize(
    "error_type", [SnapshotUnavailableError, SnapshotInconsistentError, NoSuchRevisionError]
)
def test_both_entry_points_treat_the_same_snapshot_error_alike(error_type):
    """ai4-98ye: one policy, so the two entry points cannot disagree."""
    event_connection = sqlite3.connect(":memory:")
    event_port = FakeSnapshotPort()
    event_port.fail_revision("map-1", "rev-1", error_type())
    event_service = make_service(
        event_connection, event_port, FakeHandoffPublisher(), FakeNotificationPublisher(), FakeAgentAvailability(set())
    )
    event_service.on_formal_revision_published("map-1", "rev-1")

    scan_connection = sqlite3.connect(":memory:")
    scan_port = FakeSnapshotPort()
    scan_port.fail_revision("map-1", "rev-1", error_type())
    scan_service = make_service(
        scan_connection, scan_port, FakeHandoffPublisher(), FakeNotificationPublisher(), FakeAgentAvailability(set())
    )
    scan_service.store.set_latest_revision("map-1", "rev-1")
    scan_service.startup_scan()

    event_failures = event_service.store.list_snapshot_failures()
    scan_failures = scan_service.store.list_snapshot_failures()
    assert [f["reason"] for f in event_failures] == [f["reason"] for f in scan_failures]
    assert event_failures[0]["reason"].startswith(error_type.__name__)
    # Retryable means "keep the facts", not "record a failure against them".
    assert event_service.store.list_pending_handoffs() == []
    assert scan_service.store.list_pending_handoffs() == []
    event_connection.close()
    scan_connection.close()


def test_downstream_handoff_carries_upstream_refs_and_executor_snapshot():
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(
            node("T1", "v1", ("agent-1",), task_owner_id="owner-1"),
            node("T2", "v2", ("agent-2",), task_owner_id="owner-1"),
        ),
        edges=(edge("e1", "T1", "T2", "v1", "v2"),),
        latest_published_by="owner-1",
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    service = make_service(
        connection, snapshot_port, publisher, FakeNotificationPublisher(), FakeAgentAvailability({"agent-1", "agent-2"})
    )
    service.store.set_latest_revision("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")

    service.on_task_completed("map-1", "T1", "v1")

    downstream = [m for m in publisher.published if m.task_node_id == "T2"]
    assert len(downstream) == 1
    assert downstream[0].upstream_source_refs == (("T1", "v1"),)
    assert downstream[0].executor_ref_snapshot == ("agent-2",)
    connection.close()

# --------------------------------------------- retry ceiling and transitions (ai4-7d92 / ai4-7cmr)

def test_max_attempts_default_is_five_and_docs_agree(monkeypatch, tmp_path):
    from coordinator.config import CoordinatorConfig, _max_attempts

    monkeypatch.delenv("SCIWEAVE_COORDINATOR_MAX_ATTEMPTS", raising=False)
    assert _max_attempts() == 5
    for name, value in (
        ("SCIWEAVE_COORDINATOR_SQLITE_PATH", str(tmp_path / "coordinator.sqlite")),
        ("SCIWEAVE_COORDINATOR_RETRY_INITIAL_SECONDS", "1"),
        ("SCIWEAVE_COORDINATOR_RETRY_MULTIPLIER", "2"),
        ("SCIWEAVE_COORDINATOR_RETRY_MAX_SECONDS", "60"),
        ("SCIWEAVE_COORDINATOR_DISPATCH_POLL_SECONDS", "5"),
    ):
        monkeypatch.setenv(name, value)
    assert CoordinatorConfig.from_environment().max_attempts == 5

    # Three places state the ceiling; an operator reading the docs must get
    # the behaviour the code has.
    root = Path(__file__).resolve().parents[1]
    assert "SCIWEAVE_COORDINATOR_MAX_ATTEMPTS=5" in (root / ".env.example").read_text(encoding="utf-8")
    assert "默认 5" in (root / "README.md").read_text(encoding="utf-8")


def test_below_the_ceiling_a_dispatch_is_retried_and_succeeds():
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-1",)),),
        latest_published_by="owner-1",
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    service = make_service(
        connection, snapshot_port, publisher, FakeNotificationPublisher(),
        FakeAgentAvailability({"agent-1"}), max_attempts=5,
    )
    service.store.set_latest_revision("map-1", "rev-1")
    publisher.fail_next = 1
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    assert [d.attempt_count for d in service.store.list_dispatches()] == [1]

    service.startup_scan()

    published = service.store.list_dispatches(statuses=(DISPATCH_PUBLISHED,))
    assert [d.attempt_count for d in published] == [2]
    assert service.store.list_dispatches(statuses=(DISPATCH_DEAD,)) == []
    connection.close()


def test_an_illegal_transition_keeps_the_stored_status_and_the_round_advances():
    """ai4-7cmr: one stale node version must not stop the rest of the round."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(
            node("T1", "v1", ("agent-1",), task_owner_id="owner-1"),
            node("T2", "v2", ("agent-2",), task_owner_id="owner-1"),
            node("T3", "v3", ("agent-3",), task_owner_id="owner-1"),
        ),
        edges=(
            edge("e1", "T1", "T2", "v1", "v2"),
            edge("e2", "T2", "T3", "v2", "v3"),
        ),
        latest_published_by="owner-1",
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    service = make_service(
        connection, snapshot_port, publisher, FakeNotificationPublisher(),
        FakeAgentAvailability({"agent-1", "agent-2", "agent-3"}),
    )
    service.store.set_latest_revision("map-1", "rev-1")
    # T2's stored fact moved on to superseded; the revision still carries v2.
    service.store.upsert_pending_handoff("map-1", "T2", "v2", (), ("agent-2",), PENDING_WAITING, "rev-0")
    service.store.mark_superseded("map-1", "T2", "v2")

    service.on_formal_revision_published("map-1", "rev-1")

    assert service.store.get_pending_handoff("map-1", "T2", "v2").status == PENDING_SUPERSEDED
    # T3 has no completed upstream yet, but the round reached it and left a
    # waiting fact instead of dying on T2.
    assert service.store.get_pending_handoff("map-1", "T3", "v3").status == PENDING_WAITING
    connection.close()

def test_missing_latest_published_by_is_recorded_not_guessed():
    """ai4-xkbd: a chain with no approver must not invent a recipient."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-1",), task_owner_id="owner-1"),),
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    notifications = FakeNotificationPublisher()
    service = make_service(
        connection, snapshot_port, FakeHandoffPublisher(), notifications, FakeAgentAvailability({"agent-1"})
    )
    service.store.set_latest_revision("map-1", "rev-1")

    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")

    assert [i.notification_kind for i in notifications.published] == []
    failed = service.store.list_dispatches(statuses=(DISPATCH_FAILED,))
    assert [d.error_summary for d in failed] == ["recipient_unresolved:latest_published_by_missing"]
    connection.close()


# ----------------------------------------------------------- ai4-quvy: dependency kinds

def _two_node_service(connection, snapshot_port, publisher, notifications, agents):
    service = make_service(connection, snapshot_port, publisher, notifications, agents)
    service.store.set_latest_revision("map-1", "rev-1")
    return service


def _chain_snapshot(*edge_kwargs):
    return FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(
            node("T1", "v1", ("agent-1",)),
            node("T2", "v2", ("agent-2",), task_owner_id="owner-1"),
        ),
        edges=tuple(edge("e1", "T1", "T2", "v1", "v2", **kwargs) for kwargs in edge_kwargs),
        latest_published_by="owner-1",
    )


def test_blocking_kind_requires_upstream_completion():
    """ai4-quvy: blocking edges do not advance until the upstream completion fact exists."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = _chain_snapshot({"dependency_kind": "blocking", "required_outputs": ("data.csv",), "blocks_until": "T1/output"})
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    service = _two_node_service(
        connection, snapshot_port, publisher, FakeNotificationPublisher(), FakeAgentAvailability({"agent-1", "agent-2"})
    )
    service.on_formal_revision_published("map-1", "rev-1")
    service.store.set_latest_revision("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    # T1 complete; T2 was blocked - waiting, not dispatched.
    service.on_formal_revision_published("map-1", "rev-1")
    pending_t2 = service.store.get_pending_handoff("map-1", "T2", "v2")
    assert pending_t2 is None or pending_t2.status == PENDING_WAITING
    service.on_task_completed("map-1", "T1", "v1")
    assert publisher.published[-1].task_node_id == "T2"
    assert service.store.get_pending_handoff("map-1", "T2", "v2").status == PENDING_DONE
    connection.close()


def test_conditional_edge_with_condition_parks_and_asks_human():
    """ai4-quvy: an activation_condition the coordinator cannot evaluate must not auto-advance."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = _chain_snapshot({"dependency_kind": "conditional", "activation_condition": "upstream_output >= threshold"})
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    notifications = FakeNotificationPublisher()
    service = _two_node_service(
        connection, snapshot_port, publisher, notifications,
        FakeAgentAvailability({"agent-1", "agent-2"}),
    )
    service.on_formal_revision_published("map-1", "rev-1")
    service.store.set_latest_revision("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    service.on_task_completed("map-1", "T1", "v1")
    # T2 stays waiting with activation_condition_unknown and a human is asked.
    pending_t2 = service.store.get_pending_handoff("map-1", "T2", "v2")
    assert pending_t2.status == PENDING_WAITING
    assert pending_t2.waiting_reason == "activation_condition_unknown"
    assert [i.notification_kind for i in notifications.published if "激活" in i.subject] != []
    connection.close()


def test_conditional_edge_without_condition_falls_back_to_upstream():
    """ai4-quvy: a conditional edge with no condition behaves like the completion rule."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = _chain_snapshot({"dependency_kind": "conditional", "activation_condition": None})
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    service = _two_node_service(
        connection, snapshot_port, publisher, FakeNotificationPublisher(),
        FakeAgentAvailability({"agent-1", "agent-2"}),
    )
    service.on_formal_revision_published("map-1", "rev-1")
    service.store.set_latest_revision("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    service.on_task_completed("map-1", "T1", "v1")
    assert publisher.published[-1].task_node_id == "T2"
    connection.close()


def test_alternative_edge_with_condition_parks_not_guesses():
    """ai4-quvy: alternative edges must not let the agent pick a route itself."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = _chain_snapshot({"dependency_kind": "alternative", "activation_condition": "route==B", "alternative_group_id": "grp-1"})
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    service = _two_node_service(
        connection, snapshot_port, publisher, FakeNotificationPublisher(),
        FakeAgentAvailability({"agent-1", "agent-2"}),
    )
    service.on_formal_revision_published("map-1", "rev-1")
    service.store.set_latest_revision("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    service.on_task_completed("map-1", "T1", "v1")
    pending_t2 = service.store.get_pending_handoff("map-1", "T2", "v2")
    assert pending_t2.status == PENDING_WAITING
    assert pending_t2.waiting_reason == "activation_condition_unknown"
    connection.close()


# ----------------------------------------------------------- ai4-fu4i: edge version refs

def test_handoff_message_carries_incoming_edge_version_refs():
    """ai4-fu4i: task_handoff_ready carries the incoming edges' (logical_id, version_id)."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-1",)), node("T2", "v2", ("agent-2",))),
        edges=(edge("e1", "T1", "T2", "v1", "v2"),),
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    service = _two_node_service(
        connection, snapshot_port, publisher, FakeNotificationPublisher(),
        FakeAgentAvailability({"agent-1", "agent-2"}),
    )
    service.on_formal_revision_published("map-1", "rev-1")
    service.store.set_latest_revision("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    service.on_task_completed("map-1", "T1", "v1")
    t2_message = publisher.published[-1]
    assert t2_message.task_node_id == "T2"
    # Edge logical_id e1, version default e1-v1 from the test helper.
    assert t2_message.dependency_edge_version_refs == (("e1", "e1-v1"),)
    connection.close()


def test_handoff_message_edge_refs_stay_array_for_single_edge():
    """ai4-fu4i: one incoming edge still yields a sequence, not a scalar."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-1",)), node("T2", "v2", ("agent-2",))),
        edges=(edge("e1", "T1", "T2", "v1", "v2"),),
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    service = _two_node_service(
        connection, snapshot_port, publisher, FakeNotificationPublisher(),
        FakeAgentAvailability({"agent-1", "agent-2"}),
    )
    service.on_formal_revision_published("map-1", "rev-1")
    service.store.set_latest_revision("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    service.on_task_completed("map-1", "T1", "v1")
    refs = publisher.published[-1].dependency_edge_version_refs
    assert isinstance(refs, tuple) and len(refs) == 1
    connection.close()

# ------------------------------- notification kind and dedupe granularity (ai4-lu7y)

def test_condition_hold_uses_its_own_notification_kind():
    """ai4-lu7y: a dependency condition is not an unavailable executor."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot_port.set(
        "map-1", "rev-1",
        _chain_snapshot({"dependency_kind": "conditional", "activation_condition": "upstream_output >= threshold"}),
    )
    notifications = FakeNotificationPublisher()
    service = _two_node_service(
        connection, snapshot_port, FakeHandoffPublisher(), notifications,
        FakeAgentAvailability({"agent-1", "agent-2"}),
    )
    service.on_formal_revision_published("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    service.on_task_completed("map-1", "T1", "v1")

    kinds = [i.notification_kind for i in notifications.published]
    assert kinds == ["dependency_condition_hold"]
    assert "激活条件" in notifications.published[0].subject
    connection.close()


def test_condition_hold_and_unavailable_executor_both_reach_the_owner():
    """ai4-lu7y: two reasons about one node version are two notifications."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot_port.set(
        "map-1", "rev-1",
        _chain_snapshot({"dependency_kind": "conditional", "activation_condition": "route==B"}),
    )
    # Same node versions, condition now resolved: the gate passes, but the
    # executor is gone. The second reason must not collide with the first.
    snapshot_port.set("map-1", "rev-2", _chain_snapshot({"dependency_kind": "conditional"}))
    notifications = FakeNotificationPublisher()
    service = _two_node_service(
        connection, snapshot_port, FakeHandoffPublisher(), notifications,
        FakeAgentAvailability({"agent-1"}),
    )
    service.on_formal_revision_published("map-1", "rev-1")
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    service.on_task_completed("map-1", "T1", "v1")
    assert [i.notification_kind for i in notifications.published] == ["dependency_condition_hold"]

    service.on_formal_revision_published("map-1", "rev-2")

    assert [i.notification_kind for i in notifications.published] == [
        "dependency_condition_hold",
        "agent_unavailable",
    ]
    notification_keys = [
        d.dedupe_key for d in service.store.list_dispatches() if d.message_type == MSG_HUMAN_NOTIFICATION
    ]
    assert len(set(notification_keys)) == 2
    connection.close()


def test_human_notification_dedupe_key_carries_the_kind():
    from coordinator.service import CoordinatorService
    from coordinator.store import PendingHandoff

    pending = PendingHandoff(
        pending_handoff_id="p1",
        mapping_domain_id="map-1",
        task_node_id="T2",
        target_node_version_ref="v2",
        upstream_source_refs=(),
        executor_refs=(),
        executor_agent_id=None,
        status=PENDING_WAITING,
        last_trigger_revision_id=None,
        created_at="t0",
        updated_at="t0",
    )
    hold = CoordinatorService._dedupe("map-1", pending, MSG_HUMAN_NOTIFICATION, "rev-1", discriminator="dependency_condition_hold")
    gone = CoordinatorService._dedupe("map-1", pending, MSG_HUMAN_NOTIFICATION, "rev-1", discriminator="agent_unavailable")
    handoff = CoordinatorService._dedupe("map-1", pending, MSG_HANDOFF_READY, "rev-1")
    assert hold != gone
    # Handoff dispatch keeps its old shape: one handoff per node version.
    assert handoff == "map-1:T2:v2:task_handoff_ready"


def test_retry_republishes_the_kind_the_row_was_created_for():
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot_port.set(
        "map-1", "rev-1",
        _chain_snapshot({"dependency_kind": "conditional", "activation_condition": "route==B"}),
    )
    notifications = FakeNotificationPublisher()
    notifications.fail_next = 1
    service = _two_node_service(
        connection, snapshot_port, FakeHandoffPublisher(), notifications,
        FakeAgentAvailability({"agent-1", "agent-2"}),
    )
    service.on_formal_revision_published("map-1", "rev-1")
    # The first attempt reached the email service and was rejected: the fact
    # stays result_unknown, nothing was delivered.
    assert notifications.published == []
    assert [
        d.status for d in service.store.list_dispatches() if d.message_type == MSG_HUMAN_NOTIFICATION
    ] == [DISPATCH_RESULT_UNKNOWN]

    service.startup_scan()

    # The retry reproduces the row's own kind rather than re-deriving one
    # from state that may have moved on.
    assert [i.notification_kind for i in notifications.published] == ["dependency_condition_hold"]
    connection.close()

def test_unconfigured_notification_transport_keeps_the_dispatch_retryable():
    """ai4-3gvf: a notification nobody could send must not look delivered.

    The degraded publisher raises instead of returning quietly; the dispatch
    stays ``failed`` with a configuration reason, so configuring the email
    endpoint later still lets the owner hear about the task.
    """
    from coordinator.ports import NotificationTransportUnavailable

    class _UnconfiguredPublisher:
        def publish(self, intent):
            raise NotificationTransportUnavailable("email MCP not configured")

    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", (), task_owner_id="owner-1"),),
        latest_published_by="owner-1",
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    service = _two_node_service(
        connection, snapshot_port, FakeHandoffPublisher(), _UnconfiguredPublisher(),
        FakeAgentAvailability(set()),
    )
    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")

    notifications = [
        d for d in service.store.list_dispatches() if d.message_type == MSG_HUMAN_NOTIFICATION
    ]
    assert [d.status for d in notifications] == [DISPATCH_FAILED]
    assert notifications[0].error_summary.startswith("notification_transport_unconfigured")
    connection.close()

def test_repeating_a_ready_dispatch_does_not_bypass_max_attempts():
    """ai4-ubcp: a re-dispatched node must not republish outside the retry policy.

    After a failed publish the dispatch is result_unknown with attempt_count=1.
    Re-running dispatch_root_task for the same trigger must NOT call publish
    again (that reset attempt_count and made max_attempts unreachable); the
    retry poll owns the row instead.
    """
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-1",)),),
        latest_published_by="owner-1",
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    service = make_service(
        connection, snapshot_port, publisher, FakeNotificationPublisher(),
        FakeAgentAvailability({"agent-1"}),
    )
    service.store.set_latest_revision("map-1", "rev-1")
    publisher.fail_next = 100  # every publish fails

    service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    attempts_after_first = publisher.fail_next
    first = service.store.list_dispatches(statuses=(DISPATCH_RESULT_UNKNOWN,))
    assert len(first) == 1
    assert first[0].attempt_count == 1

    # The same trigger fires again (recompute): no new publish attempt, and the
    # recorded attempt_count is untouched.
    published = service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1")
    assert published is False
    assert publisher.fail_next == attempts_after_first  # publish() was not called
    still_unknown = service.store.list_dispatches(statuses=(DISPATCH_RESULT_UNKNOWN,))
    assert len(still_unknown) == 1
    assert still_unknown[0].attempt_count == 1
    connection.close()


def test_main_passes_max_attempts_from_config():
    """ai4-ubcp: SCIWEAVE_COORDINATOR_MAX_ATTEMPTS must reach the service.

    Guards the wiring itself: config.from_environment parsed max_attempts but
    build() once dropped it on the floor, so the env var silently did nothing.
    """
    import importlib.util
    import inspect
    from pathlib import Path

    main_path = Path(__file__).resolve().parents[1] / "src" / "main.py"
    spec = importlib.util.spec_from_file_location("coordinator_entry_point_build", main_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = inspect.getsource(module.build)
    assert "max_attempts=config.max_attempts" in source


def test_pending_handoff_records_the_executor_actually_selected():
    """ai4-0k36: the stored executor must be the chosen one, not executor_refs[0]."""
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-a1", "agent-a2"), task_owner_id="owner-1"),),
        latest_published_by="owner-1",
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    notifications = FakeNotificationPublisher()
    service = make_service(
        connection, snapshot_port, publisher, notifications, FakeAgentAvailability({"agent-a2"})
    )
    service.store.set_latest_revision("map-1", "rev-1")
    assert service.dispatch_root_task("map-1", "T1", "v1", trigger_revision_id="rev-1") is True
    pending = service.store.get_pending_handoff("map-1", "T1", "v1")
    # a2 was picked even though a1 is declared first, and the row says so.
    assert pending.executor_agent_id == "agent-a2"
    assert pending.executor_refs == ("agent-a1", "agent-a2")
    connection.close()
