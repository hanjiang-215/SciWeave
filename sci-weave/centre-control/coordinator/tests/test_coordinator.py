import sqlite3

import pytest

from coordinator.ports import (
    DependencyEdgeDoc,
    FormalSnapshot,
    HandoffReadyMessage,
    NoSuchRevisionError,
    NotificationIntent,
    SnapshotUnavailableError,
    TaskNodeDoc,
)
from coordinator.service import CoordinatorService
from coordinator.store import (
    DISPATCH_FAILED,
    DISPATCH_PUBLISHED,
    DISPATCH_RESULT_UNKNOWN,
    MSG_HANDOFF_READY,
    MSG_HUMAN_NOTIFICATION,
    MSG_TERMINAL_SUMMARY,
    PENDING_DISPATCHED_UNKNOWN,
    PENDING_DONE,
    PENDING_READY,
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
    def __init__(self, available: set[str]) -> None:
        self.available = available

    def is_available(self, agent_id: str) -> bool:
        return agent_id in self.available


def make_service(connection, snapshot_port, publisher, notifications, agents) -> CoordinatorService:
    return CoordinatorService(
        CoordinatorStore(connection), snapshot_port, publisher, notifications, agents
    )


@pytest.fixture
def store():
    connection = sqlite3.connect(":memory:")
    yield CoordinatorStore(connection)
    connection.close()


def node(task_node_id: str, version_id: str, executor_refs: tuple[str, ...] = ()):
    return TaskNodeDoc(task_node_id=task_node_id, version_id=version_id, executor_refs=executor_refs)


def edge(edge_id: str, source: str, target: str, source_v: str, target_v: str):
    return DependencyEdgeDoc(
        edge_id=edge_id,
        source_node_id=source,
        source_version_id=source_v,
        target_node_id=target,
        target_version_id=target_v,
    )


def test_conditions_met_publishes_handoff_for_ready_node():
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-1",)),),
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    notifications = FakeNotificationPublisher()
    service = make_service(
        connection, snapshot_port, publisher, notifications, FakeAgentAvailability({"agent-1"})
    )
    service.on_formal_revision_published("map-1", "rev-1")
    assert [m.task_node_id for m in publisher.published] == ["T1"]
    assert publisher.published[0].target_agent_id == "agent-1"
    pending = service.store.get_pending_handoff("map-1", "T1", "v1")
    assert pending.status == PENDING_DONE
    # 无后继时额外发送终点汇总
    assert [i.notification_kind for i in notifications.published] == ["task_terminal_summary"]
    connection.close()


def test_conditions_not_met_keeps_waiting():
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    # T2 依赖 T1，但 T1 尚无完成事实
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-1",)), node("T2", "v2", ("agent-2",))),
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
    assert [m.task_node_id for m in publisher.published] == ["T1"]
    pending_t2 = service.store.get_pending_handoff("map-1", "T2", "v2")
    assert pending_t2.status == PENDING_WAITING
    connection.close()


def test_task_completed_unblocks_downstream():
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
    service = make_service(
        connection,
        snapshot_port,
        publisher,
        FakeNotificationPublisher(),
        FakeAgentAvailability({"agent-1", "agent-2"}),
    )
    service.on_formal_revision_published("map-1", "rev-1")
    assert [m.task_node_id for m in publisher.published] == ["T1"]
    service.on_task_completed("map-1", "T1", "v1")
    assert [m.task_node_id for m in publisher.published] == ["T1", "T2"]
    pending_t2 = service.store.get_pending_handoff("map-1", "T2", "v2")
    assert pending_t2.status == PENDING_DONE
    connection.close()


def test_duplicate_event_does_not_publish_twice():
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-1",)),),
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    service = make_service(
        connection, snapshot_port, publisher, FakeNotificationPublisher(), FakeAgentAvailability({"agent-1"})
    )
    service.on_formal_revision_published("map-1", "rev-1")
    service.on_formal_revision_published("map-1", "rev-1")
    assert len(publisher.published) == 1
    connection.close()


def test_agent_unavailable_keeps_waiting_and_notifies_human():
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-ghost",)),),
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    notifications = FakeNotificationPublisher()
    service = make_service(
        connection, snapshot_port, FakeHandoffPublisher(), notifications, FakeAgentAvailability(set())
    )
    service.on_formal_revision_published("map-1", "rev-1")
    pending = service.store.get_pending_handoff("map-1", "T1", "v1")
    assert pending.status == PENDING_WAITING
    assert [i.notification_kind for i in notifications.published] == ["agent_unavailable"]
    connection.close()


def test_unknown_result_is_retried_on_startup_scan():
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    snapshot = FormalSnapshot(
        mapping_domain_id="map-1",
        formal_revision_id="rev-1",
        nodes=(node("T1", "v1", ("agent-1",)),),
    )
    snapshot_port.set("map-1", "rev-1", snapshot)
    publisher = FakeHandoffPublisher()
    publisher.fail_next = 1  # 首次发布失败 -> result_unknown
    service = make_service(
        connection, snapshot_port, publisher, FakeNotificationPublisher(), FakeAgentAvailability({"agent-1"})
    )
    service.on_formal_revision_published("map-1", "rev-1")
    assert len(publisher.published) == 0
    unknown = service.store.list_dispatches(statuses=(DISPATCH_RESULT_UNKNOWN,))
    assert len(unknown) == 1
    assert unknown[0].message_type == MSG_HANDOFF_READY
    # 启动扫描重试
    service.startup_scan()
    assert len(publisher.published) == 1
    recovered = service.store.get_dispatch(unknown[0].dispatch_id)
    assert recovered.status == DISPATCH_PUBLISHED
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
        nodes=(node("T1", "v1", ("agent-1",)), node("T2", "v2", ("agent-2",))),
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
    assert [m.task_node_id for m in publisher.published] == ["T1"]
    # 不触发完成事件，但模拟一个进程里等待中的 T2；启动扫描应保持其 waiting
    service.startup_scan()
    pending_t2 = service.store.get_pending_handoff("map-1", "T2", "v2")
    assert pending_t2.status == PENDING_WAITING
    assert len(publisher.published) == 1  # 不重复发布 T1
    connection.close()


def test_terminal_summary_only_for_nodes_without_successors():
    connection = sqlite3.connect(":memory:")
    snapshot_port = FakeSnapshotPort()
    # 链式 T1 -> T2 -> T3，T1/T2 有后继，只有 T3 是终点
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
    service.on_formal_revision_published("map-1", "rev-1")
    # 只发 T1；T3 未满足条件（依赖 T2 未完成），无终点汇总
    assert notifications.published == []
    service.on_task_completed("map-1", "T1", "v1")
    assert notifications.published == []
    service.on_task_completed("map-1", "T2", "v2")
    assert [i.notification_kind for i in notifications.published] == ["task_terminal_summary"]
    assert notifications.published[0].related["task_node_id"] == "T3"
    connection.close()